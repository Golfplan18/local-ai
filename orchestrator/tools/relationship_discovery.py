"""
relationship_discovery.py — Pass 1 Relationship Discovery

Scans a vault note for explicit references to other notes (wikilinks, named mentions)
and classifies each reference into a typed relationship from the 13-type taxonomy.

Pass 1 runs at the end of the pipeline on each new or modified note.
All discovered relationships are assigned confidence: high (explicit textual reference).

Usage:
    from orchestrator.tools.relationship_discovery import discover_relationships
    relationships = discover_relationships(note_path, vault_path)
"""

from __future__ import annotations

import os
import re
import yaml
from pathlib import Path


# The 13 relationship types
RELATIONSHIP_TYPES = [
    "supports", "contradicts", "qualifies", "extends", "supersedes",
    "analogous-to", "derived-from", "enables", "requires", "produces",
    "precedes", "parent", "child"
]

# Signal phrases that suggest specific relationship types
# These are scanned in the surrounding context of each wikilink
TYPE_SIGNALS = {
    "supports": [
        r"supports?\b", r"evidence for", r"confirms?", r"demonstrates?",
        r"backs up", r"validates?", r"corroborates?"
    ],
    "contradicts": [
        r"contradicts?", r"conflicts? with", r"incompatible with",
        r"opposes?", r"refutes?", r"disproves?"
    ],
    "qualifies": [
        r"qualifies?", r"except when", r"but only", r"with the caveat",
        r"limits?", r"boundary", r"exception"
    ],
    "extends": [
        r"extends?", r"builds? on", r"expands?", r"elaborates? on",
        r"takes? further", r"deepens?"
    ],
    "supersedes": [
        r"supersedes?", r"replaces?", r"obsoletes?", r"updates?",
        r"newer version", r"revised"
    ],
    "analogous-to": [
        r"analogous to", r"similar to", r"like\b", r"parallels?",
        r"maps? to", r"corresponds? to", r"mirrors?"
    ],
    "derived-from": [
        r"derived from", r"extracted from", r"based on",
        r"originated from", r"sourced from", r"comes? from"
    ],
    "enables": [
        r"enables?", r"makes? possible", r"allows?",
        r"facilitates?", r"creates? the conditions"
    ],
    "requires": [
        r"requires?", r"depends? on", r"needs?",
        r"prerequisite", r"necessary for", r"cannot work without"
    ],
    "produces": [
        r"produces?", r"generates?", r"creates?",
        r"outputs?", r"results? in", r"yields?"
    ],
    "precedes": [
        r"precedes?", r"comes? before", r"must happen before",
        r"prior to", r"leads? to", r"followed by"
    ],
    "parent": [
        r"contains?", r"encompasses?", r"includes?",
        r"is the parent", r"governs?"
    ],
    "child": [
        r"is part of", r"belongs? to", r"is contained in",
        r"is a component of", r"falls? under"
    ]
}


def parse_yaml_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}
    end = content.find("---", 3)
    if end == -1:
        return {}
    try:
        return yaml.safe_load(content[3:end]) or {}
    except yaml.YAMLError:
        return {}


def extract_wikilinks(content: str) -> list[dict]:
    """
    Extract all wikilinks from markdown content with their surrounding context.
    Returns list of {target, alias, context, line_num}
    """
    links = []
    # Strip YAML frontmatter before scanning
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            body = content[end + 3:]
        else:
            body = content
    else:
        body = content

    # Match [[target]] and [[target|alias]]
    pattern = re.compile(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]')

    for line_num, line in enumerate(body.split("\n"), 1):
        for match in pattern.finditer(line):
            target = match.group(1).strip()
            alias = match.group(2).strip() if match.group(2) else None

            # Get surrounding context (the full line, or window around the link)
            context = line.strip()

            links.append({
                "target": target,
                "alias": alias,
                "context": context,
                "line_num": line_num
            })

    return links


def classify_relationship(context: str, source_fm: dict, target_name: str) -> str:
    """
    Classify the relationship type based on the surrounding context of a wikilink.
    Returns the most likely relationship type from the 13-type taxonomy.
    Falls back to 'supports' as the most common general relationship.
    """
    context_lower = context.lower()

    # Check signal phrases for each type
    scores = {}
    for rtype, patterns in TYPE_SIGNALS.items():
        score = 0
        for pattern in patterns:
            if re.search(pattern, context_lower):
                score += 1
        if score > 0:
            scores[rtype] = score

    if scores:
        # Return the type with the highest signal match count
        return max(scores, key=scores.get)

    # Structural signals from note metadata
    source_type = source_fm.get("type", "")
    source_tags = source_fm.get("tags", []) or []

    # If source is a compound note linking to extracted principles → parent
    if "compound" in source_tags and ("extracted" in context_lower or "principle" in context_lower):
        return "parent"

    # If context mentions "source document" → derived-from
    if "source document" in context_lower:
        return "derived-from"

    # If source is an MOC/matrix → parent
    if source_type == "matrix":
        return "parent"

    # Default: supports (most common relationship in knowledge graphs)
    return "supports"


def get_vault_note_titles(vault_path: str) -> set[str]:
    """Get all note titles (filenames without .md) in the vault."""
    titles = set()
    for root, dirs, files in os.walk(vault_path):
        # Skip hidden directories and known non-content directories
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "Old AI Working Files"]
        for f in files:
            if f.endswith(".md"):
                titles.add(f[:-3])  # Remove .md extension
    return titles


def discover_relationships(note_path: str, vault_path: str = None) -> list[dict]:
    """
    Discover typed relationships in a vault note.

    Args:
        note_path: Absolute path to the note file
        vault_path: Absolute path to the vault root directory.
                    If None, uses ~/Documents/vault/

    Returns:
        List of relationship dicts: {type, target, confidence}
    """
    if vault_path is None:
        vault_path = os.path.expanduser("~/Documents/vault")

    with open(note_path, "r") as f:
        content = f.read()

    # Parse source note's frontmatter
    source_fm = parse_yaml_frontmatter(content)

    # Get all valid vault note titles for validation
    valid_titles = get_vault_note_titles(vault_path)

    # Extract wikilinks
    links = extract_wikilinks(content)

    # Classify each link
    relationships = []
    seen_targets = {}  # track {(type, target)} to avoid duplicates

    for link in links:
        target = link["target"]

        # Skip self-references
        source_title = Path(note_path).stem
        if target == source_title:
            continue

        # Validate target exists in vault
        if target not in valid_titles:
            continue

        # Classify the relationship
        rtype = classify_relationship(link["context"], source_fm, target)

        # Deduplicate: one relationship per (type, target) pair
        key = (rtype, target)
        if key in seen_targets:
            continue
        seen_targets[key] = True

        relationships.append({
            "type": rtype,
            "target": target,
            "confidence": "high"  # Pass 1 = explicit textual reference
        })

    return relationships


def update_note_relationships(note_path: str, relationships: list[dict]) -> bool:
    """
    Write discovered relationships into a note's YAML frontmatter.
    Merges with existing relationships (does not overwrite).

    Returns True if the file was modified, False otherwise.
    """
    with open(note_path, "r") as f:
        content = f.read()

    fm = parse_yaml_frontmatter(content)

    # Get existing relationships
    existing = fm.get("relationships", []) or []
    existing_keys = {(r["type"], r["target"]) for r in existing if isinstance(r, dict)}

    # Find new relationships to add
    new_rels = []
    for rel in relationships:
        key = (rel["type"], rel["target"])
        if key not in existing_keys:
            new_rels.append(rel)

    if not new_rels:
        return False

    # Merge
    merged = existing + new_rels
    fm["relationships"] = merged

    # Reconstruct the file with updated frontmatter
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            body = content[end + 3:]
        else:
            body = content
    else:
        body = content

    # Build YAML frontmatter
    yaml_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False)
    new_content = f"---\n{yaml_str}---{body}"

    with open(note_path, "w") as f:
        f.write(new_content)

    return True


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: relationship_discovery.py <note_path> [vault_path]")
        print("  Discovers typed relationships in a vault note.")
        print("  --write: Also update the note's YAML frontmatter with discoveries.")
        sys.exit(1)

    write_mode = "--write" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--write"]

    note_path = os.path.abspath(args[0])
    vault_path = os.path.abspath(args[1]) if len(args) > 1 else None

    if not os.path.isfile(note_path):
        print(f"Error: {note_path} not found")
        sys.exit(1)

    relationships = discover_relationships(note_path, vault_path)

    if relationships:
        print(f"Discovered {len(relationships)} relationships:")
        for rel in relationships:
            print(f"  {rel['type']} → \"{rel['target']}\" (confidence: {rel['confidence']})")

        if write_mode:
            modified = update_note_relationships(note_path, relationships)
            if modified:
                print(f"\nUpdated {note_path}")
            else:
                print(f"\nNo new relationships to add (all already present)")
    else:
        print("No relationships discovered.")
