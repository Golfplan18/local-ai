"""rag_fit_gate.py — relevance fit-gate for retrieved RAG candidates.

The type-weighted ranker (`rag_engine.rank_vault_chunks`) scores chunks by
`similarity × provenance × recency`, but neither similarity nor provenance
can tell "on-topic" from "off-topic but vocabulary-close." A cosmology
engram can match a Japanese-garden art question on shared "emptiness /
space" vocabulary and — because it is a high-provenance engram — rank at
the top. See `Book — RAG Architecture Report v2.0` Process 13.

This module adds the missing precision step: a small fast model reads the
user's actual request alongside the retrieved candidates and marks each
KEEP or DROP with a one-line reason. It runs BEFORE the provenance ranker
(gate-first), so a high-provenance off-topic chunk is removed before
provenance can float it to the top.

Design:
- ONE batched model call per retrieval lane (all candidates in one prompt),
  not one call per candidate.
- Annotation only: `apply_fit_gate` sets `gate_verdict` / `gate_reason` on
  each chunk and returns the list; `rag_engine.rank_vault_chunks` does the
  actual dropping (and records the decision to the candidate trace).
- Fail-OPEN: any error, empty response, or unparseable line defaults to
  KEEP. A gate failure must never blank the RAG package — degrading to
  "keep everything" reproduces pre-gate behaviour, which is safe.
- The model caller is injected as `call_fn(system, user) -> str`, so this
  module has no dependency on the orchestrator's model dispatch (keeps it
  import-light, avoids a circular import, and is unit-testable with a stub).
"""

from __future__ import annotations

import re
import sys
from typing import Any, Callable


_GATE_SYSTEM_PROMPT = """You are a retrieval relevance filter for an analytical pipeline.

You are given a USER REQUEST and a numbered list of CANDIDATE context snippets that were retrieved from a knowledge base by vector similarity. Vector similarity matches on shared vocabulary, so some candidates will share words with the request while being about a different subject.

For each candidate, decide:
- KEEP — genuinely on-topic; would help an analyst address the request.
- DROP — about a different subject, even if it shares some words. (Example: a note about cosmology shares "space" and "observation" with a question about interior design, but it is a DROP.)

Judge topical relevance to the request's actual intent, not mere word overlap. Be strict about vocabulary-coincidence, but when you are genuinely unsure, KEEP — a later stage handles ranking, so only remove clear mismatches.

Output EXACTLY one line per candidate, in number order, and nothing else:
<n>: KEEP - <reason, 8 words or fewer>
or
<n>: DROP - <reason, 8 words or fewer>
"""


def _candidate_text(chunk: dict[str, Any], max_preview: int) -> str:
    body = chunk.get("document") or ""
    return " ".join(body.split())[:max_preview]


def _candidate_label(chunk: dict[str, Any]) -> str:
    meta = chunk.get("metadata") or {}
    return str(meta.get("source") or chunk.get("url") or chunk.get("id") or "unknown")


def _build_gate_messages(query: str, chunks: list[dict[str, Any]],
                         max_preview: int) -> tuple[str, str]:
    lines = [f"USER REQUEST:\n{(query or '').strip()}\n", "CANDIDATES:"]
    for i, c in enumerate(chunks, start=1):
        lines.append(f"{i}. [{_candidate_label(c)}] {_candidate_text(c, max_preview)}")
    return _GATE_SYSTEM_PROMPT, "\n".join(lines)


_VERDICT_RE = re.compile(r"^\s*(\d+)\s*[:.\)]\s*(keep|drop)\b(.*)$", re.IGNORECASE)


def _parse_gate_verdicts(text: str, n: int) -> list[tuple[str, str]]:
    """Parse the model's per-candidate verdicts into a list of length ``n``
    of ``(verdict, reason)``. Any candidate the model did not clearly mark
    DROP defaults to ``("keep", ...)`` — fail-open per item."""
    verdicts: list[tuple[str, str]] = [("keep", "no verdict returned (kept)")] * n
    if not text:
        return verdicts
    for line in text.splitlines():
        m = _VERDICT_RE.match(line)
        if not m:
            continue
        idx = int(m.group(1)) - 1
        if not (0 <= idx < n):
            continue
        verdict = m.group(2).lower()
        reason = (m.group(3) or "").strip(" \t-:–—").strip()[:120] or verdict
        verdicts[idx] = (verdict, reason)
    return verdicts


def apply_fit_gate(
    chunks: list[dict[str, Any]],
    query: str,
    *,
    call_fn: Callable[[str, str], str],
    max_preview: int = 300,
) -> list[dict[str, Any]]:
    """Annotate each chunk with ``gate_verdict`` ('keep'/'drop') and
    ``gate_reason``. Does NOT remove anything — ``rank_vault_chunks`` drops
    the 'drop'-verdict chunks and records the decision. Fail-open: any error
    marks every chunk 'keep' so the package is never blanked by a gate
    failure.
    """
    if not chunks:
        return chunks
    try:
        system, user = _build_gate_messages(query, chunks, max_preview)
        raw = call_fn(system, user)
        if not isinstance(raw, str) or raw.startswith("[Error"):
            raise RuntimeError(f"gate call returned non-answer: {raw!r:.80}")
        verdicts = _parse_gate_verdicts(raw, len(chunks))
    except Exception as exc:
        print(f"[rag_fit_gate] gate unavailable, failing open (keep all): "
              f"{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        for c in chunks:
            c["gate_verdict"] = "keep"
            c["gate_reason"] = "gate_unavailable_failopen"
        return chunks
    for c, (verdict, reason) in zip(chunks, verdicts):
        c["gate_verdict"] = verdict
        c["gate_reason"] = reason
    return chunks


def make_fit_gate(call_fn: Callable[[str, str], str], *, max_preview: int = 300):
    """Build the ``fit_gate(chunks, query)`` callable that
    ``rag_engine.assemble_ranked_context`` expects, closing over the injected
    model caller."""
    def _gate(chunks: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
        return apply_fit_gate(chunks, query, call_fn=call_fn, max_preview=max_preview)
    return _gate


__all__ = ["apply_fit_gate", "make_fit_gate"]
