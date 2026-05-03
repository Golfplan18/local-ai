"""Load + parse cleaned-pair markdown files written by Phase 1.

A cleaned-pair file has this shape (Phase 1.10 writer):

    ---
    nexus:
    type: cleaned-pair
    date created: YYYY-MM-DD
    date modified: YYYY-MM-DD
    source_chat: <path>
    source_pair_num: <int>
    source_platform: claude | chatgpt | gemini | local-ora | unknown
    source_timestamp: <ISO-8601>
    thread_id: thread_<hash>_<NNN>
    prior_pair: <filename or empty>
    next_pair: <filename or empty>
    processing_model: <model-id>
    processed_at: <ISO-8601>
    tags: []
    ---

    ## Context

    ### Session context
    <one paragraph>

    ### Pair context
    <one paragraph>

    ## Exchange

    ### User input
    <cleaned user input>

    #### Pasted segments  (optional)
    ...

    ### Assistant response
    <cleaned AI response>

    #### Engagement strip log  (optional)
    ...

This module exposes one function — `load_cleaned_pair(path)` — which
returns a `CleanedPairFile` dataclass with the parsed fields. Tolerant
of empty user-input or empty AI-response sections (Phase 1's empty-side
success contract). Raises `ValueError` only on missing frontmatter or
missing `## Exchange` block.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Parsed record
# ---------------------------------------------------------------------------


@dataclass
class CleanedPairFile:
    """Parsed cleaned-pair file. Source of truth for Phase 2 chunk emission."""
    # File identity
    file_path:           str
    # Frontmatter
    source_chat:         str
    source_pair_num:     int
    source_platform:     str
    source_timestamp:    Optional[datetime]
    thread_id:           str
    prior_pair:          str = ""
    next_pair:           str = ""
    processing_model:    str = ""
    processed_at:        Optional[datetime] = None
    tags:                list[str] = field(default_factory=list)
    # Body — context
    session_context:     str = ""
    pair_context:        str = ""
    # Body — exchange
    cleaned_user_input:  str = ""
    cleaned_ai_response: str = ""


# ---------------------------------------------------------------------------
# Parsing internals
# ---------------------------------------------------------------------------


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split YAML frontmatter from body. Returns (yaml_dict, body)."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("missing YAML frontmatter")
    raw, body = m.group(1), m.group(2)
    out: dict = {}
    for line in raw.splitlines():
        if ":" not in line or line.startswith(" "):
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out, body


def _parse_iso_timestamp(value: str) -> Optional[datetime]:
    """Best-effort ISO-8601 parse; returns None on failure."""
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value[:len(fmt) + 4], fmt)
        except (ValueError, TypeError):
            continue
    return None


def _strip_yaml_quotes(value: str) -> str:
    """Strip YAML's single-quote escaping from a frontmatter value."""
    if value.startswith("'") and value.endswith("'") and len(value) >= 2:
        return value[1:-1].replace("''", "'")
    return value


def _section(body: str, heading: str, terminators: list[str]) -> str:
    """Extract the content under an exact heading line until the EARLIEST
    of the given exact terminator strings. Returns the empty string if
    the heading is absent.

    Markdown headings INSIDE cleaned content (e.g. an AI response that
    contains `### Analysis Of Your Ideas`) are NOT section boundaries —
    only the specific structural strings the Phase 1 writer emits are.
    Hardcoded terminators avoid mis-truncation when content carries
    markdown headings of its own.
    """
    h_pat = rf"(?:^|\n){re.escape(heading)}[ \t]*\n"
    m = re.search(h_pat, body)
    if not m:
        return ""
    start = m.end()
    end = len(body)
    for term in terminators:
        t_pat = rf"\n{re.escape(term)}(?:[ \t]*\n|\s|\Z)"
        tm = re.search(t_pat, body[start:])
        if tm:
            end = min(end, start + tm.start())
    return body[start:end].strip()


def _strip_optional_subsection(text: str, heading: str) -> str:
    """Within a section's body, drop a `#### heading` subsection (e.g.
    pasted-segments annotation) so only the canonical content remains."""
    pat = rf"\n#### {re.escape(heading)}\b.*?(?=\n##|\Z)"
    return re.sub(pat, "", text, flags=re.DOTALL).rstrip()


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def load_cleaned_pair(path: str | Path) -> CleanedPairFile:
    """Read + parse one cleaned-pair file.

    Raises:
        FileNotFoundError: file doesn't exist
        ValueError:        missing frontmatter, missing Exchange block,
                           or unparseable required field
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    yaml, body = _parse_frontmatter(text)

    # Frontmatter
    source_chat      = _strip_yaml_quotes(yaml.get("source_chat", ""))
    pair_num_raw     = yaml.get("source_pair_num", "0")
    try:
        source_pair_num = int(pair_num_raw)
    except (ValueError, TypeError):
        raise ValueError(f"unparseable source_pair_num: {pair_num_raw!r}")

    source_platform  = yaml.get("source_platform", "unknown")
    source_timestamp = _parse_iso_timestamp(yaml.get("source_timestamp", ""))
    processed_at     = _parse_iso_timestamp(yaml.get("processed_at", ""))
    thread_id        = yaml.get("thread_id", "")
    prior_pair       = _strip_yaml_quotes(yaml.get("prior_pair", ""))
    next_pair        = _strip_yaml_quotes(yaml.get("next_pair", ""))
    processing_model = _strip_yaml_quotes(yaml.get("processing_model", ""))

    # Body sections — tolerant of missing User input or Assistant response
    # (Phase 1's empty-side success contract). Terminators are the EXACT
    # structural headings the Phase 1 writer emits in document order, so
    # markdown headings inside the cleaned content (e.g. AI response with
    # `### Analysis…`) don't accidentally truncate sections.
    session_context = _section(
        body, "### Session context", ["### Pair context", "## Exchange"],
    )
    pair_context = _section(
        body, "### Pair context", ["## Exchange"],
    )

    # User input section may carry a `#### Pasted segments` subsection;
    # the cleaned content is everything BEFORE that subsection. Strip
    # the annotation block so the chunk gets just the cleaned text.
    user_section = _section(
        body, "### User input", ["### Assistant response"],
    )
    user_clean = _strip_optional_subsection(user_section, "Pasted segments")

    # Assistant response is the last section — runs to end of file (or
    # the optional `#### Engagement strip log` subsection).
    ai_section = _section(body, "### Assistant response", [])
    ai_clean = _strip_optional_subsection(ai_section, "Engagement strip log")

    if "## Exchange" not in body:
        raise ValueError("missing `## Exchange` section")

    return CleanedPairFile(
        file_path           = str(p),
        source_chat         = source_chat,
        source_pair_num     = source_pair_num,
        source_platform     = source_platform,
        source_timestamp    = source_timestamp,
        thread_id           = thread_id,
        prior_pair          = prior_pair,
        next_pair           = next_pair,
        processing_model    = processing_model,
        processed_at        = processed_at,
        tags                = [],   # Phase 1 always emits empty tags
        session_context     = session_context,
        pair_context        = pair_context,
        cleaned_user_input  = user_clean,
        cleaned_ai_response = ai_clean,
    )


__all__ = [
    "CleanedPairFile",
    "load_cleaned_pair",
]
