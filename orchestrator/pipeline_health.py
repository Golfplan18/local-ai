"""Pipeline-execution warning surface.

Pipeline steps that detect a silent-degradation case (Phase A output
unparseable, RAG retrieval failure surviving as empty content, etc.)
record a warning here. The chat handler reads the collected warnings
after the turn completes and prepends a chat-visible banner so the
user knows what happened. Mirrors the ``oversight_health`` pattern
but for in-pipeline state rather than meta-layer state.

Storage is per-thread (each chat request runs on its own Flask
worker thread). The pipeline calls ``record(category, message)`` from
anywhere within the request; the chat handler calls
``collect_and_clear()`` at the end of the turn to drain the warnings
list and emit them as a banner. The list is reset on the next
``record`` after ``collect_and_clear`` runs.

Used by:
  - ``parse_step1_output`` (boot.py): records ``phase_a_parse_failed``
    when neither CLEANED PROMPT heading is found in the cleanup model's
    output. Surface gives the user a chance to notice that the pipeline
    ran against the cleaning model's narrative response, not their
    actual prompt.

Added 2026-05-22 to close silent-failure path S3.
"""
from __future__ import annotations

import threading
from typing import Optional


_tls = threading.local()


def record(category: str, message: str, **extra) -> None:
    """Append a warning to the current thread's pipeline-warnings list.

    ``category`` is a short identifier the chat handler can use to
    group warnings (e.g. ``phase_a_parse_failed``). ``message`` is the
    user-facing text. ``extra`` keys land in the warning dict for any
    downstream consumer that wants more detail.
    """
    if not hasattr(_tls, "warnings"):
        _tls.warnings = []
    warning = {"category": category, "message": message}
    warning.update(extra)
    _tls.warnings.append(warning)


def collect_and_clear() -> list[dict]:
    """Drain the current thread's pipeline-warnings list.

    Returns the warnings recorded during the in-flight chat turn and
    clears the list so the next turn starts fresh. Always safe to call
    — returns an empty list when nothing was recorded.
    """
    warnings = getattr(_tls, "warnings", [])
    _tls.warnings = []
    return warnings


def format_warnings_as_chat_note(warnings: list[dict]) -> str:
    """Format pipeline-health warnings as a markdown chat banner.

    Mirrors ``oversight_health.format_warnings_as_chat_note`` so the
    chat handler can render both kinds of warnings with a consistent
    visual treatment. Returns an empty string when there are no
    warnings.
    """
    if not warnings:
        return ""
    lines = ["> ⚠️ **Pipeline-execution warning**"]
    for w in warnings:
        lines.append(f"> - {w['message']}")
    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


__all__ = ["record", "collect_and_clear", "format_warnings_as_chat_note"]
