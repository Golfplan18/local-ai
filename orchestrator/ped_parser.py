"""PED parser — parses Problem Evolution Document markdown into structured fields.

A PED is a markdown file produced and maintained by Framework — Problem Evolution.
This parser extracts the sections the meta-layer oversight apparatus needs:
Mission, Excluded Outcomes, Constraints, Objectives, Active Milestones,
Aspirational Milestones, Decision Log, Oversight Specification.

The parser is forgiving — sections that are absent return empty rather than
raising. The PED format is markdown and humans edit it; the parser handles
reasonable variation.

Author: meta-layer implementation per Reference — Meta-Layer Architecture §13.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None  # parser still works for everything except YAML frontmatter


# ---------- Data classes ----------

@dataclass
class Constraint:
    classification: str  # "Hard", "Soft", "Working Assumption"
    statement: str
    rationale: str = ""  # cost/why-violation-unacceptable/revisit-trigger
    revisit_trigger: str = ""  # only for Working Assumption

@dataclass
class Milestone:
    raw_text: str
    is_complete: bool  # checkbox state
    statement: str  # text after the checkbox
    milestone_id: Optional[str] = None  # if explicitly labeled
    fields: dict = field(default_factory=dict)  # additional fields like Verification Criterion, P-Feasibility Verdict

@dataclass
class DecisionLogEntry:
    raw_text: str
    date: str = ""
    summary: str = ""

@dataclass
class OversightSpecification:
    triggers_active: list = field(default_factory=list)
    framework_chain: list = field(default_factory=list)
    per_milestone_criteria: str = "use_declared"
    revisit_triggers: list = field(default_factory=list)
    escalation_contact: str = "user"
    workflow_references: list = field(default_factory=list)
    raw_yaml: str = ""  # the unparsed YAML block

@dataclass
class ParsedPED:
    file_path: str
    frontmatter: dict = field(default_factory=dict)
    title: str = ""
    problem_definition: str = ""
    mission_resolution_statement: str = ""
    mission_core_essence: str = ""
    mission_emotional_drivers: list = field(default_factory=list)
    excluded_outcomes: list = field(default_factory=list)
    constraints: list = field(default_factory=list)  # list[Constraint]
    objectives: list = field(default_factory=list)
    active_milestones: list = field(default_factory=list)  # list[Milestone]
    aspirational_milestones: list = field(default_factory=list)  # list[Milestone]
    terrain_maps: list = field(default_factory=list)
    decision_log: list = field(default_factory=list)  # list[DecisionLogEntry]
    iteration_history: list = field(default_factory=list)
    oversight_specification: Optional[OversightSpecification] = None
    raw_sections: dict = field(default_factory=dict)  # section name -> raw text


# ---------- Public API ----------

def parse_ped_file(path: str) -> ParsedPED:
    """Parse a PED file at the given path."""
    with open(path, encoding="utf-8") as f:
        content = f.read()
    return parse_ped_text(content, file_path=path)


def parse_ped_text(content: str, file_path: str = "") -> ParsedPED:
    """Parse PED content from a string."""
    ped = ParsedPED(file_path=file_path)

    # Frontmatter
    fm, body = _split_frontmatter(content)
    if fm and yaml is not None:
        try:
            ped.frontmatter = yaml.safe_load(fm) or {}
        except yaml.YAMLError:
            ped.frontmatter = {}

    # Title (H1)
    title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    if title_match:
        ped.title = title_match.group(1).strip()

    # Split into ## sections
    sections = _split_sections(body)
    ped.raw_sections = sections

    # Extract sections by name (case-insensitive, trimmed)
    for section_name, section_text in sections.items():
        name_lower = section_name.lower().strip()

        if "problem definition" in name_lower or "problem statement" in name_lower:
            ped.problem_definition = section_text.strip()

        elif name_lower == "mission":
            _parse_mission(section_text, ped)

        elif "excluded outcomes" in name_lower:
            ped.excluded_outcomes = _parse_bullet_list(section_text)

        elif name_lower == "constraints":
            ped.constraints = _parse_constraints(section_text)

        elif name_lower == "objectives":
            ped.objectives = _parse_bullet_list(section_text)

        elif "active milestones" in name_lower:
            ped.active_milestones = _parse_milestones(section_text)

        elif "aspirational milestones" in name_lower:
            ped.aspirational_milestones = _parse_milestones(section_text)

        elif name_lower == "milestones":
            # Combined milestones section — parse as active by default
            ped.active_milestones = _parse_milestones(section_text)

        elif "terrain map" in name_lower:
            ped.terrain_maps = _parse_bullet_list(section_text)

        elif "decision log" in name_lower:
            ped.decision_log = _parse_decision_log(section_text)

        elif "iteration" in name_lower and "history" in name_lower:
            ped.iteration_history = _parse_iteration_history(section_text)

        elif "oversight specification" in name_lower:
            ped.oversight_specification = _parse_oversight_spec(section_text)

    return ped


# ---------- Section splitting ----------

_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _split_frontmatter(content: str) -> tuple[str, str]:
    """Return (frontmatter_text, body_text). Empty frontmatter if absent."""
    m = _FRONTMATTER_PATTERN.match(content)
    if not m:
        return ("", content)
    return (m.group(1), content[m.end():])


def _split_sections(body: str) -> dict[str, str]:
    """Split body into a dict of {section_name: section_text} by ## headers.

    The text under H1 (before any ## header) is stored under the empty-string key.
    Subsections (### or deeper) stay inside their parent section.
    """
    sections: dict[str, str] = {}
    current_name = ""
    current_lines: list[str] = []

    for line in body.split("\n"):
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match and not line.startswith("###"):
            # Save the previous section
            if current_lines:
                sections[current_name] = "\n".join(current_lines).strip()
            current_name = match.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)

    # Save the last section
    if current_lines:
        sections[current_name] = "\n".join(current_lines).strip()

    return sections


# ---------- Mission parsing ----------

def _parse_mission(text: str, ped: ParsedPED):
    """Extract Resolution Statement, Core Essence, Emotional Drivers."""
    # Look for **Resolution Statement:** patterns
    res_match = re.search(
        r"\*\*Resolution Statement:?\*\*\s*[:.]?\s*(.+?)(?=\n\s*[-*]\s*\*\*|\n\n|\Z)",
        text, re.DOTALL | re.IGNORECASE,
    )
    if res_match:
        ped.mission_resolution_statement = res_match.group(1).strip()

    core_match = re.search(
        r"\*\*Core Essence(?:\s*\([^)]*\))?:?\*\*\s*[:.]?\s*(.+?)(?=\n\s*[-*]\s*\*\*|\n\n|\Z)",
        text, re.DOTALL | re.IGNORECASE,
    )
    if core_match:
        ped.mission_core_essence = core_match.group(1).strip()

    drivers_match = re.search(
        r"\*\*Emotional Drivers(?:\s*\([^)]*\))?:?\*\*\s*[:.]?\s*\n((?:\s*[-*]\s+.+\n?)+)",
        text, re.IGNORECASE,
    )
    if drivers_match:
        driver_lines = drivers_match.group(1)
        ped.mission_emotional_drivers = _parse_bullet_list(driver_lines)


# ---------- Bullet-list parsing ----------

_BULLET_LINE = re.compile(r"^\s*[-*]\s+(.+?)\s*$")


def _parse_bullet_list(text: str) -> list[str]:
    """Extract top-level bullet items from a markdown bullet list.

    Sub-bullets are concatenated into the parent. Empty items are skipped.
    """
    items: list[str] = []
    current: Optional[str] = None
    for line in text.split("\n"):
        m = _BULLET_LINE.match(line)
        if m and not line.startswith(("    -", "    *", "\t-", "\t*")):
            # Top-level bullet
            if current is not None:
                items.append(current.strip())
            current = m.group(1)
        elif current is not None and line.strip():
            # Continuation (sub-bullet, indented text)
            current += " " + line.strip().lstrip("-*").strip()
    if current is not None:
        items.append(current.strip())
    return [i for i in items if i]


# ---------- Constraints parsing ----------

_CONSTRAINT_HEADER = re.compile(
    r"^\s*[-*]\s+\*\*(Hard|Soft|Working Assumption)(?:\s*Constraint)?:?\*\*\s*(.+?)\s*$",
    re.IGNORECASE,
)


def _parse_constraints(text: str) -> list[Constraint]:
    """Parse the Constraints section. Recognizes Hard / Soft / Working Assumption."""
    constraints: list[Constraint] = []
    current: Optional[Constraint] = None
    for line in text.split("\n"):
        m = _CONSTRAINT_HEADER.match(line)
        if m:
            if current is not None:
                _finalize_constraint(current)
                constraints.append(current)
            classification = m.group(1).title()
            if classification.lower() == "working assumption":
                classification = "Working Assumption"
            current = Constraint(
                classification=classification,
                statement=m.group(2).strip(),
            )
        elif current is not None and line.strip():
            stripped = line.strip()
            # Look for revisit trigger inline
            if re.match(r"^revisit trigger:?\s*", stripped, re.IGNORECASE):
                current.revisit_trigger = re.sub(
                    r"^revisit trigger:?\s*", "", stripped, flags=re.IGNORECASE,
                )
            elif re.match(r"^cost(\s+of\s+violation)?:?\s*", stripped, re.IGNORECASE):
                current.rationale = stripped
            else:
                # Generic continuation — treat as rationale
                if current.rationale:
                    current.rationale += " " + stripped
                else:
                    current.rationale = stripped
    if current is not None:
        _finalize_constraint(current)
        constraints.append(current)
    return constraints


def _finalize_constraint(constraint: Constraint):
    """Pull inline revisit-trigger phrases out of the statement so they land
    in the dedicated field (handles forms like "... statement. Revisit trigger: foo").
    """
    if constraint.classification != "Working Assumption":
        return
    if constraint.revisit_trigger:
        return
    # Look for "Revisit trigger: X" or "Revisit when X" inside the statement
    m = re.search(
        r"(?:^|[.?!]\s+)(?:revisit\s+(?:trigger:?\s*|when\s+))(.+?)(?:[.?!]\s*$|$)",
        constraint.statement,
        re.IGNORECASE,
    )
    if m:
        constraint.revisit_trigger = m.group(1).strip()
        # Trim the trigger off the statement
        constraint.statement = re.sub(
            r"(?:^|[.?!]\s+)(?:revisit\s+(?:trigger:?\s*|when\s+))(.+?)(?:[.?!]\s*$|$)",
            ".",
            constraint.statement,
            flags=re.IGNORECASE,
        ).rstrip(". ").strip() + "."


# ---------- Milestones parsing ----------

_MILESTONE_LINE = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s+(.+?)\s*$")
_MILESTONE_BOLD_HEADER = re.compile(
    r"^\s*[-*]\s+\*\*Milestone\s+([A-Z]?\d+):\*\*\s+(.+?)\s*$",
    re.IGNORECASE,
)


def _parse_milestones(text: str) -> list[Milestone]:
    """Parse a milestones section. Recognizes both checkbox-style and
    Active/Aspirational structured-block style.
    """
    milestones: list[Milestone] = []
    current: Optional[Milestone] = None

    for line in text.split("\n"):
        cb_match = _MILESTONE_LINE.match(line)
        bold_match = _MILESTONE_BOLD_HEADER.match(line)

        if cb_match:
            if current is not None:
                milestones.append(current)
            checkbox_state = cb_match.group(1).strip().lower() == "x"
            statement = cb_match.group(2).strip()
            current = Milestone(
                raw_text=line.strip(),
                is_complete=checkbox_state,
                statement=statement,
            )
        elif bold_match:
            if current is not None:
                milestones.append(current)
            current = Milestone(
                raw_text=line.strip(),
                is_complete=False,  # bold-header milestones don't have checkboxes
                statement=bold_match.group(2).strip(),
                milestone_id=bold_match.group(1),
            )
        elif current is not None and line.strip().startswith("-"):
            # Sub-bullet — treat as a field if it matches `- Field name: value`
            stripped = line.strip().lstrip("-").strip()
            field_match = re.match(r"^([A-Z][A-Za-z\s\-]+):\s*(.+)$", stripped)
            if field_match:
                fname = field_match.group(1).strip()
                fvalue = field_match.group(2).strip()
                current.fields[fname] = fvalue

    if current is not None:
        milestones.append(current)
    return milestones


# ---------- Decision log parsing ----------

_DECISION_DATE = re.compile(r"^\s*[#\-*]+\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE)


def _parse_decision_log(text: str) -> list[DecisionLogEntry]:
    """Parse the Decision Log section. Each entry begins with a date or a bullet."""
    entries: list[DecisionLogEntry] = []
    current_lines: list[str] = []
    current_date = ""

    for line in text.split("\n"):
        date_match = _DECISION_DATE.match(line)
        if date_match:
            # Save previous entry
            if current_lines:
                entries.append(DecisionLogEntry(
                    raw_text="\n".join(current_lines).strip(),
                    date=current_date,
                    summary=current_lines[0].strip() if current_lines else "",
                ))
            current_date = date_match.group(1)
            current_lines = [line]
        elif line.strip():
            current_lines.append(line)

    if current_lines:
        entries.append(DecisionLogEntry(
            raw_text="\n".join(current_lines).strip(),
            date=current_date,
            summary=current_lines[0].strip() if current_lines else "",
        ))

    return entries


# ---------- Iteration history ----------

_ITERATION_HEADER = re.compile(r"^###?\s*Iteration\s+(\d+)", re.IGNORECASE)


def _parse_iteration_history(text: str) -> list[dict]:
    """Parse iteration history into a list of {iteration_number, raw_text} dicts."""
    iterations: list[dict] = []
    current: Optional[dict] = None
    for line in text.split("\n"):
        m = _ITERATION_HEADER.match(line)
        if m:
            if current is not None:
                iterations.append(current)
            current = {"iteration": int(m.group(1)), "raw_text": line + "\n"}
        elif current is not None:
            current["raw_text"] += line + "\n"
    if current is not None:
        iterations.append(current)
    return iterations


# ---------- Oversight Specification ----------

def _parse_oversight_spec(text: str) -> OversightSpecification:
    """Parse the Oversight Specification block. Format is YAML embedded in markdown."""
    spec = OversightSpecification()
    spec.raw_yaml = text

    # Look for a YAML code block
    yaml_block = re.search(r"```yaml\s*\n(.*?)\n```", text, re.DOTALL)
    if not yaml_block:
        # Try plain YAML without code fence
        # Strip markdown bullets/headers; assume the rest is YAML
        plain = re.sub(r"^[#\-*]\s*", "", text, flags=re.MULTILINE)
        yaml_text = plain
    else:
        yaml_text = yaml_block.group(1)

    if yaml is None:
        return spec

    try:
        parsed = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return spec

    if not isinstance(parsed, dict):
        return spec

    # Spec might be top-level or nested under "oversight_specification:"
    data = parsed.get("oversight_specification", parsed)
    if not isinstance(data, dict):
        data = parsed

    spec.triggers_active = data.get("triggers_active", []) or []
    spec.framework_chain = data.get("framework_chain", []) or []
    spec.per_milestone_criteria = data.get("per_milestone_criteria", "use_declared")
    spec.revisit_triggers = data.get("revisit_triggers", []) or []
    spec.escalation_contact = data.get("escalation_contact", "user")
    spec.workflow_references = data.get("workflow_references", []) or []

    return spec


# ---------- Active milestone helpers ----------

def get_active_milestone_states(ped: ParsedPED) -> list[tuple[str, bool]]:
    """Return [(milestone_statement, is_complete)] for active milestones.

    Used by ped_watcher to detect checkbox state changes between snapshots.
    """
    return [(m.statement, m.is_complete) for m in ped.active_milestones]


# ---------- CLI smoke test ----------

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python ped_parser.py <path-to-ped-file>")
        sys.exit(1)
    parsed = parse_ped_file(sys.argv[1])
    print(f"Title: {parsed.title}")
    print(f"Mission resolution: {parsed.mission_resolution_statement[:100]}...")
    print(f"Excluded outcomes: {len(parsed.excluded_outcomes)}")
    print(f"Constraints: {len(parsed.constraints)}")
    print(f"Active milestones: {len(parsed.active_milestones)}")
    for ms in parsed.active_milestones:
        check = "[x]" if ms.is_complete else "[ ]"
        print(f"  {check} {ms.statement[:80]}")
    print(f"Decision log entries: {len(parsed.decision_log)}")
    print(f"Oversight spec: {parsed.oversight_specification is not None}")
