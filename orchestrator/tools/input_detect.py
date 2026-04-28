"""
input_detect.py — Input Type Detection for Document Processing Pipeline

Classifies input documents into processing tracks before extraction.
Runs on the markdown output from format_convert.py.

Input types:
  - chat: conversation transcript (alternating speaker turns) → Path 1 + Path 2
  - long_form_source: structured document > 4000 tokens → Path 1 + HCP
  - short_document: structured document <= 4000 tokens → Path 1
  - vault_note: existing vault note with YAML frontmatter → Path 1 simplified
  - fragment: unstructured text < 500 tokens → human review
  - unknown: unclassifiable → human review

Usage:
    from orchestrator.tools.input_detect import detect_input_type
    result = detect_input_type(markdown_text)
    # result: {"type": "chat", "confidence": "high", "details": {...}}
"""

from __future__ import annotations

import re


# Approximate token count: ~4 chars per token for English text
def _estimate_tokens(text: str) -> int:
    """Estimate token count from character length."""
    return len(text) // 4


def _has_yaml_frontmatter(text: str) -> dict | None:
    """Check for YAML frontmatter and extract vault properties if present."""
    match = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
    if not match:
        return None

    yaml_block = match.group(1)
    properties = {}

    # Check for vault-specific properties
    for prop in ("nexus", "type", "tags", "subtype", "hub", "writing"):
        if re.search(rf'^{prop}\s*:', yaml_block, re.MULTILINE):
            properties[prop] = True

    return properties if properties else None


def _detect_chat_pattern(text: str) -> dict | None:
    """
    Detect conversation turn-pair patterns.

    Looks for alternating speaker labels that indicate a chat transcript.
    Returns turn count and detected pattern if found.
    """
    # Common chat patterns (case-insensitive)
    patterns = [
        # User/Assistant pattern (Ora, Claude, ChatGPT exports)
        (r'(?:^|\n)\s*\*?\*?(?:User|Human|You)\s*[:：]\*?\*?',
         r'(?:^|\n)\s*\*?\*?(?:Assistant|AI|Claude|ChatGPT|Gemini|Model|Bot)\s*[:：]\*?\*?'),
        # Q/A pattern
        (r'(?:^|\n)\s*\*?\*?Q\s*[:：]\*?\*?',
         r'(?:^|\n)\s*\*?\*?A\s*[:：]\*?\*?'),
        # Numbered turn pattern
        (r'(?:^|\n)\s*\*?\*?(?:Turn|Exchange)\s+\d+',
         None),  # Single pattern for turn-based formats
        # Timestamp + speaker pattern (session logs)
        (r'(?:^|\n)\*?\*?Timestamp\*?\*?\s*:.*\n\*?\*?(?:User|Human)\*?\*?\s*:',
         r'(?:^|\n)\*?\*?(?:Assistant|AI)\*?\*?\s*:'),
    ]

    for user_pat, assistant_pat in patterns:
        user_matches = re.findall(user_pat, text, re.IGNORECASE)
        if assistant_pat:
            assistant_matches = re.findall(assistant_pat, text, re.IGNORECASE)
            turn_count = min(len(user_matches), len(assistant_matches))
        else:
            turn_count = len(user_matches)

        if turn_count >= 2:
            return {
                "turn_count": turn_count,
                "pattern": user_pat[:40],
            }

    return None


def _detect_document_structure(text: str) -> dict:
    """
    Analyze document structure indicators.

    Returns a dict with structure signals: headings, sections, formal tone,
    bibliography, abstract, etc.
    """
    signals = {}

    # Heading count (markdown ## style)
    headings = re.findall(r'^#{1,6}\s+.+', text, re.MULTILINE)
    signals["heading_count"] = len(headings)

    # Numbered sections
    numbered = re.findall(r'^(?:\d+\.)+\s+.+', text, re.MULTILINE)
    signals["numbered_sections"] = len(numbered)

    # Bibliography / references section
    signals["has_bibliography"] = bool(
        re.search(r'(?:^|\n)#{1,3}\s*(?:References|Bibliography|Works Cited|Sources)',
                  text, re.IGNORECASE)
    )

    # Abstract
    signals["has_abstract"] = bool(
        re.search(r'(?:^|\n)#{1,3}\s*Abstract', text, re.IGNORECASE)
    )

    # Table of contents indicators
    signals["has_toc"] = bool(
        re.search(r'(?:^|\n)#{1,3}\s*(?:Table of Contents|Contents)',
                  text, re.IGNORECASE)
    )

    # Formal tone indicators (specification language)
    formal_patterns = [
        r'\bSHALL\b', r'\bMUST\b', r'\bSHOULD\b',
        r'\bherein\b', r'\baforementioned\b',
        r'\bpursuant to\b', r'\bin accordance with\b',
    ]
    formal_count = sum(
        len(re.findall(p, text)) for p in formal_patterns
    )
    signals["formal_tone_score"] = min(formal_count, 10)

    # Calculate overall structure score
    score = (
        min(signals["heading_count"], 5) * 2 +
        min(signals["numbered_sections"], 3) +
        (3 if signals["has_bibliography"] else 0) +
        (2 if signals["has_abstract"] else 0) +
        (1 if signals["has_toc"] else 0) +
        signals["formal_tone_score"]
    )
    signals["structure_score"] = score

    return signals


def detect_input_type(text: str) -> dict:
    """
    Classify input text into a processing track.

    Args:
        text: Markdown text (output of format_convert.py or raw markdown).

    Returns:
        dict with keys:
            type: str — one of: chat, long_form_source, short_document,
                  vault_note, fragment, unknown
            confidence: str — high, medium, low
            details: dict — supporting evidence for the classification
            paths: list[int] — which output paths to run (1, 2, or both)
            hcp: bool — whether HCP context prepend is needed
    """
    token_estimate = _estimate_tokens(text)
    details = {"estimated_tokens": token_estimate}

    # Check for vault note (YAML frontmatter with vault properties)
    vault_props = _has_yaml_frontmatter(text)
    if vault_props:
        vault_keys = list(vault_props.keys())
        # Require at least 2 vault-specific properties to confirm
        if len(vault_keys) >= 2 or "nexus" in vault_keys:
            details["vault_properties"] = vault_keys
            return {
                "type": "vault_note",
                "confidence": "high" if len(vault_keys) >= 3 else "medium",
                "details": details,
                "paths": [1],
                "hcp": False,
            }

    # Check for chat pattern
    chat_result = _detect_chat_pattern(text)
    if chat_result:
        details["chat_detection"] = chat_result
        confidence = "high" if chat_result["turn_count"] >= 4 else "medium"
        return {
            "type": "chat",
            "confidence": confidence,
            "details": details,
            "paths": [1, 2],
            "hcp": False,
        }

    # Check for fragment (too small for reliable extraction)
    if token_estimate < 500:
        structure = _detect_document_structure(text)
        details["structure"] = structure
        # Even small text with strong structure is a short document
        if structure["structure_score"] >= 5:
            return {
                "type": "short_document",
                "confidence": "medium",
                "details": details,
                "paths": [1],
                "hcp": False,
            }
        return {
            "type": "fragment",
            "confidence": "high" if token_estimate < 200 else "medium",
            "details": details,
            "paths": [],
            "hcp": False,
        }

    # Analyze document structure
    structure = _detect_document_structure(text)
    details["structure"] = structure

    # Long-form source vs short document
    if token_estimate > 4000:
        if structure["structure_score"] >= 3:
            return {
                "type": "long_form_source",
                "confidence": "high",
                "details": details,
                "paths": [1],
                "hcp": True,
            }
        else:
            # Large but unstructured — could be a long chat without clear labels
            # or a raw text dump
            return {
                "type": "long_form_source",
                "confidence": "low",
                "details": details,
                "paths": [1],
                "hcp": True,
            }

    # Short document (structured, <= 4000 tokens)
    if structure["structure_score"] >= 3:
        return {
            "type": "short_document",
            "confidence": "high" if structure["structure_score"] >= 6 else "medium",
            "details": details,
            "paths": [1],
            "hcp": False,
        }

    # Unstructured medium-length text — likely a short document but low confidence
    if token_estimate >= 500:
        return {
            "type": "short_document",
            "confidence": "low",
            "details": details,
            "paths": [1],
            "hcp": False,
        }

    # Fallback
    return {
        "type": "unknown",
        "confidence": "low",
        "details": details,
        "paths": [],
        "hcp": False,
    }


def detect_from_file(file_path: str) -> dict:
    """
    Detect input type from a file path.

    Runs format conversion first, then classifies the converted text.
    """
    from orchestrator.tools.format_convert import convert_to_markdown

    markdown = convert_to_markdown(file_path)
    result = detect_input_type(markdown)
    result["details"]["source_file"] = file_path
    return result


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: input_detect.py <file_path_or_->")
        print("  Detects input type for document processing pipeline.")
        print("  Use '-' to read from stdin.")
        sys.exit(1)

    if sys.argv[1] == "-":
        text = sys.stdin.read()
        result = detect_input_type(text)
    else:
        result = detect_from_file(sys.argv[1])

    print(json.dumps(result, indent=2))
