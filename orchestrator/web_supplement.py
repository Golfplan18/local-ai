"""Step 2.5 — Anticipatory Web Supplement Loop.

Builds a web-supplemental context block during Step 2 (before the analyst
runs) so that vault + conversation + web context all arrive at the
analyst together. The existing mid-analysis Supplemental RAG Protocol
remains as a rare-case fallback when the upfront pass missed something.

Algorithm:

    1. Decision pass — a fast model call decides whether the prompt
       needs web supplement and, if yes, produces up to ``max_gaps``
       specific gaps each with an initial DDG query.

    2. For each gap, run up to ``max_attempts_per_gap`` cycles of:
         a. Search (DDG via web_search_structured; first attempt uses
            ``site:`` filter to high-provenance trusted domains; later
            attempts drop the filter for general DDG).
         b. Evaluate — the same fast model reads the snippets and either
            declares the gap ANSWERED (selecting relevant result indices)
            or proposes a reformulated query for the next attempt.

    3. All retained chunks are scored via
       ``rag_engine.score_external_chunks`` (whitelisted / corroborated /
       single / excluded per ``Reference — Trusted Web Sources``) and
       formatted with provenance markers via
       ``rag_engine.format_context_with_provenance``.

The module is dependency-injected: callers pass in ``call_model`` and
``get_endpoint`` so this code doesn't import ``orchestrator.boot``
(which imports ``rag_engine``, which would otherwise create a cycle).

See ``Reference — Trusted Web Sources.md`` for the trusted-source list
and ``Reference — Ora YAML Schema §15`` for the external-tier weight
table used by the ranker.
"""

from __future__ import annotations

import os
import re
import sys
import time
from typing import Any, Callable, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from rag_engine import (  # noqa: E402
    score_external_chunks,
    format_context_with_provenance,
)
from tools import web_corroboration  # noqa: E402
from tools.web_search import web_search_structured  # noqa: E402


# ---------------------------------------------------------------------------
# Configuration constants (overridable at call site via kwargs)
# ---------------------------------------------------------------------------

DEFAULT_MAX_GAPS = 3
DEFAULT_MAX_ATTEMPTS_PER_GAP = 2
DEFAULT_MAX_RESULTS_PER_SEARCH = 6
DEFAULT_MAX_CHARS = 12_000
DEFAULT_SLOT = "step1_cleanup"   # fast slot for the decision + eval passes

# Subset of trusted domains used as the ``site:`` filter on the first
# attempt per gap. Kept small (DDG handles 2–4 ``site:`` operators
# reliably; more degrades quality). The picker reads from the registered
# trusted-sources file at call time so this list automatically tracks
# changes to ``Reference — Trusted Web Sources``.
_GENERALIST_HINT_DOMAINS = (
    "en.wikipedia.org",
    "plato.stanford.edu",
    "iep.utm.edu",
    "www.britannica.com",
)


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_DECISION_SYSTEM_PROMPT = """\
You are deciding whether an analytical query needs supplemental web search before \
the main analytical pipeline runs. The pipeline already has access to the user's \
personal vault (philosophical and conceptual notes) and the recent conversation \
history. Your job is to decide whether the prompt also requires external \
information that the vault wouldn't carry.

Web supplement is appropriate for:
  - Recent events, news, current data (anything time-sensitive)
  - Specific statistics, facts, dates, named entities that need authoritative grounding
  - Subjects the user is asking about that are external to their own thinking
  - Named bills / court cases / products / organizations the user wants analyzed

Web supplement is NOT appropriate for:
  - Pure conceptual analysis (the vault carries the user's thinking)
  - Questions about the user's own work, projects, or previously-discussed ideas
  - Subjective / interpretive / philosophical questions with no factual ground

Output EXACTLY in one of these two shapes. Do not add prose outside the format.

When supplement IS needed:

NEEDS_WEB: yes
RATIONALE: <one sentence why>
GAPS:
- gap: <specific factual question this analysis needs answered>
  query: <DDG search string, 3-7 words>
- gap: <another specific factual question>
  query: <DDG search string>

When supplement is NOT needed:

NEEDS_WEB: no
RATIONALE: <one sentence why this is answerable without web>

Hard limits: at most {max_gaps} gaps. Each gap should be a distinct \
factual question; do not list overlapping or near-duplicate gaps. Each \
query should be search-engine-style (keywords, not natural language)."""


_DECISION_USER_TEMPLATE = """\
USER PROMPT:
{user_prompt}

RECENT CONVERSATION CONTEXT:
{conversation_context}"""


_EVAL_SYSTEM_PROMPT = """\
You requested a web search for a specific factual gap. Read the search \
results below and decide whether the gap is now answered.

Output EXACTLY in one of these two shapes. No prose outside the format.

When the gap IS answered:

ANSWERED: yes
RELEVANT: <comma-separated 1-indexed result numbers that are most relevant, e.g. "1,3,5">
RATIONALE: <one sentence>

When the gap is NOT answered:

ANSWERED: no
REFORMULATED_QUERY: <a different DDG search string, OR the literal word "stop" if you think no further search will help>
RATIONALE: <one short sentence>"""


_EVAL_USER_TEMPLATE = """\
GAP: {gap}
QUERY: "{query}"

SEARCH RESULTS:

{results_text}"""


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

_NEEDS_WEB_RE = re.compile(r"^NEEDS_WEB:\s*(yes|no)\s*$",
                            re.IGNORECASE | re.MULTILINE)
_GAP_BLOCK_RE = re.compile(
    r"^\s*-\s+gap:\s*(?P<gap>.+?)\s*\n\s+query:\s*(?P<query>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_RATIONALE_RE = re.compile(r"^RATIONALE:\s*(.+?)\s*$",
                            re.IGNORECASE | re.MULTILINE)
_ANSWERED_RE = re.compile(r"^ANSWERED:\s*(yes|no)\s*$",
                           re.IGNORECASE | re.MULTILINE)
_RELEVANT_RE = re.compile(r"^RELEVANT:\s*([\d, ]+)\s*$",
                           re.IGNORECASE | re.MULTILINE)
_REFORMULATED_RE = re.compile(r"^REFORMULATED_QUERY:\s*(.+?)\s*$",
                               re.IGNORECASE | re.MULTILINE)


def _parse_decision(text: str, max_gaps: int) -> dict:
    """Parse the decision-pass model output. Returns a structured dict.

    Tolerant of leading/trailing whitespace and minor format variation;
    strict about the load-bearing tokens (``NEEDS_WEB:``, ``RATIONALE:``,
    ``gap:`` / ``query:``). A failed parse degrades to "no web" rather
    than guessing — silent guessing would either over-fetch (cost) or
    fabricate gaps the prompt doesn't have.
    """
    if not text:
        return {"needs_web": False, "rationale": "empty model output",
                "gaps": [], "parse_failed": True}

    m = _NEEDS_WEB_RE.search(text)
    if not m:
        return {"needs_web": False,
                "rationale": "decision parse failed (no NEEDS_WEB line)",
                "gaps": [], "parse_failed": True}

    needs_web = m.group(1).lower() == "yes"
    rat_match = _RATIONALE_RE.search(text)
    rationale = rat_match.group(1).strip() if rat_match else ""

    gaps: list[dict] = []
    if needs_web:
        for gm in _GAP_BLOCK_RE.finditer(text):
            gaps.append({
                "gap":   gm.group("gap").strip(),
                "query": gm.group("query").strip().strip('"\''),
            })
            if len(gaps) >= max_gaps:
                break
        if not gaps:
            # Model said yes but emitted no parseable gaps — treat as no.
            return {"needs_web": False,
                    "rationale": "NEEDS_WEB=yes but no parseable gaps emitted",
                    "gaps": [], "parse_failed": True}

    return {"needs_web": needs_web, "rationale": rationale,
            "gaps": gaps, "parse_failed": False}


def _parse_evaluation(text: str, num_results: int) -> dict:
    """Parse the evaluation-pass model output."""
    if not text:
        return {"answered": False, "relevant_indices": [],
                "reformulated_query": None, "rationale": "empty model output",
                "parse_failed": True}

    m = _ANSWERED_RE.search(text)
    if not m:
        return {"answered": False, "relevant_indices": [],
                "reformulated_query": None,
                "rationale": "eval parse failed (no ANSWERED line)",
                "parse_failed": True}

    answered = m.group(1).lower() == "yes"
    rat_match = _RATIONALE_RE.search(text)
    rationale = rat_match.group(1).strip() if rat_match else ""

    indices: list[int] = []
    reformulated: Optional[str] = None

    if answered:
        rel_match = _RELEVANT_RE.search(text)
        if rel_match:
            for tok in rel_match.group(1).split(","):
                tok = tok.strip()
                if tok.isdigit():
                    idx = int(tok)
                    if 1 <= idx <= num_results:
                        # Convert to 0-indexed.
                        indices.append(idx - 1)
    else:
        rq_match = _REFORMULATED_RE.search(text)
        if rq_match:
            candidate = rq_match.group(1).strip().strip('"\'')
            if candidate.lower() != "stop":
                reformulated = candidate

    return {"answered": answered, "relevant_indices": indices,
            "reformulated_query": reformulated, "rationale": rationale,
            "parse_failed": False}


# ---------------------------------------------------------------------------
# Search helpers
# ---------------------------------------------------------------------------

def _site_filtered_query(query: str, hint_domains: tuple = _GENERALIST_HINT_DOMAINS) -> str:
    """Wrap a DDG query with a ``site:`` filter to a small set of trusted
    generalist domains. DDG's `OR` between site: operators is reasonably
    reliable at 2-4 domains; more than that degrades quality."""
    if not hint_domains:
        return query
    site_clause = " OR ".join(f"site:{d}" for d in hint_domains)
    return f"{query} ({site_clause})"


def _format_results_for_eval(results: list[dict]) -> str:
    """Pretty-print structured DDG results for the eval prompt."""
    if not results:
        return "(no results)"
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r.get('title', '(no title)')}")
        lines.append(f"   URL: {r.get('url', '')}")
        snippet = r.get("snippet", "").strip()
        if snippet:
            lines.append(f"   {snippet}")
        lines.append("")
    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def assemble_web_supplemental_context(
    user_prompt: str,
    *,
    call_model: Callable[[list, dict], str],
    fast_endpoint: Optional[dict],
    conversation_context: str = "",
    trusted_registry: Optional[web_corroboration.TrustedSourcesRegistry] = None,
    max_gaps: int = DEFAULT_MAX_GAPS,
    max_attempts_per_gap: int = DEFAULT_MAX_ATTEMPTS_PER_GAP,
    max_results_per_search: int = DEFAULT_MAX_RESULTS_PER_SEARCH,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict:
    """Run the Step 2.5 web-supplement loop.

    Args:
        user_prompt: the user's prompt (raw or Phase-A-cleaned).
        call_model: callable (messages, endpoint) → response string.
            Injected by the caller (typically ``boot.call_model``) so
            this module doesn't depend on boot directly.
        fast_endpoint: endpoint dict for the decision + eval passes
            (typically resolved from ``step1_cleanup``). When None,
            the supplement loop returns an empty result silently.
        conversation_context: recent conversation context, threaded into
            the decision prompt so the model can tell whether the user
            is asking a follow-up question that already has prior
            context in the thread.
        trusted_registry: TrustedSourcesRegistry instance for scoring.
            Defaults to a freshly-loaded instance.
        max_gaps: cap on gaps the decision pass can produce.
        max_attempts_per_gap: cap on search-and-evaluate cycles per gap.
        max_results_per_search: how many DDG results to fetch per call.
        max_chars: hard cap on the formatted output text.

    Returns:
        {
          "text": str,                     # formatted ## WEB CONTEXT body
          "decision": dict,                # parsed decision-pass output
          "gaps_processed": list[dict],    # per-gap trace
          "elapsed_seconds": float,
          "signals": list[str],            # one-line trace events
          "endpoint_used": str | None,
        }

    Failure modes:
      - fast_endpoint is None → returns empty text immediately.
      - Decision pass returns "no" → returns empty text after one call.
      - Decision parse fails → returns empty text + parse_failed signal.
      - Network errors during search → that attempt's results are []; the
        eval still runs and typically produces a reformulated query.
      - All gaps unresolved → returns text from whatever WAS resolved
        (or empty if zero gaps resolved).
    """
    t_start = time.time()
    signals: list[str] = []
    endpoint_name = (fast_endpoint or {}).get("name") if isinstance(fast_endpoint, dict) else None

    if not fast_endpoint:
        signals.append("web_supplement_skipped: no fast endpoint resolved")
        return {
            "text": "",
            "decision": {"needs_web": False, "rationale": "no fast endpoint",
                         "gaps": [], "parse_failed": False},
            "gaps_processed": [],
            "elapsed_seconds": time.time() - t_start,
            "signals": signals,
            "endpoint_used": None,
        }

    if trusted_registry is None:
        trusted_registry = web_corroboration.TrustedSourcesRegistry()

    # --- Decision pass --------------------------------------------------
    decision_system = _DECISION_SYSTEM_PROMPT.format(max_gaps=max_gaps)
    decision_user = _DECISION_USER_TEMPLATE.format(
        user_prompt=user_prompt or "(empty)",
        conversation_context=conversation_context or "(none)",
    )
    try:
        decision_raw = call_model(
            [{"role": "system", "content": decision_system},
             {"role": "user",   "content": decision_user}],
            fast_endpoint,
        )
    except Exception as exc:
        signals.append(f"web_supplement_decision_call_error: {exc}")
        return {
            "text": "",
            "decision": {"needs_web": False, "rationale": f"decision call error: {exc}",
                         "gaps": [], "parse_failed": True},
            "gaps_processed": [],
            "elapsed_seconds": time.time() - t_start,
            "signals": signals,
            "endpoint_used": endpoint_name,
        }

    decision = _parse_decision(decision_raw or "", max_gaps=max_gaps)
    signals.append(
        f"web_supplement_decision: needs_web={decision['needs_web']}, "
        f"gaps={len(decision.get('gaps', []))}, "
        f"parse_failed={decision.get('parse_failed', False)}"
    )

    if not decision["needs_web"] or not decision["gaps"]:
        return {
            "text": "",
            "decision": decision,
            "gaps_processed": [],
            "elapsed_seconds": time.time() - t_start,
            "signals": signals,
            "endpoint_used": endpoint_name,
        }

    # --- Per-gap search + evaluate loop --------------------------------
    all_chunks: list[dict] = []
    gaps_processed: list[dict] = []

    for gap_entry in decision["gaps"]:
        gap_text  = gap_entry["gap"]
        initial_q = gap_entry["query"]

        attempts: list[dict] = []
        resolved = False
        retained_chunks_for_gap: list[dict] = []
        current_query = initial_q

        for attempt_idx in range(max_attempts_per_gap):
            # First attempt: try with site: filter to trusted generalists.
            # Subsequent attempts: drop the filter for a general DDG search.
            if attempt_idx == 0:
                effective_query = _site_filtered_query(current_query)
                used_filter = True
            else:
                effective_query = current_query
                used_filter = False

            results = web_search_structured(
                effective_query, max_results=max_results_per_search,
            )

            # Run the eval pass even when results is empty — the model
            # gets to see "(no results)" and can propose a different query.
            eval_user = _EVAL_USER_TEMPLATE.format(
                gap=gap_text,
                query=effective_query,
                results_text=_format_results_for_eval(results),
            )
            try:
                eval_raw = call_model(
                    [{"role": "system", "content": _EVAL_SYSTEM_PROMPT},
                     {"role": "user",   "content": eval_user}],
                    fast_endpoint,
                )
            except Exception as exc:
                signals.append(
                    f"web_supplement_eval_call_error: gap={gap_text[:40]!r} "
                    f"attempt={attempt_idx + 1}: {exc}"
                )
                attempts.append({
                    "attempt": attempt_idx + 1,
                    "query": effective_query,
                    "site_filter": used_filter,
                    "result_count": len(results),
                    "answered": False,
                    "eval_call_failed": True,
                })
                break

            eval_parsed = _parse_evaluation(eval_raw or "", num_results=len(results))
            attempts.append({
                "attempt": attempt_idx + 1,
                "query": effective_query,
                "site_filter": used_filter,
                "result_count": len(results),
                "answered": eval_parsed["answered"],
                "relevant_indices": eval_parsed["relevant_indices"],
                "rationale": eval_parsed["rationale"],
                "parse_failed": eval_parsed["parse_failed"],
            })

            if eval_parsed["answered"]:
                # Retain only the indices the model marked relevant —
                # snippets carry an embed-similarity proxy of 1.0 since
                # they came from a targeted search the model just
                # confirmed; score_external_chunks downweights based on
                # provenance, not similarity.
                keep_idx = eval_parsed["relevant_indices"] or list(range(len(results)))
                for i in keep_idx:
                    if 0 <= i < len(results):
                        r = results[i]
                        retained_chunks_for_gap.append({
                            "url":        r["url"],
                            "similarity": 1.0,
                            "document":   _result_to_document(r),
                        })
                resolved = True
                break

            # Not answered — switch to the model's reformulated query
            # for the next attempt, or stop if the model said "stop" or
            # gave no reformulation.
            next_q = eval_parsed["reformulated_query"]
            if not next_q:
                signals.append(
                    f"web_supplement_gap_stopped_by_model: {gap_text[:60]!r}"
                )
                break
            current_query = next_q

        gaps_processed.append({
            "gap": gap_text,
            "initial_query": initial_q,
            "attempts": attempts,
            "resolved": resolved,
            "chunks_retained": len(retained_chunks_for_gap),
        })
        all_chunks.extend(retained_chunks_for_gap)

    resolved_count = sum(1 for g in gaps_processed if g["resolved"])
    signals.append(
        f"web_supplement_summary: gaps_total={len(gaps_processed)}, "
        f"resolved={resolved_count}, chunks={len(all_chunks)}"
    )

    # --- Score + format -------------------------------------------------
    if all_chunks:
        all_urls = [c["url"] for c in all_chunks]
        scored = score_external_chunks(
            all_chunks, all_urls=all_urls, registry=trusted_registry,
        )
        text = format_context_with_provenance(scored, max_chars=max_chars)
    else:
        text = ""

    return {
        "text": text,
        "decision": decision,
        "gaps_processed": gaps_processed,
        "elapsed_seconds": time.time() - t_start,
        "signals": signals,
        "endpoint_used": endpoint_name,
    }


def _result_to_document(result: dict) -> str:
    """Render one DDG result as the ``document`` body the formatter consumes.

    The snippet + title gives the analyst enough surface area without
    requiring a page fetch (which is a v2 concern). The URL is recorded
    separately via the chunk's ``url`` field — the formatter prepends a
    provenance marker that names the source.
    """
    title = (result.get("title") or "").strip()
    snippet = (result.get("snippet") or "").strip()
    if title and snippet:
        return f"**{title}**\n{snippet}"
    return title or snippet or "(no content)"


__all__ = [
    "assemble_web_supplemental_context",
    "DEFAULT_MAX_GAPS",
    "DEFAULT_MAX_ATTEMPTS_PER_GAP",
    "DEFAULT_MAX_RESULTS_PER_SEARCH",
    "DEFAULT_MAX_CHARS",
    "DEFAULT_SLOT",
]
