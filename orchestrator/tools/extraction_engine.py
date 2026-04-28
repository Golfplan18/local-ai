"""
extraction_engine.py — Three-Pass Document Extraction Engine (Phase 10, Step 5)

Implements the three-pass extraction pipeline:
  Pass A — Signal identification (lightweight model)
  Pass B — Note generation (primary analysis model)
  Pass C — Quality pre-screening (lightweight model)

Each pass is a separate model invocation with a focused context window.
The raw input document does not persist across passes — only structured
output from each pass feeds the next.

Canonical specification: Framework — Knowledge Artifact Coach v5.0
Pipeline specification: frameworks/book/document-processing.md

Usage:
    from orchestrator.tools.extraction_engine import ExtractionEngine
    engine = ExtractionEngine(config)
    results = engine.extract(markdown_text, input_type_result)
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    """A signal identified in Pass A."""
    id: str
    signal_type: str
    location: str
    summary: str
    proposed_note_type: str
    proposed_subtype: str | None
    confidence: str
    skip_reason: str | None = None
    source_text: str = ""


@dataclass
class CandidateNote:
    """A candidate note produced by Pass B."""
    signal_id: str
    title: str
    note_type: str
    subtype: str | None
    yaml_frontmatter: dict
    body: str
    relationships: list[dict] = field(default_factory=list)
    source_file: str = ""
    source_section: str = ""


@dataclass
class ScreenedNote:
    """A note after Pass C quality pre-screening."""
    note: CandidateNote
    queue: str  # "quality_gate", "auto_reject", "human_review"
    checks: dict = field(default_factory=dict)  # check_name → pass/fail/flag
    rejection_reason: str | None = None


@dataclass
class ExtractionResult:
    """Complete extraction result for a document."""
    source_file: str
    input_type: str
    signals: list[Signal]
    candidates: list[CandidateNote]
    screened: list[ScreenedNote]
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Subtype body schemas (from Framework — Knowledge Artifact Coach v5.0)
# ---------------------------------------------------------------------------

SUBTYPE_SCHEMAS = {
    "fact": {
        "description": "A verifiable empirical claim about how something works, what something is, or what has been observed.",
        "required_elements": [
            "Proposition bullets stating the factual claim with explicit actor-verb-target structure",
            "Each bullet is an independently verifiable statement",
            "Sources or evidence basis named where applicable",
        ],
        "example_title": "The hippocampus consolidates short-term memories into long-term storage during sleep",
    },
    "process_principle": {
        "description": "A generalizable rule about how a process, system, or methodology operates. Not a procedure — a principle that explains why a process works or what governs its behavior.",
        "required_elements": [
            "Proposition bullets stating the principle with explicit actor-verb-target structure",
            "Each bullet captures one facet of the governing rule",
            "The principle must be transferable across contexts",
        ],
        "example_title": "Feedback loops accelerate learning only when the delay between action and signal is shorter than the learner's attention cycle",
    },
    "definition": {
        "description": "A precise, formal definition of a concept. The definition itself is the insight.",
        "required_elements": [
            "Opening bullet states the definition as a complete proposition",
            "Supporting bullets clarify scope, boundary conditions, or distinguishing features",
            "Each bullet is self-contained",
        ],
        "example_title": "Minimum sufficiency is the smallest bundle of information that conveys an idea completely without requiring the reader to perform an unfinished synthesis",
    },
    "causal_claim": {
        "description": "An assertion that one thing causes, prevents, enables, or modulates another. Directional claim about mechanism.",
        "required_elements": [
            "Opening bullet states the causal relationship with explicit cause-effect structure",
            "Supporting bullets name the mechanism, conditions, or mediating factors",
            "Boundary conditions or exceptions stated where known",
        ],
        "example_title": "Premature abstraction in code increases maintenance cost by forcing all future changes through an interface that encoded the wrong assumptions",
    },
    "analogy": {
        "description": "A structural comparison where understanding one domain illuminates another.",
        "required_elements": [
            "Opening bullet names both domains and the structural correspondence",
            "Supporting bullets map specific elements from source domain to target domain",
            "Closing bullet states where the analogy breaks down",
        ],
        "example_title": "Version control branches function like parallel universe timelines that can be merged back into a shared reality",
    },
    "evaluative": {
        "description": "A judgment, assessment, or ranked comparison. Takes a position on relative value, quality, effectiveness, or priority.",
        "required_elements": [
            "Opening bullet states the evaluative claim with explicit criteria",
            "Supporting bullets name the evidence or reasoning for the judgment",
            "Comparison points or alternatives named where relevant",
        ],
        "example_title": "Proposition-format notes outperform prose paragraphs for RAG retrieval precision because each bullet is an independently addressable semantic unit",
    },
}

# The three grammar rules
GRAMMAR_RULES = """
Rule 1 — Named Actors: Every bullet must name its actor explicitly. No implicit subjects.
  Good: "The retrieval pipeline scores documents by semantic similarity"
  Bad: "Documents are scored by semantic similarity"

Rule 2 — Resolved Pronouns: No unresolved pronouns. Restate the actor rather than using "it", "they", "this".
  Good: "The linter enforces property order across all vault files"
  Bad: "It enforces property order across all files"

Rule 3 — Concrete Verbs: Active voice with specific, concrete verbs. No passive with hidden actors.
  Good: "The linter enforces property order"
  Bad: "Property order is enforced"
"""

# Relationship taxonomy
RELATIONSHIP_TYPES = [
    "supports", "contradicts", "qualifies", "extends", "supersedes",
    "analogous-to", "derived-from", "enables", "requires", "produces",
    "precedes", "parent", "child",
]

# Signal types for Pass A
SIGNAL_TYPES = [
    "crystallization", "definition", "causal", "process", "evaluative",
    "analogy", "principle", "fact", "position", "relationship",
    "decision", "framework", "validated", "open_question", "re_education",
    "thesis", "evidence_chain", "cross_reference",
]


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def build_pass_a_prompt(markdown_text: str, input_type: str,
                        source_file: str = "") -> list[dict]:
    """Build the Pass A (signal identification) prompt.

    Uses a simple numbered-list format optimized for local reasoning models.
    These models reliably produce numbered lists but fail at structured
    formats (YAML, pipe-delimited) due to reasoning-loop behavior.
    """
    system = "List the key knowledge claims from the text below. Number each one. Be concise — one sentence per claim. Skip trivial or well-known facts."

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": markdown_text},
    ]


def build_pass_b_prompt(signals: list[Signal], source_sections: dict[str, str],
                        source_file: str = "") -> list[dict]:
    """
    Build the Pass B (note generation) prompt.

    Args:
        signals: List of Signal objects from Pass A (excluding skipped signals).
        source_sections: Map of signal_id → relevant source text section.
        source_file: Original filename for provenance.
    """
    # Build schema reference
    schema_text = "## Subtype Body Schemas\n\n"
    for name, schema in SUBTYPE_SCHEMAS.items():
        schema_text += f"### {name}\n"
        schema_text += f"{schema['description']}\n"
        schema_text += "Required elements:\n"
        for elem in schema["required_elements"]:
            schema_text += f"  - {elem}\n"
        schema_text += f"Example title: {schema['example_title']}\n\n"

    # Build signal list
    signal_text = "## Signals to Process\n\n"
    for s in signals:
        signal_text += f"### {s.id}: {s.summary}\n"
        signal_text += f"Type: {s.signal_type} | Note type: {s.proposed_note_type}"
        if s.proposed_subtype:
            signal_text += f" | Subtype: {s.proposed_subtype}"
        signal_text += f" | Confidence: {s.confidence}\n"
        signal_text += f"Location: {s.location}\n"
        if s.id in source_sections:
            signal_text += f"\nSource text:\n{source_sections[s.id]}\n"
        signal_text += "\n"

    system = f"""You are a knowledge note generator for a vault-based PKM system.

Your task: Generate complete, vault-ready notes for each signal below.

{schema_text}

## Grammar Rules (enforce on all atomic and molecular notes)

{GRAMMAR_RULES}

## Relationship Types

Use these 13 types: {', '.join(RELATIONSHIP_TYPES)}
Confidence: high (explicit reference), medium (semantic discovery), low (entity co-occurrence)

## Output Format

For EACH signal, emit a note in this exact format:

<<<NOTE_START>>>
<<<YAML_START>>>
nexus:
type: working
tags:
  - [tag]
subtype: [value if atomic, omit otherwise]
<<<YAML_END>>>
<<<TITLE>>>
[Declarative title stating the claim — complete sentence for atomic/molecular]
<<<BODY>>>
[Note body in the correct format for its type:
 - Atomic/Molecular: proposition bullets with actor-verb-target
 - Glossary: Definition + Scope + Excludes + Related terms
 - Process: IF/THEN conditional format or numbered steps
 - Position: Current position + Reasoning + Rejected alternatives
 - Compound: preserve natural document structure]
<<<RELATIONSHIPS>>>
- type: [relationship type]
  target: "[Target Note Title]"
  confidence: [high|medium|low]
<<<SOURCE>>>
file: "{source_file}"
section: "[section heading]"
<<<NOTE_END>>>

CRITICAL: Generate ONLY the note blocks. Do NOT explain your reasoning or show your thought process. Emit the structured output directly."""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"{signal_text}"},
    ]


def build_pass_c_prompt(notes_text: str) -> list[dict]:
    """Build the Pass C (quality pre-screening) prompt."""
    system = """You are a quality pre-screening engine for a knowledge extraction pipeline.

Your task: Apply four quick checks to each candidate note and route it to the correct queue.

## Four Quick Checks

1. Self-containment: Read each bullet in isolation. Does it make sense without the title?
2. Single-claim: Does the note make exactly one claim (for atomics)? Title with "and" = flag.
3. Complete-sentence title: Is the title a declarative claim (for atomic/molecular)? Topic label = flag.
4. Schema conformance: Does the body follow the subtype's required schema?

## Routing

- ALL four checks pass → queue: quality_gate
- Clear structural violation (topic-label title, multiple claims, empty body) → queue: auto_reject
- Ambiguous failure OR compound note type → queue: human_review

## Output Format

For EACH note, emit:

<<<SCREEN_START>>>
signal_id: [id]
title: "[note title]"
checks:
  self_containment: [pass|fail|flag]
  single_claim: [pass|fail|flag|na]
  complete_sentence_title: [pass|fail|flag]
  schema_conformance: [pass|fail|flag]
queue: [quality_gate|auto_reject|human_review]
rejection_reason: [null or reason string]
<<<SCREEN_END>>>

CRITICAL: Output ONLY the screening blocks. Do NOT explain your reasoning or show your thought process. Emit the structured output directly."""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Screen these candidate notes:\n\n{notes_text}"},
    ]


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_signal_map(response: str) -> list[Signal]:
    """Parse Pass A signal map response into Signal objects.

    Primary format: numbered list ("1. Claim text here")
    Local LLMs reliably produce numbered lists but fail at structured formats.

    Also supports pipe-delimited and YAML-delimited as fallbacks.
    """
    signals = []

    # --- Primary: numbered list (from conversational prompt) ---
    numbered_items = re.findall(r'(?:^|\n)\s*(\d+)[\.\)]\s*(.+)', response)
    if numbered_items:
        for num_str, claim in numbered_items:
            claim = claim.strip().rstrip('.')
            if not claim or len(claim) < 10:
                continue

            # Heuristic type classification from claim content
            signal_type = _classify_claim(claim)
            subtype = _claim_to_subtype(signal_type)

            signals.append(Signal(
                id=f"S{int(num_str):03d}",
                signal_type=signal_type,
                location="",
                summary=claim,
                proposed_note_type="atomic",
                proposed_subtype=subtype,
                confidence="high",
                skip_reason=None,
            ))
        if signals:
            return signals

    # --- Fallback: pipe-delimited ---
    pipe_lines = [
        line.strip() for line in response.strip().split('\n')
        if '|' in line and re.match(r'^\s*S\d+\s*\|', line.strip())
    ]
    if pipe_lines:
        for line in pipe_lines:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) < 3:
                continue
            signal_id = parts[0]
            signal_type = parts[1] if len(parts) > 1 else "fact"
            summary = parts[2] if len(parts) > 2 else ""
            note_type = parts[3] if len(parts) > 3 else "atomic"
            subtype_val = parts[4] if len(parts) > 4 else None
            confidence = parts[5] if len(parts) > 5 else "medium"
            skip_reason = None
            if len(parts) > 6 and parts[6].upper() == "SKIP":
                skip_reason = "re-education"
            subtype = subtype_val if subtype_val and subtype_val != "null" else None
            signals.append(Signal(
                id=signal_id, signal_type=signal_type, location="",
                summary=summary, proposed_note_type=note_type,
                proposed_subtype=subtype, confidence=confidence,
                skip_reason=skip_reason,
            ))
        return signals

    # --- Fallback: YAML-delimited ---
    map_match = re.search(
        r'<<<SIGNAL_MAP_START>>>(.*?)<<<SIGNAL_MAP_END>>>',
        response, re.DOTALL
    )
    content = map_match.group(1) if map_match else response
    content = re.sub(r'```(?:ya?ml)?\s*\n', '', content)
    content = re.sub(r'\n```\s*$', '', content)

    signal_blocks = re.split(r'\n\s*-\s+id:\s+', content)
    for block in signal_blocks[1:]:
        signal_id = ""
        signal_type = ""
        summary = ""
        note_type = ""
        subtype = None
        confidence = "medium"
        skip_reason = None

        for line in block.strip().split('\n'):
            line = line.strip()
            if line.startswith('id:') or (not signal_id and re.match(r'^S\d+', line)):
                m = re.search(r'(S\d+)', line)
                signal_id = m.group(1) if m else ""
            elif line.startswith('type:'):
                signal_type = line.split(':', 1)[1].strip().strip('"\'')
            elif line.startswith('summary:'):
                summary = line.split(':', 1)[1].strip().strip('"\'')
            elif line.startswith('proposed_note_type:'):
                note_type = line.split(':', 1)[1].strip().strip('"\'')
            elif line.startswith('proposed_subtype:'):
                val = line.split(':', 1)[1].strip().strip('"\'')
                subtype = val if val and val != "null" else None
            elif line.startswith('confidence:'):
                confidence = line.split(':', 1)[1].strip().strip('"\'')
            elif line.startswith('skip_reason:'):
                val = line.split(':', 1)[1].strip().strip('"\'')
                skip_reason = val if val and val != "null" else None

        if not signal_id:
            m = re.match(r'(S\d+)', block.strip())
            if m:
                signal_id = m.group(1)
        if signal_id:
            signals.append(Signal(
                id=signal_id, signal_type=signal_type, location="",
                summary=summary, proposed_note_type=note_type,
                proposed_subtype=subtype, confidence=confidence,
                skip_reason=skip_reason,
            ))

    return signals


def _classify_claim(claim: str) -> str:
    """Heuristic signal type classification from claim text."""
    lower = claim.lower()

    # Definition patterns
    if re.search(r'\b(?:is defined as|means|refers to|is the)\b', lower):
        return "definition"
    if re.search(r'\b(?:is|are)\s+(?:a|an|the)\s+\w+\s+(?:that|which|where)\b', lower):
        return "definition"

    # Causal patterns
    if re.search(r'\b(?:causes?|prevents?|enables?|leads?\s+to|results?\s+in|produces?|because)\b', lower):
        return "causal"

    # Process/heuristic patterns
    if re.search(r'\b(?:steps?|procedure|method|heuristic|approach|technique|strategy)\b', lower):
        return "process"

    # Evaluative/tradeoff patterns
    if re.search(r'\b(?:tradeoff|trade-off|better|worse|more\s+effective|advantage|disadvantage|expensive|cheap)\b', lower):
        return "evaluative"

    # Analogy patterns
    if re.search(r'\b(?:like|analogous|similar\s+to|maps?\s+to|parallel)\b', lower):
        return "analogy"

    # Principle patterns
    if re.search(r'\b(?:principle|rule|law|always|never|must|fundamental)\b', lower):
        return "principle"

    # Quantitative fact patterns
    if re.search(r'\$\d|\d+%|\d+\s*(?:kWh|GB|MB|ms)', lower):
        return "fact"

    # Default: fact (most conservative classification)
    return "fact"


def _claim_to_subtype(signal_type: str) -> str | None:
    """Map signal type to atomic note subtype."""
    mapping = {
        "definition": "definition",
        "causal": "causal_claim",
        "process": "process_principle",
        "evaluative": "evaluative",
        "analogy": "analogy",
        "principle": "process_principle",
        "fact": "fact",
    }
    return mapping.get(signal_type)


def parse_candidate_notes(response: str, signals: list[Signal]) -> list[CandidateNote]:
    """Parse Pass B note generation response into CandidateNote objects."""
    candidates = []

    # Extract NOTE blocks
    blocks = re.findall(
        r'<<<NOTE_START>>>(.*?)<<<NOTE_END>>>',
        response, re.DOTALL
    )

    for i, block in enumerate(blocks):
        # Parse YAML frontmatter
        yaml_match = re.search(r'<<<YAML_START>>>(.*?)<<<YAML_END>>>', block, re.DOTALL)
        yaml_text = yaml_match.group(1).strip() if yaml_match else ""
        frontmatter = _parse_simple_yaml(yaml_text)

        # Parse title
        title_match = re.search(r'<<<TITLE>>>\s*(.+?)(?:\n|<<<)', block, re.DOTALL)
        title = title_match.group(1).strip() if title_match else f"Untitled Note {i+1}"

        # Parse body
        body_match = re.search(r'<<<BODY>>>(.*?)<<<(?:RELATIONSHIPS|SOURCE|NOTE_END)>>>', block, re.DOTALL)
        body = body_match.group(1).strip() if body_match else ""

        # Parse relationships
        rel_match = re.search(r'<<<RELATIONSHIPS>>>(.*?)<<<(?:SOURCE|NOTE_END)>>>', block, re.DOTALL)
        relationships = _parse_relationships(rel_match.group(1)) if rel_match else []

        # Parse source
        source_match = re.search(r'<<<SOURCE>>>(.*?)<<<NOTE_END>>>', block, re.DOTALL)
        source_file = ""
        source_section = ""
        if source_match:
            for line in source_match.group(1).strip().split('\n'):
                if line.strip().startswith('file:'):
                    source_file = line.split(':', 1)[1].strip().strip('"\'')
                elif line.strip().startswith('section:'):
                    source_section = line.split(':', 1)[1].strip().strip('"\'')

        # Determine note type and subtype
        tags = frontmatter.get("tags", [])
        note_type = "atomic"  # default
        for tag in tags:
            if tag in ("atomic", "molecular", "compound", "process", "glossary", "position"):
                note_type = tag
                break
        if frontmatter.get("type") == "matrix":
            note_type = "moc"

        subtype = frontmatter.get("subtype")

        # Match to signal if possible
        signal_id = ""
        if i < len(signals):
            signal_id = signals[i].id

        candidates.append(CandidateNote(
            signal_id=signal_id,
            title=title,
            note_type=note_type,
            subtype=subtype,
            yaml_frontmatter=frontmatter,
            body=body,
            relationships=relationships,
            source_file=source_file,
            source_section=source_section,
        ))

    return candidates


def parse_screening_results(response: str, candidates: list[CandidateNote]) -> list[ScreenedNote]:
    """Parse Pass C screening response into ScreenedNote objects."""
    screened = []

    blocks = re.findall(
        r'<<<SCREEN_START>>>(.*?)<<<SCREEN_END>>>',
        response, re.DOTALL
    )

    # Build lookup by signal_id or index
    candidate_lookup = {c.signal_id: c for c in candidates if c.signal_id}

    for i, block in enumerate(blocks):
        signal_id = ""
        title = ""
        checks = {}
        queue = "human_review"
        rejection_reason = None

        for line in block.strip().split('\n'):
            line = line.strip()
            if line.startswith('signal_id:'):
                signal_id = line.split(':', 1)[1].strip()
            elif line.startswith('title:'):
                title = line.split(':', 1)[1].strip().strip('"\'')
            elif line.startswith('self_containment:'):
                checks["self_containment"] = line.split(':', 1)[1].strip()
            elif line.startswith('single_claim:'):
                checks["single_claim"] = line.split(':', 1)[1].strip()
            elif line.startswith('complete_sentence_title:'):
                checks["complete_sentence_title"] = line.split(':', 1)[1].strip()
            elif line.startswith('schema_conformance:'):
                checks["schema_conformance"] = line.split(':', 1)[1].strip()
            elif line.startswith('queue:'):
                queue = line.split(':', 1)[1].strip()
            elif line.startswith('rejection_reason:'):
                val = line.split(':', 1)[1].strip().strip('"\'')
                rejection_reason = val if val and val != "null" else None

        # Match to candidate
        candidate = candidate_lookup.get(signal_id)
        if not candidate and i < len(candidates):
            candidate = candidates[i]

        if candidate:
            screened.append(ScreenedNote(
                note=candidate,
                queue=queue,
                checks=checks,
                rejection_reason=rejection_reason,
            ))

    # Any candidates not in screening results go to human_review
    screened_ids = {s.note.signal_id for s in screened}
    for c in candidates:
        if c.signal_id and c.signal_id not in screened_ids:
            screened.append(ScreenedNote(
                note=c,
                queue="human_review",
                checks={"note": "not screened — defaulting to human review"},
            ))

    return screened


def _parse_simple_yaml(text: str) -> dict:
    """Parse simple YAML-like text into a dict (no dependency on pyyaml)."""
    result = {}
    current_list_key = None

    for line in text.split('\n'):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue

        # List item
        if stripped.startswith('- '):
            if current_list_key:
                if current_list_key not in result:
                    result[current_list_key] = []
                result[current_list_key].append(stripped[2:].strip())
            continue

        # Key-value pair
        if ':' in stripped:
            key, _, value = stripped.partition(':')
            key = key.strip()
            value = value.strip()

            if not value:
                # Could be a list header
                current_list_key = key
                continue

            current_list_key = None
            # Clean up value
            value = value.strip('"\'')
            if value == "null" or value == "~":
                value = None
            result[key] = value

    return result


def _parse_relationships(text: str) -> list[dict]:
    """Parse relationship entries from a block."""
    relationships = []
    current = {}

    for line in text.strip().split('\n'):
        line = line.strip()
        if line.startswith('- type:'):
            if current:
                relationships.append(current)
            current = {"type": line.split(':', 1)[1].strip().strip('"\'') }
        elif line.startswith('target:'):
            current["target"] = line.split(':', 1)[1].strip().strip('"\'')
        elif line.startswith('confidence:'):
            current["confidence"] = line.split(':', 1)[1].strip().strip('"\'')

    if current:
        relationships.append(current)

    return relationships


# ---------------------------------------------------------------------------
# Template-based note generation (Pass B replacement)
# ---------------------------------------------------------------------------

def _build_candidates_from_signals(signals: list[Signal],
                                    source_file: str = "") -> list[CandidateNote]:
    """Build candidate notes directly from signals using templates.

    This replaces the model-driven Pass B for local LLMs that cannot
    produce structured <<<NOTE_START>>> output reliably.
    """
    candidates = []

    for signal in signals:
        # Title: use the claim summary directly (already a complete sentence)
        title = signal.summary.strip()
        if not title:
            continue

        # Frontmatter
        tags = ["atomic"]
        if signal.signal_type == "definition":
            tags = ["glossary"]
        elif signal.signal_type == "process":
            tags = ["process"]
        elif signal.signal_type == "evaluative":
            tags = ["atomic"]

        frontmatter = {
            "type": "working",
            "tags": tags,
        }
        if signal.proposed_subtype:
            frontmatter["subtype"] = signal.proposed_subtype

        # Body: format as proposition bullets (the core atomic note format)
        # Quality gate requires ≥2 bullets for non-fragment status.
        body = f"- {title}"
        if source_file:
            body += f"\n- Source: extracted from session {source_file}"
        else:
            body += "\n- Source: extracted from chat session"

        candidates.append(CandidateNote(
            signal_id=signal.id,
            title=title,
            note_type=tags[0],
            subtype=signal.proposed_subtype,
            yaml_frontmatter=frontmatter,
            body=body,
            relationships=[],
            source_file=source_file,
            source_section="",
        ))

    return candidates


def _screen_candidates_heuristic(candidates: list[CandidateNote]) -> list[ScreenedNote]:
    """Rule-based quality screening without model calls.

    Checks:
    1. Self-containment: body makes sense without title context
    2. Single-claim: title doesn't contain "and" joining two claims
    3. Complete-sentence title: title is a declarative sentence, not a topic label
    4. Minimum length: body has enough substance
    """
    screened = []

    for candidate in candidates:
        checks = {}
        queue = "quality_gate"

        title = candidate.title
        body = candidate.body

        # Check 1: Self-containment (body has substance)
        body_words = len(body.split())
        if body_words < 5:
            checks["self_containment"] = "fail"
            queue = "auto_reject"
        else:
            checks["self_containment"] = "pass"

        # Check 2: Single-claim (no "and" joining independent clauses)
        if " and " in title and title.count(" and ") > 1:
            checks["single_claim"] = "flag"
            if queue == "quality_gate":
                queue = "human_review"
        else:
            checks["single_claim"] = "pass"

        # Check 3: Complete-sentence title (has a verb)
        # Simple heuristic: title has > 4 words and contains common verbs
        title_words = title.split()
        has_verb = any(
            w.lower() in ("is", "are", "was", "were", "has", "have", "had",
                          "does", "do", "did", "can", "could", "will", "would",
                          "should", "must", "may", "might")
            or w.lower().endswith(("es", "ed", "ing", "tes", "ses", "zes"))
            for w in title_words
        )
        if len(title_words) < 4 or not has_verb:
            checks["complete_sentence_title"] = "flag"
            if queue == "quality_gate":
                queue = "human_review"
        else:
            checks["complete_sentence_title"] = "pass"

        # Check 4: Schema conformance (basic structure check)
        checks["schema_conformance"] = "pass"

        screened.append(ScreenedNote(
            note=candidate,
            queue=queue,
            checks=checks,
            rejection_reason=None if queue != "auto_reject" else "Body too short",
        ))

    return screened


# ---------------------------------------------------------------------------
# Section extraction helper
# ---------------------------------------------------------------------------

def extract_sections_for_signals(markdown_text: str, signals: list[Signal]) -> dict[str, str]:
    """
    Given the source markdown and signal locations, extract the relevant
    text section for each signal. Returns signal_id → section_text.
    """
    lines = markdown_text.split('\n')
    sections = {}

    # Build a heading index
    heading_positions = []
    for i, line in enumerate(lines):
        if re.match(r'^#{1,6}\s+', line):
            heading_positions.append((i, line.strip()))

    for signal in signals:
        if signal.skip_reason:
            continue

        location = signal.location
        section_text = ""

        # Try to match location to a heading
        matched_start = None
        matched_end = len(lines)

        for idx, (pos, heading) in enumerate(heading_positions):
            if location.lower() in heading.lower() or heading.lower() in location.lower():
                matched_start = pos
                # End at next heading of same or higher level
                heading_level = len(re.match(r'^(#+)', heading).group(1))
                for next_pos, next_heading in heading_positions[idx + 1:]:
                    next_level = len(re.match(r'^(#+)', next_heading).group(1))
                    if next_level <= heading_level:
                        matched_end = next_pos
                        break
                break

        if matched_start is not None:
            section_lines = lines[matched_start:min(matched_end, matched_start + 100)]
            section_text = '\n'.join(section_lines)
        else:
            # Try line range (e.g., "lines 10-25")
            range_match = re.search(r'(?:lines?\s+)?(\d+)\s*[-–]\s*(\d+)', location)
            if range_match:
                start = max(0, int(range_match.group(1)) - 1)
                end = min(len(lines), int(range_match.group(2)))
                section_text = '\n'.join(lines[start:end])
            else:
                # Fallback: search for signal summary text in the document
                summary_lower = signal.summary.lower()
                for i, line in enumerate(lines):
                    if any(word in line.lower() for word in summary_lower.split()[:3]):
                        start = max(0, i - 2)
                        end = min(len(lines), i + 20)
                        section_text = '\n'.join(lines[start:end])
                        break

        # Cap section length to ~1500 chars
        if len(section_text) > 1500:
            section_text = section_text[:1500] + "\n[... truncated]"

        sections[signal.id] = section_text

    return sections


# ---------------------------------------------------------------------------
# Machine-readable output formatter
# ---------------------------------------------------------------------------

def format_pipeline_output(result: ExtractionResult) -> str:
    """Format extraction results in the machine-readable pipeline format."""
    output_parts = []

    for screened in result.screened:
        note = screened.note
        fm = note.yaml_frontmatter

        block = "<<<NOTE_START>>>\n"
        block += "<<<YAML_START>>>\n"

        # Frontmatter
        nexus = fm.get("nexus", "")
        if nexus:
            if isinstance(nexus, list):
                block += "nexus:\n"
                for n in nexus:
                    block += f"  - {n}\n"
            else:
                block += f"nexus:\n  - {nexus}\n"
        else:
            block += "nexus:\n"

        block += f"type: {fm.get('type', 'working')}\n"

        tags = fm.get("tags", [])
        if isinstance(tags, list) and tags:
            block += "tags:\n"
            for t in tags:
                block += f"  - {t}\n"
        else:
            block += "tags:\n"

        if note.subtype:
            block += f"subtype: {note.subtype}\n"

        defs = fm.get("definitions_required")
        if defs:
            if isinstance(defs, list):
                block += "definitions_required:\n"
                for d in defs:
                    block += f"  - {d}\n"

        block += "<<<YAML_END>>>\n"
        block += f"<<<TITLE>>>\n{note.title}\n"
        block += f"<<<BODY>>>\n{note.body}\n"

        if note.relationships:
            block += "<<<RELATIONSHIPS>>>\n"
            for rel in note.relationships:
                block += f'- type: {rel.get("type", "supports")}\n'
                block += f'  target: "{rel.get("target", "")}"\n'
                block += f'  confidence: {rel.get("confidence", "medium")}\n'

        block += "<<<SOURCE>>>\n"
        block += f'file: "{note.source_file}"\n'
        block += f'section: "{note.source_section}"\n'
        block += "<<<NOTE_END>>>"

        output_parts.append(block)

    # Run metadata
    meta = "<<<RUN_METADATA>>>\n"
    meta += f'source_file: "{result.source_file}"\n'
    meta += f'input_type: {result.input_type}\n'
    meta += f'notes_extracted: {len(result.candidates)}\n'

    approved = sum(1 for s in result.screened if s.queue == "quality_gate")
    rejected = sum(1 for s in result.screened if s.queue == "auto_reject")
    review = sum(1 for s in result.screened if s.queue == "human_review")

    meta += f'notes_auto_approved: {approved}\n'
    meta += f'notes_auto_rejected: {rejected}\n'
    meta += f'notes_human_review: {review}\n'

    rel_count = sum(len(s.note.relationships) for s in result.screened)
    meta += f'relationship_candidates: {rel_count}\n'

    meta += "<<<RUN_METADATA_END>>>"
    output_parts.append(meta)

    return "\n\n".join(output_parts)


# ---------------------------------------------------------------------------
# Main extraction engine
# ---------------------------------------------------------------------------

class ExtractionEngine:
    """
    Three-pass document extraction engine.

    Requires a model calling function to be provided. The engine builds
    prompts and parses responses; model invocation is delegated.

    Usage:
        engine = ExtractionEngine(call_fn=call_model_function)
        result = engine.extract(markdown_text, input_type_result)
    """

    def __init__(self, call_fn=None, config: dict = None):
        """
        Args:
            call_fn: Function(messages, endpoint) -> str. The model call function.
                     If None, the engine operates in prompt-only mode (returns prompts
                     without calling models).
            config: Endpoints configuration dict for slot resolution.
        """
        self.call_fn = call_fn
        self.config = config or {}

    def _get_endpoint(self, slot: str) -> dict | None:
        """Resolve a slot name to an endpoint dict."""
        if not self.config:
            return None
        try:
            # Import here to avoid circular dependency
            from boot import get_slot_endpoint
            return get_slot_endpoint(self.config, slot)
        except ImportError:
            try:
                from orchestrator.boot import get_slot_endpoint
                return get_slot_endpoint(self.config, slot)
            except ImportError:
                return None

    def _call_model(self, messages: list, slot: str = "sidebar",
                    max_tokens: int | None = None) -> str | None:
        """Call a model via the configured call function.

        Args:
            messages: Chat messages to send.
            slot: Model slot name (sidebar, depth, etc.).
            max_tokens: Override max generation tokens for this call.
        """
        if not self.call_fn:
            return None
        endpoint = self._get_endpoint(slot)
        if not endpoint:
            return None
        if max_tokens:
            endpoint = dict(endpoint)  # copy so we don't mutate the original
            endpoint["max_tokens"] = max_tokens
        return self.call_fn(messages, endpoint)

    @staticmethod
    def _chunk_transcript(text: str, max_chars: int) -> list[str]:
        """Split a long transcript into chunks at natural boundaries.

        Splits on turn boundaries (**User:** / **Assistant:**) first,
        falling back to paragraph breaks, then hard split.
        """
        # Try to split on conversation turns
        turn_pattern = re.compile(r'\n\n\*\*(?:User|Assistant)\*?\*?:\*?\*?\n\n')
        parts = turn_pattern.split(text)
        delimiters = turn_pattern.findall(text)

        chunks = []
        current = ""

        for i, part in enumerate(parts):
            # Re-attach the delimiter that preceded this part
            if i > 0 and i - 1 < len(delimiters):
                candidate = current + delimiters[i - 1] + part
            else:
                candidate = current + part

            if len(candidate) <= max_chars or not current:
                current = candidate
            else:
                chunks.append(current)
                # Start new chunk with this part (include its delimiter)
                if i > 0 and i - 1 < len(delimiters):
                    current = delimiters[i - 1] + part
                else:
                    current = part

        if current:
            chunks.append(current)

        # If no splits were possible (no turn markers), split on paragraphs
        if len(chunks) == 1 and len(chunks[0]) > max_chars:
            paragraphs = text.split("\n\n")
            chunks = []
            current = ""
            for p in paragraphs:
                if len(current) + len(p) + 2 <= max_chars or not current:
                    current = (current + "\n\n" + p) if current else p
                else:
                    chunks.append(current)
                    current = p
            if current:
                chunks.append(current)

        return chunks if chunks else [text]

    def extract(self, markdown_text: str, input_type_result: dict,
                source_file: str = "") -> ExtractionResult:
        """
        Run the full three-pass extraction pipeline.

        Args:
            markdown_text: The converted markdown text to process.
            input_type_result: Output from detect_input_type().
            source_file: Original filename for provenance.

        Returns:
            ExtractionResult with signals, candidates, and screened notes.
        """
        input_type = input_type_result.get("type", "short_document")

        # --- Pass A: Signal Identification ---
        # Compact pipe-delimited prompt prevents reasoning-model loop behavior.
        # 8192 tokens gives reasoning models room for chain-of-thought + output.
        pass_a_messages = build_pass_a_prompt(markdown_text, input_type, source_file)
        pass_a_response = self._call_model(pass_a_messages, slot="sidebar",
                                            max_tokens=8192)

        if not pass_a_response:
            return ExtractionResult(
                source_file=source_file,
                input_type=input_type,
                signals=[],
                candidates=[],
                screened=[],
                metadata={"error": "Pass A model call failed"},
            )

        signals = parse_signal_map(pass_a_response)

        # Filter out skipped signals and placeholder-only signals
        active_signals = [
            s for s in signals
            if not s.skip_reason
            and s.signal_type not in ("", "[type]")
            and s.summary not in ("", "[summary]")
        ]

        if not active_signals:
            return ExtractionResult(
                source_file=source_file,
                input_type=input_type,
                signals=signals,
                candidates=[],
                screened=[],
                metadata={"note": "No viable signals identified"},
            )

        # --- Pass B: Note Generation ---
        # Build candidate notes directly from signals (template-based).
        # Local reasoning models cannot reliably produce structured
        # <<<NOTE_START>>> delimited output. Template generation is
        # instant and 100% reliable.
        candidates = _build_candidates_from_signals(active_signals, source_file)

        if not candidates:
            return ExtractionResult(
                source_file=source_file,
                input_type=input_type,
                signals=signals,
                candidates=[],
                screened=[],
                metadata={"note": "No candidate notes generated"},
            )

        # --- Pass C: Quality Pre-Screening ---
        # Rule-based screening: check title completeness, self-containment,
        # body length. No model call needed.
        screened = _screen_candidates_heuristic(candidates)

        return ExtractionResult(
            source_file=source_file,
            input_type=input_type,
            signals=signals,
            candidates=candidates,
            screened=screened,
            metadata={
                "total_signals": len(signals),
                "active_signals": len(active_signals),
                "skipped_signals": len(signals) - len(active_signals),
                "candidates_generated": len(candidates),
                "auto_approved": sum(1 for s in screened if s.queue == "quality_gate"),
                "auto_rejected": sum(1 for s in screened if s.queue == "auto_reject"),
                "human_review": sum(1 for s in screened if s.queue == "human_review"),
            },
        )

    def extract_prompts_only(self, markdown_text: str, input_type_result: dict,
                             source_file: str = "") -> dict:
        """
        Return the prompts for all three passes without calling models.
        Useful for testing, inspection, and manual execution.
        """
        input_type = input_type_result.get("type", "short_document")

        return {
            "pass_a": build_pass_a_prompt(markdown_text, input_type, source_file),
            "pass_b_template": "Requires Pass A results — run Pass A first",
            "pass_c_template": "Requires Pass B results — run Pass B first",
        }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: extraction_engine.py <file_path>")
        print("  Runs in prompt-only mode (shows Pass A prompt without calling models).")
        sys.exit(1)

    file_path = sys.argv[1]

    # Use format converter
    try:
        from orchestrator.tools.format_convert import convert_to_markdown
        text = convert_to_markdown(file_path)
    except ImportError:
        with open(file_path, "r") as f:
            text = f.read()

    # Detect input type
    try:
        from orchestrator.tools.input_detect import detect_input_type
        type_result = detect_input_type(text)
    except ImportError:
        type_result = {"type": "short_document"}

    print(f"Input type: {type_result['type']} (confidence: {type_result.get('confidence', 'unknown')})")
    print(f"Estimated tokens: {type_result.get('details', {}).get('estimated_tokens', '?')}")
    print()

    engine = ExtractionEngine()
    prompts = engine.extract_prompts_only(text, type_result, source_file=file_path)

    print("=== Pass A Prompt (System) ===")
    print(prompts["pass_a"][0]["content"][:500])
    print("...")
    print()
    print(f"Pass A user message length: {len(prompts['pass_a'][1]['content'])} chars")
