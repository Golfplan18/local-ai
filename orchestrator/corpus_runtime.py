"""Corpus runtime — C-Instance and C-Validate execution.

Implements the mechanical CFF modes that take an existing corpus template
and instantiate or validate corpus instances. The model-driven CFF modes
(C-Design, C-Modify) are not implemented here — they're full framework
executions that produce or modify templates via multi-step elicitation.

C-Instance: takes a corpus template, produces a fresh corpus instance for
a given period. Mechanical — copies the template's section structure into
a new file with empty section bodies, frontmatter updated for the period.

C-Validate: takes a corpus instance, checks each section's population
state against the template's missing-data behavior and section schema.
Returns a validation report.

Both functions emit oversight events through oversight_events.emit so the
meta-layer apparatus sees them.

Per Reference — Meta-Layer Architecture §5 (E7, E9) and §13 (corpus_watcher
detects file changes; this module fires explicit events for code-driven
operations).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None

from corpus_parser import (
    parse_corpus_file,
    parse_corpus_text,
    ParsedCorpus,
    CorpusSection,
)


# ---------- Result types ----------

@dataclass
class InstantiateResult:
    success: bool
    instance_path: str = ""
    template_path: str = ""
    period: str = ""
    sections_created: list = field(default_factory=list)
    error: str = ""


@dataclass
class SectionValidation:
    section_id: str
    populated: bool
    body_length: int
    schema_violations: list = field(default_factory=list)
    cadence_status: str = ""  # "ok" / "stale" / "unknown"
    notes: str = ""


@dataclass
class ValidateResult:
    success: bool  # True iff PASS
    instance_path: str = ""
    overall_status: str = "PASS"  # "PASS" / "PARTIAL" / "FAIL"
    sections: list = field(default_factory=list)  # list[SectionValidation]
    missing_sections: list = field(default_factory=list)
    error: str = ""

    @property
    def populated_count(self) -> int:
        return sum(1 for s in self.sections if s.populated)

    @property
    def total_count(self) -> int:
        return len(self.sections)


# ---------- C-Instance ----------

def c_instance(
    template_path: str,
    period: str,
    instance_dir: str,
    workflow_id: Optional[str] = None,
    project_nexus: Optional[str] = None,
    chain_inputs: Optional[list] = None,
) -> InstantiateResult:
    """Create a fresh corpus instance from a template.

    Args:
        template_path: path to the corpus template markdown file
        period: reporting period label (e.g., "2026-05" or "Q2-2026")
        instance_dir: directory where the new instance file is written
        workflow_id: optional workflow id for the event payload
        project_nexus: optional project nexus for the event payload
        chain_inputs: optional list of source-corpus instance paths whose
            chain content should be pulled into this instance

    Returns: InstantiateResult with instance_path on success.
    """
    if not os.path.isfile(template_path):
        return InstantiateResult(success=False, error=f"Template not found: {template_path}")

    try:
        template = parse_corpus_file(template_path)
    except Exception as e:
        return InstantiateResult(success=False, error=f"Failed to parse template: {e}")

    if not template.is_template:
        return InstantiateResult(
            success=False,
            error=f"File at {template_path!r} is not a template (frontmatter type != corpus_template)",
        )

    if not template.sections:
        return InstantiateResult(
            success=False,
            error="Template declares no sections — nothing to instantiate.",
        )

    os.makedirs(instance_dir, exist_ok=True)

    # Generate the instance filename
    safe_period = re.sub(r"[^A-Za-z0-9_-]+", "_", period)
    instance_name = f"{_template_slug(template, template_path)}-{safe_period}.md"
    instance_path = os.path.join(instance_dir, instance_name)

    if os.path.exists(instance_path):
        return InstantiateResult(
            success=False,
            error=f"Instance already exists at {instance_path}; refusing to overwrite.",
        )

    # Build the instance content
    content = _build_instance_content(template, template_path, period, chain_inputs or [])

    try:
        with open(instance_path, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        return InstantiateResult(success=False, error=f"Failed to write instance: {e}")

    sections_created = [s.section_id for s in template.sections]

    # Emit CorpusInstanceCreated event
    try:
        from oversight_events import emit
        emit({
            "event_type": "CorpusInstanceCreated",
            "workflow_id": workflow_id or "",
            "project_nexus": project_nexus or "",
            "corpus_template_path": template_path,
            "corpus_template_version": template.template_version,
            "instance_path": instance_path,
            "instance_period": period,
            "chain_inputs_pulled": chain_inputs or [],
        })
    except Exception:
        pass

    return InstantiateResult(
        success=True,
        instance_path=instance_path,
        template_path=template_path,
        period=period,
        sections_created=sections_created,
    )


def _template_slug(template: ParsedCorpus, template_path: str) -> str:
    """Derive a slug for the instance filename from the template."""
    base = template.title or os.path.splitext(os.path.basename(template_path))[0]
    base = re.sub(r"^Corpus Template[-\s—:]+", "", base, flags=re.IGNORECASE).strip()
    return re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-") or "corpus"


def _build_instance_content(
    template: ParsedCorpus,
    template_path: str,
    period: str,
    chain_inputs: list,
) -> str:
    """Construct the markdown body of a fresh corpus instance."""
    lines: list[str] = []

    # Frontmatter
    lines.append("---")
    lines.append("type: corpus_instance")
    lines.append(f"template: {os.path.basename(template_path)}")
    lines.append(f"template_version: {template.template_version or 'unknown'}")
    lines.append(f"period: {period}")
    lines.append(f"created_at: {_now_iso()}")
    if chain_inputs:
        lines.append("chain_inputs:")
        for ci in chain_inputs:
            lines.append(f"  - {ci}")
    lines.append("---")
    lines.append("")

    # Title
    title_base = template.title or "Corpus Instance"
    title_base = re.sub(r"^Corpus Template[-\s—:]+", "", title_base, flags=re.IGNORECASE).strip()
    lines.append(f"# {title_base} — {period}")
    lines.append("")

    # Sections — each gets a heading in a parser-recognized format and an empty body
    if template.sections:
        lines.append("## Sections")
        lines.append("")
        for section in template.sections:
            display_name = section.name or section.section_id
            lines.append(f"### Section {section.section_id} — {display_name}")
            if section.source_pff:
                lines.append(f"*Source PFF:* `{section.source_pff}`")
            if section.missing_data_behavior:
                lines.append(f"*Missing-data behavior:* {section.missing_data_behavior}")
            if section.oversight and section.oversight.cadence:
                lines.append(f"*Cadence:* {section.oversight.cadence}")
            lines.append("")
            lines.append("<!-- Section content goes here. -->")
            lines.append("")

    return "\n".join(lines)


# ---------- C-Validate ----------

# Heuristic for "populated": a section's body must contain at least one
# non-comment, non-whitespace character beyond the section heading + meta lines.
_PLACEHOLDER_PATTERNS = [
    re.compile(r"<!--.*?-->", re.DOTALL),
    re.compile(r"^\s*\*[^*]+:\*\s.*$", re.MULTILINE),  # *Source PFF:* lines, etc.
]


def c_validate(
    instance_path: str,
    template_path: Optional[str] = None,
    workflow_id: Optional[str] = None,
    project_nexus: Optional[str] = None,
) -> ValidateResult:
    """Validate a corpus instance against its template.

    Checks per section:
      - Populated (has content beyond the heading + meta lines)
      - Schema conformance (basic — full schema validation requires a
        machine-readable schema language; the MVP checks for non-empty
        content matching declared cadence)
      - Cadence (deferred — needs date/period awareness)

    Returns: ValidateResult with overall_status PASS / PARTIAL / FAIL.
    """
    if not os.path.isfile(instance_path):
        return ValidateResult(success=False, instance_path=instance_path,
                              error=f"Instance not found: {instance_path}",
                              overall_status="FAIL")

    try:
        instance = parse_corpus_file(instance_path)
    except Exception as e:
        return ValidateResult(success=False, instance_path=instance_path,
                              error=f"Failed to parse instance: {e}",
                              overall_status="FAIL")

    # Resolve template path: explicit arg, or from instance frontmatter
    if not template_path:
        template_filename = instance.frontmatter.get("template", "")
        if template_filename:
            instance_dir = os.path.dirname(instance_path)
            for candidate in (
                os.path.join(instance_dir, template_filename),
                os.path.join(instance_dir, "..", template_filename),
                os.path.join(os.path.dirname(instance_dir), template_filename),
            ):
                if os.path.isfile(candidate):
                    template_path = os.path.abspath(candidate)
                    break

    template_sections: list[CorpusSection] = []
    if template_path and os.path.isfile(template_path):
        try:
            template = parse_corpus_file(template_path)
            template_sections = template.sections
        except Exception:
            pass
    if not template_sections:
        # Fall back: validate against the instance's own section list
        template_sections = instance.sections

    sections_validated: list[SectionValidation] = []
    missing_sections: list[str] = []

    instance_section_map = {s.section_id: s for s in instance.sections}

    for ts in template_sections:
        instance_section = instance_section_map.get(ts.section_id)
        if instance_section is None:
            # Section declared in template but absent from instance
            mdb = (ts.missing_data_behavior or "").lower()
            if "default-empty" in mdb:
                # Default-empty is acceptable as missing
                sections_validated.append(SectionValidation(
                    section_id=ts.section_id,
                    populated=False,
                    body_length=0,
                    cadence_status="unknown",
                    notes="missing (default-empty acceptable)",
                ))
            else:
                missing_sections.append(ts.section_id)
                sections_validated.append(SectionValidation(
                    section_id=ts.section_id,
                    populated=False,
                    body_length=0,
                    cadence_status="unknown",
                    notes="missing from instance",
                ))
            continue

        body = instance_section.raw_body or ""
        cleaned = _strip_placeholders(body).strip()
        populated = bool(cleaned)
        sections_validated.append(SectionValidation(
            section_id=ts.section_id,
            populated=populated,
            body_length=len(cleaned),
            cadence_status="ok" if populated else "unknown",
            notes="populated" if populated else "empty (missing-data behavior: " + (ts.missing_data_behavior or "unspecified") + ")",
        ))

    # Determine overall status
    populated = sum(1 for s in sections_validated if s.populated)
    total = len(sections_validated)
    if missing_sections:
        overall = "FAIL"
    elif populated == total:
        overall = "PASS"
    elif populated == 0:
        overall = "FAIL"
    else:
        overall = "PARTIAL"

    result = ValidateResult(
        success=(overall == "PASS"),
        instance_path=instance_path,
        overall_status=overall,
        sections=sections_validated,
        missing_sections=missing_sections,
    )

    # Emit CorpusValidated event
    try:
        from oversight_events import emit
        emit({
            "event_type": "CorpusValidated",
            "workflow_id": workflow_id or "",
            "project_nexus": project_nexus or "",
            "corpus_instance_path": instance_path,
            "validation_result": overall,
            "missing_sections": list(missing_sections),
            "stale_sections": [],  # cadence-based staleness deferred
            "consistency_violations": [],
        })
    except Exception:
        pass

    return result


def _strip_placeholders(text: str) -> str:
    """Remove HTML comments and meta-info lines; what remains is real content."""
    out = text
    for pat in _PLACEHOLDER_PATTERNS:
        out = pat.sub("", out)
    return out


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- CLI ----------

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python corpus_runtime.py instance <template-path> <period> <instance-dir>")
        print("  python corpus_runtime.py validate <instance-path> [<template-path>]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "instance":
        if len(sys.argv) < 5:
            print("Usage: python corpus_runtime.py instance <template-path> <period> <instance-dir>")
            sys.exit(1)
        result = c_instance(sys.argv[2], sys.argv[3], sys.argv[4])
        if result.success:
            print(f"OK: created instance at {result.instance_path}")
            print(f"Sections: {', '.join(result.sections_created)}")
        else:
            print(f"FAIL: {result.error}")
            sys.exit(2)

    elif cmd == "validate":
        if len(sys.argv) < 3:
            print("Usage: python corpus_runtime.py validate <instance-path> [<template-path>]")
            sys.exit(1)
        template = sys.argv[3] if len(sys.argv) >= 4 else None
        result = c_validate(sys.argv[2], template_path=template)
        print(f"Overall: {result.overall_status} ({result.populated_count}/{result.total_count} populated)")
        for s in result.sections:
            mark = "✓" if s.populated else "✗"
            print(f"  {mark} {s.section_id}: {s.notes}")
        if result.missing_sections:
            print(f"Missing: {result.missing_sections}")
        if result.error:
            print(f"Error: {result.error}")
            sys.exit(2)
        sys.exit(0 if result.success else 1)

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
