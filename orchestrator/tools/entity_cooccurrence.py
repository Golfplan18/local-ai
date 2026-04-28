"""
entity_cooccurrence.py — Entity Co-Occurrence for Relationship Discovery (Phase 10, Step 10)

Lightweight NLP entity extraction providing a third relationship discovery signal
alongside explicit references (Phase 7 Pass 1) and semantic similarity (Phase 7 Pass 2).

When two notes share 2+ non-trivial named entities but lack explicit links or high
semantic similarity, they become relationship candidates at confidence: low.

Uses regex-based entity extraction (no spaCy dependency required, though spaCy can be
used when available for better precision).

Usage:
    from orchestrator.tools.entity_cooccurrence import EntityExtractor
    extractor = EntityExtractor()
    entities = extractor.extract(note_text)
    candidates = extractor.find_cooccurrences(notes_dict)
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Entity:
    """An extracted entity."""
    text: str
    entity_type: str  # "proper_noun", "technical_term", "concept"
    count: int = 1


@dataclass
class CooccurrenceCandidate:
    """A relationship candidate from entity co-occurrence."""
    source_title: str
    target_title: str
    shared_entities: list[str]
    confidence: str = "low"
    relationship_type: str = "supports"  # default; human review refines


class EntityExtractor:
    """
    Extracts named entities from note text using regex heuristics.

    For higher precision, can optionally use spaCy when available.
    """

    # Technical terms commonly found in knowledge management / AI context
    # These are patterns, not an exhaustive list
    TECHNICAL_PATTERNS = [
        r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b',  # Multi-word proper nouns
        r'\b[A-Z]{2,}[a-z]*\b',  # Acronyms (RAG, HCP, YAML, etc.)
        r'\b[a-z]+(?:_[a-z]+)+\b',  # snake_case terms (technical identifiers)
    ]

    # Common stop entities to exclude
    STOP_ENTITIES = {
        # Generic terms that appear everywhere
        "the", "this", "that", "note", "notes", "file", "files",
        "section", "system", "model", "user", "input", "output",
        "data", "text", "list", "type", "name", "value", "path",
        "step", "process", "result", "error", "example", "document",
        # Common markdown artifacts
        "true", "false", "null", "none", "yaml", "json", "markdown",
        # Months, days (not useful for co-occurrence)
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
        "monday", "tuesday", "wednesday", "thursday", "friday",
        "saturday", "sunday",
    }

    # Minimum entity length to consider
    MIN_ENTITY_LENGTH = 3

    # Minimum shared entities for a co-occurrence candidate
    MIN_SHARED = 2

    def __init__(self, use_spacy: bool = False):
        """
        Args:
            use_spacy: Try to use spaCy for extraction. Falls back to regex if unavailable.
        """
        self._spacy_nlp = None
        if use_spacy:
            try:
                import spacy
                self._spacy_nlp = spacy.load("en_core_web_sm")
            except (ImportError, OSError):
                pass  # Fall back to regex

    def extract(self, text: str) -> list[Entity]:
        """
        Extract named entities from text.

        Returns deduplicated list of Entity objects.
        """
        if self._spacy_nlp:
            return self._extract_spacy(text)
        return self._extract_regex(text)

    def _extract_regex(self, text: str) -> list[Entity]:
        """Regex-based entity extraction."""
        entities = defaultdict(lambda: {"count": 0, "type": ""})

        # Strip markdown formatting
        clean = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
        clean = re.sub(r'`[^`]+`', '', clean)
        clean = re.sub(r'\[\[([^\]]+)\]\]', r'\1', clean)  # Preserve wikilink text
        clean = re.sub(r'[#*_~>|]', ' ', clean)

        # Multi-word proper nouns (capitalized sequences)
        for match in re.finditer(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', clean):
            term = match.group(1)
            normalized = term.lower()
            if normalized not in self.STOP_ENTITIES and len(normalized) >= self.MIN_ENTITY_LENGTH:
                entities[normalized]["count"] += 1
                entities[normalized]["type"] = "proper_noun"

        # Acronyms (2+ uppercase letters)
        for match in re.finditer(r'\b([A-Z]{2,}[a-z]*)\b', clean):
            term = match.group(1)
            normalized = term.lower()
            if normalized not in self.STOP_ENTITIES and len(normalized) >= self.MIN_ENTITY_LENGTH:
                entities[normalized]["count"] += 1
                entities[normalized]["type"] = "technical_term"

        # Technical terms in quotes or backticks (from original text)
        for match in re.finditer(r'["`]([^"`]{3,50})["`]', text):
            term = match.group(1)
            normalized = term.lower().strip()
            if normalized not in self.STOP_ENTITIES:
                entities[normalized]["count"] += 1
                entities[normalized]["type"] = "concept"

        # Wikilink targets (important domain concepts)
        for match in re.finditer(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', text):
            term = match.group(1).strip()
            normalized = term.lower()
            if normalized not in self.STOP_ENTITIES:
                entities[normalized]["count"] += 1
                entities[normalized]["type"] = "concept"

        # Domain-specific compound terms (e.g., "context window", "knowledge graph")
        compound_patterns = [
            r'\b(context\s+window)\b', r'\b(knowledge\s+graph)\b',
            r'\b(vector\s+(?:store|database|search|embedding))\b',
            r'\b(language\s+model)\b', r'\b(neural\s+network)\b',
            r'\b(machine\s+learning)\b', r'\b(deep\s+learning)\b',
            r'\b(natural\s+language)\b', r'\b(attention\s+mechanism)\b',
            r'\b(token\s+(?:count|budget|limit|window))\b',
            r'\b(embedding\s+(?:model|space|similarity|vector))\b',
            r'\b(semantic\s+(?:search|similarity|chunking|extraction))\b',
            r'\b(quality\s+gate)\b', r'\b(relationship\s+(?:graph|type|taxonomy))\b',
            r'\b(atomic\s+note)\b', r'\b(molecular\s+note)\b',
            r'\b(compound\s+note)\b', r'\b(process\s+(?:note|principle))\b',
            r'\b(glossary\s+(?:note|entry))\b',
        ]
        for pattern in compound_patterns:
            for match in re.finditer(pattern, clean, re.IGNORECASE):
                term = match.group(1)
                normalized = term.lower()
                entities[normalized]["count"] += 1
                entities[normalized]["type"] = "technical_term"

        return [
            Entity(text=term, entity_type=info["type"], count=info["count"])
            for term, info in entities.items()
        ]

    def _extract_spacy(self, text: str) -> list[Entity]:
        """spaCy-based entity extraction (when available)."""
        # Strip markdown formatting
        clean = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
        clean = re.sub(r'`[^`]+`', '', clean)
        clean = re.sub(r'\[\[([^\]]+)\]\]', r'\1', clean)
        clean = re.sub(r'[#*_~>|]', ' ', clean)

        doc = self._spacy_nlp(clean[:100000])  # Limit to prevent memory issues

        entities = defaultdict(lambda: {"count": 0, "type": ""})

        for ent in doc.ents:
            normalized = ent.text.lower().strip()
            if (normalized not in self.STOP_ENTITIES
                    and len(normalized) >= self.MIN_ENTITY_LENGTH):
                entities[normalized]["count"] += 1
                entities[normalized]["type"] = ent.label_

        # Also extract noun chunks as concepts
        for chunk in doc.noun_chunks:
            normalized = chunk.text.lower().strip()
            if (len(normalized.split()) >= 2
                    and normalized not in self.STOP_ENTITIES
                    and len(normalized) >= self.MIN_ENTITY_LENGTH):
                entities[normalized]["count"] += 1
                if not entities[normalized]["type"]:
                    entities[normalized]["type"] = "concept"

        # Add wikilinks from original text
        for match in re.finditer(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', text):
            term = match.group(1).strip().lower()
            if term not in self.STOP_ENTITIES:
                entities[term]["count"] += 1
                if not entities[term]["type"]:
                    entities[term]["type"] = "concept"

        return [
            Entity(text=term, entity_type=info["type"], count=info["count"])
            for term, info in entities.items()
        ]

    def find_cooccurrences(self, notes: dict[str, str],
                           min_shared: int = None) -> list[CooccurrenceCandidate]:
        """
        Find entity co-occurrences across notes.

        Args:
            notes: dict of {note_title: note_text}
            min_shared: Minimum shared entities to be a candidate (default: 2)

        Returns:
            List of CooccurrenceCandidate objects.
        """
        if min_shared is None:
            min_shared = self.MIN_SHARED

        # Extract entities for each note
        note_entities: dict[str, set[str]] = {}
        for title, text in notes.items():
            extracted = self.extract(text)
            # Use only entities that appear at least once and aren't trivial
            entity_set = {e.text for e in extracted if e.count >= 1}
            note_entities[title] = entity_set

        # Find co-occurrences
        candidates = []
        titles = list(note_entities.keys())

        for i in range(len(titles)):
            for j in range(i + 1, len(titles)):
                title_a = titles[i]
                title_b = titles[j]
                shared = note_entities[title_a] & note_entities[title_b]

                if len(shared) >= min_shared:
                    candidates.append(CooccurrenceCandidate(
                        source_title=title_a,
                        target_title=title_b,
                        shared_entities=sorted(shared),
                        confidence="low",
                    ))

        # Sort by number of shared entities (most shared first)
        candidates.sort(key=lambda c: len(c.shared_entities), reverse=True)

        return candidates

    def find_cooccurrences_incremental(self, new_note_title: str, new_note_text: str,
                                        existing_entities: dict[str, set[str]],
                                        min_shared: int = None) -> list[CooccurrenceCandidate]:
        """
        Find co-occurrences between a new note and existing note entities.

        This is the incremental version — used when adding a single note
        rather than batch-processing the entire vault.

        Args:
            new_note_title: Title of the new note.
            new_note_text: Text of the new note.
            existing_entities: dict of {note_title: set of entity strings}
            min_shared: Minimum shared entities.

        Returns:
            List of CooccurrenceCandidate objects.
        """
        if min_shared is None:
            min_shared = self.MIN_SHARED

        new_entities = {e.text for e in self.extract(new_note_text)}

        candidates = []
        for title, entity_set in existing_entities.items():
            if title == new_note_title:
                continue
            shared = new_entities & entity_set
            if len(shared) >= min_shared:
                candidates.append(CooccurrenceCandidate(
                    source_title=new_note_title,
                    target_title=title,
                    shared_entities=sorted(shared),
                    confidence="low",
                ))

        candidates.sort(key=lambda c: len(c.shared_entities), reverse=True)
        return candidates


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: entity_cooccurrence.py <file_path> [file_path2 ...]")
        print("  Extracts entities from files and finds co-occurrences.")
        sys.exit(1)

    extractor = EntityExtractor()

    # Single file: just show entities
    if len(sys.argv) == 2:
        with open(sys.argv[1], "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        entities = extractor.extract(text)
        print(f"Entities found: {len(entities)}")
        for e in sorted(entities, key=lambda x: x.count, reverse=True)[:20]:
            print(f"  [{e.entity_type}] {e.text} (×{e.count})")

    # Multiple files: show entities and co-occurrences
    else:
        notes = {}
        for path in sys.argv[1:]:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                from pathlib import Path
                title = Path(path).stem
                notes[title] = f.read()

        print(f"Processing {len(notes)} notes...")
        candidates = extractor.find_cooccurrences(notes)
        print(f"Co-occurrence candidates: {len(candidates)}")
        for c in candidates[:10]:
            print(f"  {c.source_title} ↔ {c.target_title}")
            print(f"    Shared: {', '.join(c.shared_entities[:5])}")
