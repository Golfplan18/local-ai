"""Engagement-wrapper strip (Phase 1.4).

Implements the strict 5-step rule locked in the architecture doc:

  For every AI response, after format cleanup:
    1. Identify the last paragraph.
    2. If it starts with a question → delete the entire last paragraph.
    3. If it contains any question anywhere in it → delete the entire
       last paragraph.
    4. Iterate from step 1 against the new last paragraph until the new
       last paragraph contains no questions.
    5. The cleaned response ends at the last question-free paragraph.

Bias is intentionally aggressive — the user accepts losses; the cost
of leaving a wrapper is higher than the cost of stripping content.

A `?` is treated as a question marker EXCEPT in code blocks, inline
code, and URLs. (Pre-sanitization step removes those before the
question check.)

Every strip is logged as JSONL to `~/ora/data/engagement-strips.log`
so the user can audit aggressive removals on the pilot batch.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

ENGAGEMENT_LOG_DEFAULT = os.path.expanduser("~/ora/data/engagement-strips.log")


# ---------------------------------------------------------------------------
# Strip record
# ---------------------------------------------------------------------------


@dataclass
class StripRecord:
    """One paragraph that was stripped from an AI response."""
    paragraph:        str        # the full original paragraph text
    paragraph_index:  int        # 0-based index from end (0=last, 1=second-last...)
    paragraph_length: int        # char count of stripped paragraph
    reason:           str        # always 'trailing-question' for now
    sanitized_text:   str = ""   # paragraph after url/code stripping (debug)


# ---------------------------------------------------------------------------
# Sanitization helpers
# ---------------------------------------------------------------------------

_CODE_FENCE_RE  = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_URL_RE         = re.compile(r"https?://\S+")


def _sanitize_for_question_check(text: str) -> str:
    """Remove code blocks, inline code, and URLs so their `?` chars
    don't trigger false positives."""
    text = _CODE_FENCE_RE.sub("", text)
    text = _INLINE_CODE_RE.sub("", text)
    text = _URL_RE.sub("", text)
    return text


def _has_question(paragraph: str) -> bool:
    """True if the paragraph contains any `?` after sanitization."""
    return "?" in _sanitize_for_question_check(paragraph)


# ---------------------------------------------------------------------------
# Paragraph splitting
# ---------------------------------------------------------------------------

_BLANK_LINE_RE = re.compile(r"\n\s*\n")


def _split_paragraphs(text: str) -> list[str]:
    """Split on blank lines, preserving non-empty paragraphs."""
    if not text:
        return []
    return [p.rstrip() for p in _BLANK_LINE_RE.split(text) if p.strip()]


# ---------------------------------------------------------------------------
# Strip
# ---------------------------------------------------------------------------


def strip_engagement(ai_response: str) -> tuple[str, list[StripRecord]]:
    """Apply the strict engagement-wrapper strip rule.

    Iterates from the end of the response, removing every trailing
    paragraph that contains a `?`. Stops when the new last paragraph is
    question-free, or when the response is empty.

    Returns (cleaned_response, strip_records). `strip_records` is in
    pop order — first record = last paragraph removed (initial last);
    subsequent records = the paragraphs revealed and stripped after.
    """
    paragraphs = _split_paragraphs(ai_response)
    if not paragraphs:
        return "", []

    strips: list[StripRecord] = []
    pop_index = 0
    while paragraphs:
        last = paragraphs[-1]
        if _has_question(last):
            strips.append(StripRecord(
                paragraph=last,
                paragraph_index=pop_index,
                paragraph_length=len(last),
                reason="trailing-question",
                sanitized_text=_sanitize_for_question_check(last)[:200],
            ))
            paragraphs.pop()
            pop_index += 1
        else:
            break

    cleaned = "\n\n".join(paragraphs)
    return cleaned, strips


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------


def log_strips(strip_records: list[StripRecord],
               *,
               context: Optional[dict] = None,
               log_path: str = ENGAGEMENT_LOG_DEFAULT) -> int:
    """Append strip records to the audit log as JSONL.

    `context` is a small dict identifying the source (source_path,
    pair_num, etc.) and is merged into each line for traceability.

    Returns the number of records written. No-op if `strip_records`
    is empty.
    """
    if not strip_records:
        return 0
    log_file = Path(log_path).expanduser()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    ctx = dict(context or {})
    written = 0
    with log_file.open("a", encoding="utf-8") as f:
        for record in strip_records:
            entry: dict[str, Any] = {
                "logged_at":        datetime.now().isoformat(timespec="seconds"),
                **ctx,
                "paragraph_index":  record.paragraph_index,
                "paragraph_length": record.paragraph_length,
                "reason":           record.reason,
                "paragraph":        record.paragraph,
                "sanitized_text":   record.sanitized_text,
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            written += 1
    return written


def strip_and_log(ai_response: str,
                   *,
                   context: Optional[dict] = None,
                   log_path: str = ENGAGEMENT_LOG_DEFAULT
                   ) -> tuple[str, list[StripRecord]]:
    """Convenience: strip engagement then log to file. Returns the
    same (cleaned, records) tuple as strip_engagement."""
    cleaned, records = strip_engagement(ai_response)
    log_strips(records, context=context, log_path=log_path)
    return cleaned, records


__all__ = [
    "ENGAGEMENT_LOG_DEFAULT",
    "StripRecord",
    "strip_engagement",
    "log_strips",
    "strip_and_log",
]
