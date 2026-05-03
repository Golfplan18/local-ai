"""Cleaned-pair file writer (Phase 1.10).

Composes the full cleaned-pair markdown file (YAML frontmatter +
Context + Exchange + per-pair annotations) and writes it to the
flat `~/Documents/Commercial AI archives/` folder.

File format (per the architecture doc):

    ---
    nexus:
    type: cleaned-pair
    date created: <YYYY-MM-DD>
    date modified: <YYYY-MM-DD>
    source_chat: <relative path under conversations/raw/>
    source_pair_num: <int>
    source_platform: claude | chatgpt | gemini | ora-local | unknown
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
    <cleaned user input — pasted blocks restored verbatim>

    #### Pasted segments
    - Segment N — type=<class>, status=<extract|mention-only|...>
      - Vault index match: ...
      - Heuristic flags: ...
    (omitted if no pasted segments)

    ### Assistant response
    <cleaned AI response, engagement wrapper(s) stripped>

    #### Engagement strip log
    - Stripped paragraph (N chars): "<first ~80 chars>..."
    (omitted if no strips)
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from orchestrator.historical import RawChat
from orchestrator.historical.context_header import ContextHeader
from orchestrator.historical.pair_cleanup import CleanedPair


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT_DIR = os.path.expanduser("~/Documents/Commercial AI archives")


# ---------------------------------------------------------------------------
# Status mapping for pasted-segment classification → file annotation
# ---------------------------------------------------------------------------

# Maps the Phase-1.3 segment classification to a status string the
# downstream extractors (Phase 3+4+5) read.
_STATUS_FOR_CLASS = {
    "news":           "extract-news",
    "opinion":        "extract-with-context",
    "resource":       "extract-resource",
    "earlier-draft":  "mention-only",
    "other":          "review",
    "":               "unclassified",
}


# ---------------------------------------------------------------------------
# YAML frontmatter
# ---------------------------------------------------------------------------


def _yaml_escape(value: str) -> str:
    """Escape a value for YAML inline output. Wraps in single quotes if
    it contains characters that would break flat-key YAML."""
    if value is None:
        return ""
    s = str(value)
    if not s:
        return ""
    needs_quote = any(c in s for c in ":#[]{},&*!|>'\"%@`\n") or s.strip() != s
    if needs_quote:
        return "'" + s.replace("'", "''") + "'"
    return s


def build_yaml_frontmatter(
    cleaned_pair:    CleanedPair,
    context_header:  ContextHeader,
    raw_chat:        RawChat,
    processed_at:    Optional[datetime] = None,
) -> str:
    """Compose the YAML frontmatter for a cleaned-pair file."""
    when = cleaned_pair.when or datetime.now()
    processed_at = processed_at or datetime.now()
    platform = (raw_chat.metadata.platform.value
                if raw_chat.metadata.platform else "unknown")
    source_chat = cleaned_pair.source_path or raw_chat.source_path or ""
    # Strip any leading absolute prefix to keep this portable.
    if source_chat:
        source_chat = source_chat.replace(os.path.expanduser("~/"), "~/")
    processing_model = ""
    if cleaned_pair.user_record and cleaned_pair.user_record.route:
        processing_model = cleaned_pair.user_record.route.model_id
    elif cleaned_pair.ai_record and cleaned_pair.ai_record.route:
        processing_model = cleaned_pair.ai_record.route.model_id

    lines = [
        "---",
        "nexus:",
        "type: cleaned-pair",
        f"date created: {when.strftime('%Y-%m-%d')}",
        f"date modified: {processed_at.strftime('%Y-%m-%d')}",
        f"source_chat: {_yaml_escape(source_chat)}",
        f"source_pair_num: {cleaned_pair.pair_num}",
        f"source_platform: {platform}",
        f"source_timestamp: {when.strftime('%Y-%m-%dT%H:%M:%S')}",
        f"thread_id: {context_header.thread_id}",
        f"prior_pair: {_yaml_escape(context_header.prior_pair_file)}",
        f"next_pair: {_yaml_escape(context_header.next_pair_file)}",
        f"processing_model: {_yaml_escape(processing_model)}",
        f"processed_at: {processed_at.strftime('%Y-%m-%dT%H:%M:%S')}",
        "tags: []",
        "---",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Body sections
# ---------------------------------------------------------------------------


def _format_pasted_segment_annotations(cleaned_pair: CleanedPair) -> str:
    """List pasted segments + their classifications + vault matches.

    Returns the empty string if no pasted segments exist.
    """
    pasted = [s for s in cleaned_pair.user_segments if s.kind == "pasted"]
    if not pasted:
        return ""
    out: list[str] = ["#### Pasted segments", ""]
    for i, seg in enumerate(pasted, start=1):
        cls = seg.classification or "unclassified"
        status = _STATUS_FOR_CLASS.get(cls, "review")
        first_line = (seg.content or "").splitlines()[0] if seg.content else ""
        marker = first_line[:60].strip() or "(empty)"
        out.append(f"- **Segment {i}** — type=`{cls}`, status=`{status}`")
        out.append(f"  - Source marker: `{marker}`")
        if seg.vault_match:
            vid = seg.vault_match.get("id", "?")
            vpath = seg.vault_match.get("vault_path", "?")
            overlap = seg.vault_match.get("overlap_ratio")
            overlap_pct = f"{int(overlap * 100)}%" if isinstance(overlap, float) else "?"
            out.append(f"  - Vault index match: `{vid}` (`{vpath}`) — overlap {overlap_pct}")
        else:
            out.append("  - Vault index match: none")
        if seg.heuristic_flags:
            flags = ", ".join(seg.heuristic_flags[:8])
            extra = f" (+{len(seg.heuristic_flags) - 8} more)" if len(seg.heuristic_flags) > 8 else ""
            out.append(f"  - Heuristic flags: {flags}{extra}")
        if seg.confidence:
            out.append(f"  - Confidence: {seg.confidence:.2f}")
        out.append(f"  - Length: {len(seg.content or '')} chars")
    return "\n".join(out) + "\n"


def _format_engagement_strip_log(cleaned_pair: CleanedPair) -> str:
    if not cleaned_pair.engagement_strips:
        return ""
    out: list[str] = ["#### Engagement strip log", ""]
    for rec in cleaned_pair.engagement_strips:
        snippet = (rec.paragraph or "").replace("\n", " ")[:80]
        if len(rec.paragraph) > 80:
            snippet += "..."
        out.append(
            f"- Stripped trailing paragraph ({rec.paragraph_length} chars): "
            f"\"{snippet}\""
        )
    return "\n".join(out) + "\n"


def build_body(
    cleaned_pair:    CleanedPair,
    context_header:  ContextHeader,
) -> str:
    """Compose the markdown body (Context + Exchange) for a cleaned-pair."""
    parts: list[str] = []

    # Context block
    parts.append("## Context\n")
    parts.append("### Session context\n")
    parts.append(context_header.session_context.strip() + "\n")
    parts.append("### Pair context\n")
    parts.append(context_header.pair_context.strip() + "\n")

    # Exchange block
    parts.append("## Exchange\n")

    parts.append("### User input\n")
    parts.append(cleaned_pair.cleaned_user_input.strip() + "\n")
    paste_block = _format_pasted_segment_annotations(cleaned_pair)
    if paste_block:
        parts.append(paste_block)

    parts.append("### Assistant response\n")
    parts.append(cleaned_pair.cleaned_ai_response.strip() + "\n")
    strip_block = _format_engagement_strip_log(cleaned_pair)
    if strip_block:
        parts.append(strip_block)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Top-level write
# ---------------------------------------------------------------------------


def build_cleaned_pair_markdown(
    cleaned_pair:    CleanedPair,
    context_header:  ContextHeader,
    raw_chat:        RawChat,
    processed_at:    Optional[datetime] = None,
) -> str:
    """Compose the full markdown content for a cleaned-pair file."""
    yaml_block = build_yaml_frontmatter(
        cleaned_pair, context_header, raw_chat, processed_at=processed_at,
    )
    body = build_body(cleaned_pair, context_header)
    return yaml_block + "\n" + body


def write_cleaned_pair_file(
    cleaned_pair:    CleanedPair,
    context_header:  ContextHeader,
    raw_chat:        RawChat,
    output_dir:      str = DEFAULT_OUTPUT_DIR,
    processed_at:    Optional[datetime] = None,
) -> str:
    """Write the cleaned-pair file to disk. Returns the absolute path
    written.

    Filename collision handling: if `<filename>` already exists, append
    `-pairNNN` to disambiguate.
    """
    output_root = Path(output_dir).expanduser()
    output_root.mkdir(parents=True, exist_ok=True)

    filename = context_header.pair_filename or "untitled.md"
    target = output_root / filename
    if target.exists():
        stem  = target.stem
        ext   = target.suffix
        target = output_root / f"{stem}-pair{cleaned_pair.pair_num:03d}{ext}"

    content = build_cleaned_pair_markdown(
        cleaned_pair, context_header, raw_chat, processed_at=processed_at,
    )
    target.write_text(content, encoding="utf-8")
    return str(target)


__all__ = [
    "DEFAULT_OUTPUT_DIR",
    "build_yaml_frontmatter",
    "build_body",
    "build_cleaned_pair_markdown",
    "write_cleaned_pair_file",
]
