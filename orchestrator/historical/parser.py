"""Raw chat format parser for Phase 1 of historical reprocessing.

Handles two formats:

1.  Web-Clipper format (Claude.ai / ChatGPT / Gemini exports via the
    Obsidian Web Clipper template). Identified by `<i>[ts]</i> 👉 <b>👤
    User</b>:` turn markers and an `## Overview` block carrying URL +
    metadata. Roughly 99% of the historical archive.

2.  Live Ora format (output of `server.py::_save_conversation`).
    Identified by `<!-- pair NNN | timestamp -->` markers and
    `**User:**` / `**Assistant:**` role headers. ~4% of the archive.

The parser auto-detects the format and returns a `RawChat` with
metadata + ordered turns. Pairing into `RawPair` happens via
`RawChat.to_pairs()` (handles multi-assistant turns where tool calls
precede a final answer).

Output is RAW — HTML noise (`<br>`, `<i>` tags), search-call clutter,
duplicate timestamps, etc. are NOT stripped here. Cleanup happens in
later phases.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import (
    Platform,
    RawChat,
    RawChatMetadata,
    RawTurn,
)


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

_WEB_CLIPPER_TURN_RE = re.compile(
    # The 👉 separator and the role emoji are both optional — Gemini exports
    # often omit 👉 and ChatGPT/Claude include it. Either way we anchor on
    # the timestamp + bold role tag.
    r"<i>\[(?P<ts>[^\]]+)\]</i>\s*(?:👉\s*)?<b>\s*"
    r"(?:(?P<emoji>👤|🤖)\s*)?"
    r"(?P<role>User|Assistant)\s*</b>\s*:?",
    re.IGNORECASE,
)

# Gemini exports wrap each assistant turn in `<details><summary>...</summary>
# <full text>...</details>`. The summary is a truncated preview of the full
# text that follows; if we don't strip the summary we double-count every
# assistant turn (once truncated, once full). The cleanest fix is to delete
# the `<details>` opening tag and the `<summary>...</summary>` block, leaving
# the full content + closing `</details>` visible.
_GEMINI_DETAILS_OPEN_RE = re.compile(
    r"<details\b[^>]*>", re.IGNORECASE,
)
_GEMINI_DETAILS_CLOSE_RE = re.compile(
    r"</details>", re.IGNORECASE,
)
_GEMINI_SUMMARY_BLOCK_RE = re.compile(
    r"<summary\b[^>]*>.*?</summary>", re.IGNORECASE | re.DOTALL,
)


def _strip_gemini_details_wrappers(text: str) -> str:
    """Remove `<details>` / `</details>` tags and `<summary>...</summary>`
    truncated-preview blocks that Gemini exports use for folding.

    Idempotent on text that has no Gemini wrappers."""
    text = _GEMINI_SUMMARY_BLOCK_RE.sub("", text)
    text = _GEMINI_DETAILS_OPEN_RE.sub("", text)
    text = _GEMINI_DETAILS_CLOSE_RE.sub("", text)
    return text

_LIVE_ORA_PAIR_RE = re.compile(
    r"<!--\s*pair\s+\d+\s*\|\s*[^>]+?\s*-->",
    re.IGNORECASE,
)


def detect_format(text: str) -> str:
    """Return 'web-clipper', 'live-ora', or 'unknown'.

    Web-Clipper dominates if the angle-bracket emoji turn markers appear.
    Falls back to live-Ora if pair-comment markers appear. Otherwise
    'unknown'.
    """
    if _WEB_CLIPPER_TURN_RE.search(text):
        return "web-clipper"
    if _LIVE_ORA_PAIR_RE.search(text):
        return "live-ora"
    return "unknown"


# ---------------------------------------------------------------------------
# YAML frontmatter
# ---------------------------------------------------------------------------

_YAML_FENCE_RE = re.compile(r"\A---\s*\n(.*?\n)---\s*\n", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Minimal YAML parser shared with vault_indexer (kept local to
    avoid a cross-tool import that pulls in unrelated machinery)."""
    m = _YAML_FENCE_RE.match(text)
    if not m:
        return {}, text
    yaml_text = m.group(1)
    body = text[m.end():]
    yaml_dict: dict = {}
    current_list: Optional[str] = None
    for line in yaml_text.split("\n"):
        if not line.strip():
            current_list = None
            continue
        list_m = re.match(r"^\s*-\s+(.*)$", line)
        if list_m and current_list:
            yaml_dict.setdefault(current_list, []).append(
                list_m.group(1).strip().strip('"\''))
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"\'')
            if value:
                yaml_dict[key] = value
                current_list = None
            else:
                current_list = key
                yaml_dict[key] = []
    return yaml_dict, body


# ---------------------------------------------------------------------------
# Timestamp parsing
# ---------------------------------------------------------------------------

# Web-Clipper timestamps look like "7/14/2025, 9:05:34 PM" or
# "12/26/2024, 6:39:09 PM". Sometimes the format is YYYY-MM-DD HH:MM:SS.
_TS_FORMATS = (
    "%m/%d/%Y, %I:%M:%S %p",
    "%m/%d/%Y, %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d",
)


def _parse_timestamp(value: str) -> Optional[datetime]:
    """Best-effort timestamp parse. Returns None on failure."""
    if not value:
        return None
    value = value.strip()
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except (ValueError, TypeError):
            continue
    return None


# ---------------------------------------------------------------------------
# Web-Clipper format parser
# ---------------------------------------------------------------------------

# Overview block field patterns.
# IMPORTANT: use `[ \t]*` (not `\s*`) for whitespace immediately after the
# closing `**` and `[^\n]*` for the value — `\s` matches newlines and would
# greedily consume the line ending, letting `val` capture content from the
# NEXT line (observed bug: an empty `**Title:**` field stole the URL line).
_OVERVIEW_FIELD_RE = re.compile(
    r"^\s*-\s*\*\*(?P<key>[^*]+):\*\*[ \t]*(?P<val>[^\n]*)$",
    re.MULTILINE,
)
_OVERVIEW_URL_RE = re.compile(
    r"\*\*Url:\*\*\s*\[?(?P<url>[^\]\s]+)",
    re.MULTILINE,
)


def _detect_platform_from_url(url: str, fallback_filename: str = "") -> Platform:
    """Match URL against known platform domains; fall back to filename."""
    url_lower = url.lower() if url else ""
    if "claude.ai" in url_lower:
        return Platform.CLAUDE
    if "chatgpt.com" in url_lower or "openai.com" in url_lower:
        return Platform.CHATGPT
    if "gemini.google.com" in url_lower or "bard.google.com" in url_lower:
        return Platform.GEMINI
    name_lower = fallback_filename.lower()
    if name_lower.startswith("claude "):
        return Platform.CLAUDE
    if name_lower.startswith("chatgpt "):
        return Platform.CHATGPT
    if name_lower.startswith("gemini "):
        return Platform.GEMINI
    return Platform.UNKNOWN


def _extract_web_clipper_metadata(yaml_meta: dict, body: str,
                                    source_path: str) -> RawChatMetadata:
    md = RawChatMetadata(
        yaml_frontmatter=yaml_meta,
        title=yaml_meta.get("title", "") or "",
    )
    # Try to harvest the Overview block (above the Conversation section).
    overview_match = re.search(
        r"##\s*Overview\s*\n(.*?)(?=^##\s|\Z)",
        body, re.DOTALL | re.MULTILINE,
    )
    overview_text = overview_match.group(1) if overview_match else ""
    if overview_text:
        # Url
        url_m = _OVERVIEW_URL_RE.search(overview_text)
        if url_m:
            md.url = url_m.group("url").strip()
        # Other fields
        for field_m in _OVERVIEW_FIELD_RE.finditer(overview_text):
            key = field_m.group("key").strip().lower()
            val = field_m.group("val").strip()
            if key == "title" and val:
                md.title = val
            elif key == "id":
                md.conversation_id = val
            elif key == "created":
                ts = _parse_timestamp(val)
                if ts:
                    md.created_at = ts
            elif key == "last updated":
                ts = _parse_timestamp(val)
                if ts:
                    md.last_updated = ts
            elif key == "total messages":
                try:
                    md.total_messages = int(val)
                except ValueError:
                    pass
    fname = os.path.basename(source_path)
    md.platform = _detect_platform_from_url(md.url, fallback_filename=fname)
    if not md.conversation_id:
        # Fallback to URL slug or filename stem.
        if md.url:
            md.conversation_id = md.url.rstrip("/").rsplit("/", 1)[-1][:32]
        else:
            md.conversation_id = Path(fname).stem[:32]
    return md


def _parse_web_clipper_turns(body: str,
                               default_when: Optional[datetime] = None
                               ) -> list[RawTurn]:
    """Parse turn markers in the Web-Clipper format and slice content.

    Each turn marker starts a new turn; content runs until the next
    marker (or end of text). Multiple Assistant turns following one
    User turn are kept as separate RawTurns; pairing merges them.
    """
    # Restrict to the body after `## Conversation` if that section exists.
    conv_match = re.search(
        r"##\s*Conversation\s*\n(.*)\Z",
        body, re.DOTALL | re.MULTILINE,
    )
    scope = conv_match.group(1) if conv_match else body
    # Strip Gemini's <details>/<summary> wrappers so we don't double-count
    # each assistant turn (the summary is a truncated preview of what
    # follows). No-op for Claude/ChatGPT.
    scope = _strip_gemini_details_wrappers(scope)

    cuts: list[tuple[int, int, str, str]] = []
    for m in _WEB_CLIPPER_TURN_RE.finditer(scope):
        ts_text = m.group("ts")
        role = m.group("role").lower()
        cuts.append((m.start(), m.end(), ts_text, role))
    if not cuts:
        return []

    turns: list[RawTurn] = []
    for i, (start, after_marker, ts_text, role) in enumerate(cuts):
        end = cuts[i + 1][0] if i + 1 < len(cuts) else len(scope)
        # Content runs from end-of-marker to next marker.
        raw_segment = scope[start:end]
        content = scope[after_marker:end].strip()
        # Remove trailing <br> noise — keep text otherwise raw.
        content = re.sub(r"<br\s*/?>\s*\Z", "", content).strip()
        ts = _parse_timestamp(ts_text) or default_when
        turns.append(RawTurn(
            role=role,
            content=content,
            timestamp=ts,
            raw_text=raw_segment,
        ))
    return turns


def parse_web_clipper(text: str, source_path: str = "") -> RawChat:
    """Parse a Web-Clipper format chat file."""
    yaml_meta, body = _parse_frontmatter(text)
    metadata = _extract_web_clipper_metadata(yaml_meta, body, source_path)
    default_when = metadata.created_at
    turns = _parse_web_clipper_turns(body, default_when=default_when)
    return RawChat(
        source_path=source_path,
        metadata=metadata,
        turns=turns,
    )


# ---------------------------------------------------------------------------
# Live-Ora format parser
# ---------------------------------------------------------------------------

_LIVE_ORA_PAIR_FULL_RE = re.compile(
    r"<!--\s*pair\s+(\d+)\s*\|\s*([^>]+?)\s*-->",
    re.IGNORECASE,
)


def parse_live_ora(text: str, source_path: str = "") -> RawChat:
    """Parse a live-Ora format chat file (the format
    `_save_conversation` writes).
    """
    yaml_meta, body = _parse_frontmatter(text)
    metadata = RawChatMetadata(
        yaml_frontmatter=yaml_meta,
        title=yaml_meta.get("title", "") or Path(source_path).stem,
        platform=Platform.ORA,
    )
    # Pull session id from "# Session <id>" if present.
    sess_m = re.search(r"#\s*Session\s+([A-Za-z0-9\-]+)", body)
    if sess_m:
        metadata.conversation_id = sess_m.group(1)

    cuts = list(_LIVE_ORA_PAIR_FULL_RE.finditer(body))
    if not cuts:
        return RawChat(source_path=source_path, metadata=metadata, turns=[])

    turns: list[RawTurn] = []
    for i, m in enumerate(cuts):
        start = m.start()
        end = cuts[i + 1].start() if i + 1 < len(cuts) else len(body)
        block = body[start:end]
        ts_text = m.group(2)
        ts = _parse_timestamp(ts_text)
        # Strip the comment header itself
        block_stripped = _LIVE_ORA_PAIR_FULL_RE.sub("", block, count=1).strip()
        # Strip trailing --- separator
        block_stripped = re.sub(r"\n---\s*\Z", "", block_stripped).strip()

        user_match = re.search(
            r"\*\*User:\*\*\s*(.+?)(?=\n\s*\*\*Assistant:\*\*|\Z)",
            block_stripped, re.DOTALL,
        )
        asst_match = re.search(
            r"\*\*Assistant:\*\*\s*(.+?)\Z",
            block_stripped, re.DOTALL,
        )
        if user_match:
            turns.append(RawTurn(
                role="user",
                content=user_match.group(1).strip(),
                timestamp=ts,
                raw_text=block,
            ))
        if asst_match:
            turns.append(RawTurn(
                role="assistant",
                content=asst_match.group(1).strip(),
                timestamp=ts,
                raw_text=block,
            ))
    return RawChat(
        source_path=source_path,
        metadata=metadata,
        turns=turns,
    )


# ---------------------------------------------------------------------------
# Top-level dispatch
# ---------------------------------------------------------------------------


def parse_raw_chat(text: str, source_path: str = "") -> RawChat:
    """Auto-detect format and parse. Returns RawChat (possibly empty)."""
    fmt = detect_format(text)
    if fmt == "web-clipper":
        return parse_web_clipper(text, source_path=source_path)
    if fmt == "live-ora":
        return parse_live_ora(text, source_path=source_path)
    yaml_meta, _ = _parse_frontmatter(text)
    return RawChat(
        source_path=source_path,
        metadata=RawChatMetadata(
            yaml_frontmatter=yaml_meta,
            title=yaml_meta.get("title", "") or Path(source_path).stem,
            platform=Platform.UNKNOWN,
        ),
        turns=[],
    )


def parse_raw_chat_file(path: str) -> RawChat:
    """Convenience: read file and parse."""
    text = Path(path).expanduser().read_text(encoding="utf-8", errors="replace")
    return parse_raw_chat(text, source_path=str(path))


__all__ = [
    "detect_format",
    "parse_raw_chat",
    "parse_raw_chat_file",
    "parse_web_clipper",
    "parse_live_ora",
]
