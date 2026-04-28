"""
relationship_traversal.py — Relationship-Aware RAG Context Assembly

Extends the standard ChromaDB vector search with relationship graph traversal.
When assembling context for a query, this module:
1. Takes the initial ChromaDB results
2. Traverses the relationship graph to find connected notes
3. Filters by the active mode's relationship priority types
4. Returns an enriched context set ordered by relevance

Usage:
    from orchestrator.tools.relationship_traversal import enrich_with_relationships
    enriched = enrich_with_relationships(
        initial_results=chromadb_results,
        mode_priorities=["supports", "extends", "enables"],
        max_additions=5
    )
"""

from __future__ import annotations

import os
import yaml
from pathlib import Path

from orchestrator.tools.relationship_graph import RelationshipGraph


def parse_mode_relationship_priorities(mode_content: str) -> dict:
    """
    Extract relationship priority and depriority lists from a mode file's
    RAG PROFILE — RELATIONSHIP PRIORITIES section.

    Returns: {priority: [types], depriority: [types]}
    """
    priorities = {"priority": [], "depriority": []}

    # Find the RELATIONSHIP PRIORITIES section
    section_start = mode_content.find("### RAG PROFILE — RELATIONSHIP PRIORITIES")
    if section_start == -1:
        return priorities

    section = mode_content[section_start:]
    # Find the next ### or ## heading to bound the section
    next_heading = -1
    for pattern in ["### RAG PROFILE —", "## "]:
        idx = section.find(pattern, len("### RAG PROFILE — RELATIONSHIP PRIORITIES"))
        if idx != -1 and (next_heading == -1 or idx < next_heading):
            next_heading = idx
    if next_heading != -1:
        section = section[:next_heading]

    # Extract prioritize line
    import re
    pri_match = re.search(r'\*\*Prioritize:\*\*\s*(.+)', section)
    if pri_match:
        types_str = pri_match.group(1)
        priorities["priority"] = re.findall(r'`([^`]+)`', types_str)

    # Extract deprioritize line
    dep_match = re.search(r'\*\*Deprioritize:\*\*\s*(.+)', section)
    if dep_match:
        types_str = dep_match.group(1)
        priorities["depriority"] = re.findall(r'`([^`]+)`', types_str)

    return priorities


def read_note_content(title: str, vault_path: str = None) -> str | None:
    """Read a vault note's content by title. Returns None if not found."""
    if vault_path is None:
        vault_path = os.path.expanduser("~/Documents/vault")

    # Search for the file
    for root, dirs, files in os.walk(vault_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")
                   and d != "Old AI Working Files"]
        for f in files:
            if f == f"{title}.md":
                with open(os.path.join(root, f), "r") as fh:
                    return fh.read()
    return None


def score_relationship(rel: dict, mode_priorities: list[str],
                       mode_depriorities: list[str]) -> float:
    """
    Score a relationship for RAG relevance based on mode priorities.

    Scoring:
    - Priority type: base 1.0
    - Non-priority, non-depriority: base 0.5
    - Depriority type: base 0.1
    - Confidence multiplier: high=1.0, medium=0.7, low=0.3
    """
    rtype = rel.get("type", rel.get("original_type", ""))
    confidence = rel.get("confidence", "medium")

    # Base score from priority
    if rtype in mode_priorities:
        base = 1.0
    elif rtype in mode_depriorities:
        base = 0.1
    else:
        base = 0.5

    # Confidence multiplier
    conf_mult = {"high": 1.0, "medium": 0.7, "low": 0.3}.get(confidence, 0.5)

    return base * conf_mult


def enrich_with_relationships(
    initial_results: list[dict],
    mode_file_content: str = None,
    mode_priorities: list[str] = None,
    mode_depriorities: list[str] = None,
    max_additions: int = 5,
    max_depth: int = 1,
    vault_path: str = None
) -> list[dict]:
    """
    Enrich ChromaDB search results with relationship-connected notes.

    Args:
        initial_results: List of dicts from ChromaDB search, each containing
                        at minimum a 'source' or 'title' key.
        mode_file_content: Full text of the active mode file. Used to extract
                          relationship priorities. Mutually exclusive with
                          mode_priorities/mode_depriorities.
        mode_priorities: Explicit list of prioritized relationship types.
        mode_depriorities: Explicit list of deprioritized relationship types.
        max_additions: Maximum number of relationship-sourced notes to add.
        max_depth: How many hops to traverse (default 1 = direct connections only).
        vault_path: Path to vault root.

    Returns:
        List of dicts representing notes to add to context, each containing:
        {title, content, source_type, relationship_path, score}
    """
    if vault_path is None:
        vault_path = os.path.expanduser("~/Documents/vault")

    # Extract priorities from mode file if provided
    if mode_file_content and not mode_priorities:
        parsed = parse_mode_relationship_priorities(mode_file_content)
        mode_priorities = parsed["priority"]
        mode_depriorities = parsed["depriority"]

    if not mode_priorities:
        mode_priorities = []
    if not mode_depriorities:
        mode_depriorities = []

    # Get titles from initial results
    initial_titles = set()
    for result in initial_results:
        title = result.get("source", result.get("title", ""))
        if title:
            # Strip .md extension if present
            if title.endswith(".md"):
                title = title[:-3]
            initial_titles.add(title)

    if not initial_titles:
        return []

    # Open graph
    graph = RelationshipGraph(vault_path=vault_path)

    # Traverse relationships from each initial result
    candidates = {}  # title → {score, relationship_path}

    for title in initial_titles:
        connected = graph.get_connected(title, depth=max_depth,
                                         types=mode_priorities if mode_priorities else None)
        for conn in connected:
            note_title = conn["note"]

            # Skip notes already in initial results
            if note_title in initial_titles:
                continue

            # Score this candidate
            score = score_relationship(conn, mode_priorities, mode_depriorities)

            # Track the best path to each candidate
            if note_title not in candidates or score > candidates[note_title]["score"]:
                candidates[note_title] = {
                    "score": score,
                    "relationship_path": f"{title} → {conn['relationship']} → {note_title}",
                    "confidence": conn["confidence"],
                    "depth": conn["depth"]
                }

    graph.close()

    # Sort candidates by score, take top N
    sorted_candidates = sorted(
        candidates.items(),
        key=lambda x: x[1]["score"],
        reverse=True
    )[:max_additions]

    # Read content for top candidates
    enriched = []
    for title, meta in sorted_candidates:
        content = read_note_content(title, vault_path)
        if content:
            enriched.append({
                "title": title,
                "content": content,
                "source_type": "relationship_traversal",
                "relationship_path": meta["relationship_path"],
                "score": meta["score"],
                "confidence": meta["confidence"],
                "depth": meta["depth"]
            })

    return enriched


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 3:
        print("Usage: relationship_traversal.py <note_title> <mode_file>")
        print("  Simulates relationship enrichment from a starting note.")
        sys.exit(1)

    note_title = sys.argv[1]
    mode_file = sys.argv[2]

    # Read mode file
    with open(mode_file, "r") as f:
        mode_content = f.read()

    # Simulate initial results (just the one note)
    initial = [{"source": note_title}]

    enriched = enrich_with_relationships(
        initial_results=initial,
        mode_file_content=mode_content,
        max_additions=10,
        max_depth=2
    )

    if enriched:
        print(f"Found {len(enriched)} related notes:")
        for e in enriched:
            print(f"  [{e['score']:.2f}] {e['title']}")
            print(f"         Path: {e['relationship_path']}")
            print(f"         Confidence: {e['confidence']}, Depth: {e['depth']}")
    else:
        print("No related notes found via relationship traversal.")
