"""Corpus parser — parses corpus templates and corpus instances.

Corpus templates and instances are markdown files produced by Framework — Corpus
Formalization (CFF). The template defines the section architecture (per-section
schema, cadence, missing-data behavior, cross-section rules, chain
relationships); the instance is a populated copy for a specific reporting
period.

Both forms share most of their structure; the parser produces a unified
ParsedCorpus record with `is_template: bool` distinguishing them.

Section-level oversight rules (added by Framework — Oversight Configuration
OS-Setup) are extracted from each section's `oversight:` sub-block per
Reference — Meta-Layer Architecture §11.

Author: meta-layer implementation per Reference — Meta-Layer Architecture §13.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None


# ---------- Data classes ----------

@dataclass
class CorpusSectionOversight:
    schema: str = ""
    cadence: str = ""
    cross_section_rules: list = field(default_factory=list)
    triggers_active: list = field(default_factory=list)


@dataclass
class CorpusSection:
    section_id: str
    name: str = ""
    source_pff: str = ""  # writer framework id
    missing_data_behavior: str = ""
    raw_yaml: str = ""
    raw_body: str = ""
    oversight: Optional[CorpusSectionOversight] = None
    fields: dict = field(default_factory=dict)


@dataclass
class ChainRelationship:
    direction: str  # "input" or "output"
    other_corpus: str
    sections_involved: list = field(default_factory=list)


@dataclass
class ParsedCorpus:
    file_path: str
    is_template: bool  # True for template, False for instance
    frontmatter: dict = field(default_factory=dict)
    title: str = ""
    template_version: str = ""
    instance_period: str = ""
    sections: list = field(default_factory=list)  # list[CorpusSection]
    chain_relationships: list = field(default_factory=list)


# ---------- Public API ----------

def parse_corpus_file(path: str) -> ParsedCorpus:
    """Parse a corpus template or instance from a markdown file."""
    with open(path, encoding="utf-8") as f:
        content = f.read()
    return parse_corpus_text(content, file_path=path)


def parse_corpus_text(content: str, file_path: str = "") -> ParsedCorpus:
    """Parse corpus content from a string."""
    fm, body = _split_frontmatter(content)
    parsed = ParsedCorpus(file_path=file_path, is_template=True)

    if fm and yaml is not None:
        try:
            parsed.frontmatter = yaml.safe_load(fm) or {}
        except yaml.YAMLError:
            parsed.frontmatter = {}

    # Determine template vs instance from frontmatter
    fm_type = parsed.frontmatter.get("type", "").lower()
    if "instance" in fm_type:
        parsed.is_template = False
    parsed.template_version = parsed.frontmatter.get("template_version", "")
    parsed.instance_period = parsed.frontmatter.get("period", "")

    # Title
    title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    if title_match:
        parsed.title = title_match.group(1).strip()

    # Look for a sections block in YAML form (preferred for templates)
    parsed.sections = _parse_sections_yaml(body) or _parse_sections_markdown(body)

    # Chain relationships
    parsed.chain_relationships = _parse_chain_relationships(body)

    return parsed


# ---------- Frontmatter splitting ----------

_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _split_frontmatter(content: str) -> tuple[str, str]:
    m = _FRONTMATTER_PATTERN.match(content)
    if not m:
        return ("", content)
    return (m.group(1), content[m.end():])


# ---------- Sections parsing — YAML form ----------

def _parse_sections_yaml(body: str) -> list[CorpusSection]:
    """Extract sections from a YAML block tagged ```yaml under ## Sections.

    Recognizes templates that declare:
        sections:
          - id: weekly_sales
            name: Weekly Sales
            source: pff-mortgage-pipeline
            ...
            oversight:
              schema: |
                Required columns: ...
              cadence: weekly
              cross_section_rules: [...]
              triggers_active: [...]
    """
    if yaml is None:
        return []

    sections: list[CorpusSection] = []
    yaml_blocks = re.findall(r"```yaml\s*\n(.*?)\n```", body, re.DOTALL)
    for block in yaml_blocks:
        try:
            data = yaml.safe_load(block)
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict):
            continue
        section_list = data.get("sections")
        if not isinstance(section_list, list):
            continue
        for s in section_list:
            if not isinstance(s, dict):
                continue
            section = CorpusSection(
                section_id=str(s.get("id", "")),
                name=str(s.get("name", "")),
                source_pff=str(s.get("source", "")),
                missing_data_behavior=str(s.get("missing_data_behavior", "")),
            )
            oversight_data = s.get("oversight")
            if isinstance(oversight_data, dict):
                section.oversight = CorpusSectionOversight(
                    schema=str(oversight_data.get("schema", "")),
                    cadence=str(oversight_data.get("cadence", "")),
                    cross_section_rules=list(oversight_data.get("cross_section_rules", []) or []),
                    triggers_active=list(oversight_data.get("triggers_active", []) or []),
                )
            # Extra fields preserved in `fields`
            for k, v in s.items():
                if k not in ("id", "name", "source", "missing_data_behavior", "oversight"):
                    section.fields[k] = v
            sections.append(section)
        if sections:
            break  # use first valid sections block

    return sections


# ---------- Sections parsing — markdown form ----------

# Match `### Section <id> — <name>` (preferred) or `### <name>` (fallback).
# Group 1: optional explicit id; Group 2: section name.
_MD_SECTION_HEADER = re.compile(
    r"^###\s+(?:Section\s+([\w\-]+)\s*[—:-]\s*)?(.+?)\s*$",
    re.IGNORECASE,
)


def _parse_sections_markdown(body: str) -> list[CorpusSection]:
    """Fallback: parse sections declared as `### Section Name` blocks under
    a `## Sections` parent header.
    """
    sections: list[CorpusSection] = []

    # Find the Sections H2 first
    sections_block_match = re.search(
        r"^##\s+Sections\s*\n(.+?)(?=^##\s+|\Z)",
        body, re.MULTILINE | re.DOTALL,
    )
    if not sections_block_match:
        return sections
    sections_text = sections_block_match.group(1)

    # Split into ### blocks
    current: Optional[CorpusSection] = None
    current_body: list[str] = []
    for line in sections_text.split("\n"):
        m = _MD_SECTION_HEADER.match(line)
        if m:
            if current is not None:
                current.raw_body = "\n".join(current_body).strip()
                sections.append(current)
            explicit_id = m.group(1)
            section_name = m.group(2).strip()
            if explicit_id:
                section_id = explicit_id.lower()
            else:
                section_id = re.sub(r"[^a-z0-9]+", "_", section_name.lower()).strip("_")
            current = CorpusSection(section_id=section_id, name=section_name)
            current_body = []
        elif current is not None:
            current_body.append(line)
            # Look for inline source/cadence declarations
            stripped = line.strip()
            src_match = re.match(r"^\*\*?Source(?:\s+PFF)?:?\*?\*?\s*(.+)$", stripped, re.IGNORECASE)
            if src_match:
                # Strip backticks if present
                current.source_pff = src_match.group(1).strip().strip("`")
            mdb_match = re.match(
                r"^\*\*?Missing[\s-]Data Behavior:?\*?\*?\s*(.+)$", stripped, re.IGNORECASE,
            )
            if mdb_match:
                current.missing_data_behavior = mdb_match.group(1).strip()

    if current is not None:
        current.raw_body = "\n".join(current_body).strip()
        sections.append(current)

    return sections


# ---------- Chain relationships parsing ----------

def _parse_chain_relationships(body: str) -> list[ChainRelationship]:
    """Look for a chain_relationships block in YAML form."""
    if yaml is None:
        return []

    relationships: list[ChainRelationship] = []
    yaml_blocks = re.findall(r"```yaml\s*\n(.*?)\n```", body, re.DOTALL)
    for block in yaml_blocks:
        try:
            data = yaml.safe_load(block)
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict):
            continue
        chain_list = data.get("chain_relationships")
        if not isinstance(chain_list, list):
            continue
        for c in chain_list:
            if not isinstance(c, dict):
                continue
            relationships.append(ChainRelationship(
                direction=str(c.get("direction", "")),
                other_corpus=str(c.get("other_corpus", "")),
                sections_involved=list(c.get("sections_involved", []) or []),
            ))
        if relationships:
            break
    return relationships


# ---------- Diff helpers (used by corpus_watcher) ----------

def section_state_summary(parsed: ParsedCorpus) -> dict[str, dict]:
    """Return a per-section state summary suitable for diffing across snapshots.

    Each section maps to a dict with keys: source_pff, body_hash, body_length.
    The watcher uses body_hash to detect content changes without storing full
    section text.
    """
    import hashlib
    out: dict[str, dict] = {}
    for s in parsed.sections:
        body = s.raw_body or s.name  # fall back to name if no body
        out[s.section_id] = {
            "source_pff": s.source_pff,
            "body_hash": hashlib.sha256(body.encode("utf-8")).hexdigest()[:16],
            "body_length": len(body),
        }
    return out


# ---------- CLI smoke test ----------

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python corpus_parser.py <path-to-corpus-file>")
        sys.exit(1)
    parsed = parse_corpus_file(sys.argv[1])
    print(f"Title: {parsed.title}")
    print(f"Type: {'template' if parsed.is_template else 'instance'}")
    print(f"Sections: {len(parsed.sections)}")
    for s in parsed.sections:
        print(f"  - {s.section_id}: {s.name} (source={s.source_pff})")
        if s.oversight:
            print(f"    cadence={s.oversight.cadence}, schema={s.oversight.schema[:60]}...")
    print(f"Chain relationships: {len(parsed.chain_relationships)}")
    for c in parsed.chain_relationships:
        print(f"  - {c.direction}: {c.other_corpus}")
