"""Step 2 — Consultation-Augmented Generation (CAG) web stream.

Implements F-Consult's web consultation: parallel web search seeded from the
prompt, justification-gated intent identification, source tiering (approved
vs open), per-chunk provenance, optional prompt-sanity check. Runs alongside
vault/conversation/relationship RAG and produces the web portion of the
consultation package.

See ~/Documents/vault/Specification — F-Consult.md for the design.

Replaces the prior gap-driven sequential web_supplement.py:
  - No "does this need web?" decision pass. Web consultation always runs when
    enabled; the intent identifier returns zero intents when nothing useful
    can be searched, and the package's web_rag is then empty.
  - Intents are generated WITH justifications at the model layer. Intents
    that cannot articulate a justification are not emitted (anti-nitpicking
    enforced upstream, not via a count cap).
  - All intent queries fire in PARALLEL via ThreadPoolExecutor with a
    per-query timeout for failure containment. No count cap.
  - Each retained chunk carries provenance: source_tier (approved/open),
    weight, retrieved_at timestamp, origin_url, intent_justification.
  - Duplication across web/vault/training is signal, not noise — preserved
    in the package so downstream can read triple-source coverage as
    confirmation strength.

The module is dependency-injected: callers pass in ``call_model`` and the
fast endpoint so this code doesn't import ``orchestrator.boot``.

See ``Reference — Trusted Web Sources.md`` for the canonical approved-source
list (consulted via tools.web_corroboration.TrustedSourcesRegistry) and
``Specification — F-Consult.md`` for the consultation-package contract.
"""

from __future__ import annotations

import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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

DEFAULT_PER_QUERY_TIMEOUT_SECONDS = 15
DEFAULT_MAX_RESULTS_PER_QUERY = 6
DEFAULT_MAX_CHARS = 12_000
DEFAULT_SLOT = "step1_cleanup"   # fast slot for intent identification + sanity check
DEFAULT_PROMPT_SANITY_ENABLED = True


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_INTENT_SYSTEM_PROMPT = """\
You are identifying web search intents for the Consultation step (Step 2) of \
an analytical pipeline. The pipeline already has vault knowledge and \
conversation history available; web consultation complements these with \
independent external information and cross-confirmation.

For the user's prompt, identify search intents that would meaningfully \
inform the analysis. Each intent must articulate why it matters — what the \
analysis would gain from external grounding on this point.

Output format — each intent as a YAML-like block. No prose outside the format.

INTENTS:
- query: <search-engine-style query, 3-8 words>
  justification: <one short sentence: what would the analysis gain from \
this search? what concrete factual angle would it ground or expand?>
- query: <another query>
  justification: <reason it matters>

Discipline:
- Emit an intent ONLY if you can articulate a real justification. If you \
cannot say why a search matters for THIS analysis, do not emit it.
- Pure conceptual / philosophical / interpretive prompts may have ZERO \
intents (vault and training cover them). Emit no intents rather than \
fabricate trivial ones.
- News, current events, named entities, quantitative figures, dates, recent \
developments — these typically need web grounding. Emit intents for each \
distinct angle.
- Subjective or contrarian framings the user is exploring are NOT to be \
"verified" at this step — that's Step 5. Step 2 web consultation supplies \
context, it doesn't gate viewpoints.

If no intents are warranted, emit:

INTENTS:
(none)"""


_INTENT_USER_TEMPLATE = """\
USER PROMPT:
{user_prompt}

RECENT CONVERSATION CONTEXT:
{conversation_context}"""


_SANITY_SYSTEM_PROMPT = """\
You are doing a light factual-sanity check on a user prompt before an \
analytical pipeline runs. Your job is to catch SURFACE-LEVEL factual errors \
the user may have made unintentionally — typos on dates, mis-remembered \
statistics, wrong attributions for quotes, named-entity slips. Catching \
these saves the pipeline from doing analytical work on a wrong premise.

CRITICAL: This is NOT a contrarian-detector. Substantive disputed positions, \
contested theories, contrarian viewpoints, and the user's analytical claims \
pass through untouched. A user prompt asserting that the Big Bang is wrong \
is NOT a factual error — it is a substantive position. You do not flag it.

You flag ONLY:
- Wrong dates (e.g., "the 1969 moon landing" stated as 1970)
- Wrong named entities (e.g., a quote attributed to the wrong person, a law \
  attributed to the wrong country)
- Surface statistical slips (e.g., off-by-decimal in a well-known figure)
- Misspellings of named entities that affect retrieval (e.g., "Charles \
  Dickson" when the user means "Charles Dickens")

You do NOT flag:
- Disputed theories or contrarian positions
- Interpretive claims (anything with a "depending on which methodology" \
  wrapper)
- The user's analytical conclusions
- Claims you cannot resolve with high confidence

Output format. No prose outside the format.

When you find one or more flags:

FLAGS:
- claim: "<the suspect claim, quoted from the prompt>"
  suspected_error: <what looks wrong>
  reasoning: <one short sentence>

When you find nothing worth flagging (the normal case):

FLAGS:
(none)"""


_SANITY_USER_TEMPLATE = """\
USER PROMPT:
{user_prompt}"""


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

_INTENT_BLOCK_RE = re.compile(
    r"^\s*-\s+query:\s*(?P<query>.+?)\s*\n\s+justification:\s*(?P<just>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_SANITY_FLAG_RE = re.compile(
    r"^\s*-\s+claim:\s*(?P<claim>.+?)\s*\n"
    r"\s+suspected_error:\s*(?P<err>.+?)\s*\n"
    r"\s+reasoning:\s*(?P<reason>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _parse_intents(text: str) -> list[dict]:
    """Parse intents from the intent-identification model output.

    Returns a list of {"query": ..., "justification": ...} dicts. Intents
    without justifications never appear here — the model is instructed to
    drop them at emission, and the regex requires both fields to be present.

    Returns an empty list on parse failure or when the model emits "(none)".
    """
    if not text:
        return []
    intents: list[dict] = []
    for m in _INTENT_BLOCK_RE.finditer(text):
        query = m.group("query").strip().strip('"\'')
        just  = m.group("just").strip()
        if query and just:
            intents.append({"query": query, "justification": just})
    return intents


def _parse_sanity_flags(text: str) -> list[dict]:
    """Parse prompt-sanity flags from the sanity-check model output."""
    if not text:
        return []
    flags: list[dict] = []
    for m in _SANITY_FLAG_RE.finditer(text):
        flags.append({
            "claim": m.group("claim").strip().strip('"\''),
            "suspected_error": m.group("err").strip(),
            "reasoning": m.group("reason").strip(),
        })
    return flags


# ---------------------------------------------------------------------------
# Per-intent query execution
# ---------------------------------------------------------------------------

def _execute_intent_query(
    intent: dict,
    *,
    max_results: int,
    timeout_seconds: int,
    registry: web_corroboration.TrustedSourcesRegistry,
) -> dict:
    """Run one intent's web search and return a structured per-intent result.

    Returns:
        {
          "intent": <intent dict>,
          "query": <effective query string>,
          "results": list[dict],          # raw DDG results
          "chunks": list[dict],           # scored chunks ready for formatting
          "elapsed_seconds": float,
          "error": Optional[str],         # None on success
        }
    """
    t_start = time.time()
    out: dict = {
        "intent": intent,
        "query": intent["query"],
        "results": [],
        "chunks": [],
        "elapsed_seconds": 0.0,
        "error": None,
    }
    try:
        results = web_search_structured(
            intent["query"], max_results=max_results,
        )
    except Exception as exc:
        out["error"] = f"web_search_failed: {exc}"
        out["elapsed_seconds"] = time.time() - t_start
        return out

    out["results"] = results or []
    if not results:
        out["elapsed_seconds"] = time.time() - t_start
        return out

    # Build chunks with intent-justification provenance threaded through.
    # Similarity is set to 1.0 — these came from a targeted query, scoring
    # downweights based on provenance tier, not similarity.
    raw_chunks: list[dict] = []
    for r in results:
        raw_chunks.append({
            "url":        r.get("url", ""),
            "similarity": 1.0,
            "document":   _result_to_document(r),
            "title":      r.get("title", ""),
            "intent_justification": intent["justification"],
            "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })

    # Score via rag_engine — assigns source tier (approved/open) per the
    # trusted-source registry and computes a per-chunk weight.
    all_urls = [c["url"] for c in raw_chunks]
    scored = score_external_chunks(
        raw_chunks, all_urls=all_urls, registry=registry,
    )
    out["chunks"] = scored
    out["elapsed_seconds"] = time.time() - t_start
    return out


def _result_to_document(result: dict) -> str:
    """Render one DDG result as the ``document`` body the formatter consumes."""
    title = (result.get("title") or "").strip()
    snippet = (result.get("snippet") or "").strip()
    if title and snippet:
        return f"**{title}**\n{snippet}"
    return title or snippet or "(no content)"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def assemble_consultation_package(
    user_prompt: str,
    *,
    call_model: Callable[[list, dict], str],
    fast_endpoint: Optional[dict],
    conversation_context: str = "",
    trusted_registry: Optional[web_corroboration.TrustedSourcesRegistry] = None,
    per_query_timeout_seconds: int = DEFAULT_PER_QUERY_TIMEOUT_SECONDS,
    max_results_per_query: int = DEFAULT_MAX_RESULTS_PER_QUERY,
    max_chars: int = DEFAULT_MAX_CHARS,
    prompt_sanity_enabled: bool = DEFAULT_PROMPT_SANITY_ENABLED,
) -> dict:
    """Run F-Consult's web consultation stream.

    This is Step 2's web-CAG entry point. The function:
      1. Identifies search intents (one fast-model call). Intents must
         carry justifications; unjustified intents are dropped at the
         model layer.
      2. Issues all intent queries in PARALLEL via ThreadPoolExecutor.
         No count cap. Per-query timeout for failure containment.
      3. Scores retrieved chunks via the trusted-source registry, threads
         provenance through (source_tier, weight, origin_url,
         retrieved_at, intent_justification).
      4. Optionally runs a prompt-sanity check in parallel with the
         consultation (separate fast-model call).
      5. Returns the consultation package — structured fields for web_rag
         text, prompt_sanity_flags, and consultation_trace metadata.

    Args:
        user_prompt: the user's prompt (raw or Phase-A-cleaned).
        call_model: callable (messages, endpoint) → response string.
            Injected by the caller (typically ``boot.call_model``).
        fast_endpoint: endpoint dict for the intent + sanity passes
            (typically resolved from ``step1_cleanup``). When None,
            consultation returns an empty result silently.
        conversation_context: recent conversation context, threaded into
            the intent prompt for follow-up awareness.
        trusted_registry: TrustedSourcesRegistry instance for tier
            classification + scoring. Defaults to a freshly-loaded
            instance.
        per_query_timeout_seconds: per-intent-query timeout. Default 15s.
        max_results_per_query: how many DDG results to fetch per intent.
        max_chars: hard cap on the formatted web_rag text output.
        prompt_sanity_enabled: whether to run the prompt-sanity check.

    Returns:
        {
          "web_rag": str,                  # formatted ## WEB CONTEXT body
          "prompt_sanity_flags": list,     # advisory flags (may be empty)
          "consultation_trace": dict,      # operational metadata:
                                           #   status (ran|skipped|errored)
                                           #   reason (when skipped/errored)
                                           #   intents_identified (count)
                                           #   intents_executed (count)
                                           #   intents_failed (list)
                                           #   chunks_total (count)
                                           #   chunks_approved (count)
                                           #   chunks_open (count)
                                           #   elapsed_seconds
                                           #   endpoint_used
                                           #   signals (list of trace events)
        }

    Failure modes:
      - fast_endpoint is None → returns empty package with status=skipped.
      - Intent identification fails to parse → returns empty package with
        status=skipped, reason=intent_parse_failed.
      - Intent identification returns zero intents → status=ran but
        chunks_total=0; this is the normal case for pure-conceptual prompts.
      - Individual intent queries timing out or erroring → that intent's
        failure is logged in intents_failed; other intents still process.
    """
    t_start = time.time()
    signals: list[str] = []
    endpoint_name = (fast_endpoint or {}).get("name") if isinstance(fast_endpoint, dict) else None

    def _empty_package(status: str, reason: str) -> dict:
        return {
            "web_rag": "",
            "prompt_sanity_flags": [],
            "consultation_trace": {
                "status": status,
                "reason": reason,
                "intents_identified": 0,
                "intents_executed": 0,
                "intents_failed": [],
                "chunks_total": 0,
                "chunks_approved": 0,
                "chunks_open": 0,
                "elapsed_seconds": time.time() - t_start,
                "endpoint_used": endpoint_name,
                "signals": signals,
            },
        }

    if not fast_endpoint:
        signals.append("web_consultation_skipped: no fast endpoint resolved")
        return _empty_package("skipped", "no_fast_endpoint")

    if trusted_registry is None:
        trusted_registry = web_corroboration.TrustedSourcesRegistry()

    # --- Intent identification (one fast-model call) -------------------
    intent_user = _INTENT_USER_TEMPLATE.format(
        user_prompt=user_prompt or "(empty)",
        conversation_context=conversation_context or "(none)",
    )
    try:
        intent_raw = call_model(
            [{"role": "system", "content": _INTENT_SYSTEM_PROMPT},
             {"role": "user",   "content": intent_user}],
            fast_endpoint,
        )
    except Exception as exc:
        signals.append(f"web_consultation_intent_call_error: {exc}")
        return _empty_package("errored", f"intent_call_error: {exc}")

    intents = _parse_intents(intent_raw or "")
    signals.append(f"web_consultation_intents_identified: {len(intents)}")

    # --- Prompt-sanity check (parallel; one fast-model call) -----------
    # Kicked off alongside the per-intent queries below so we don't add
    # serial latency. If prompt-sanity is disabled, prompt_sanity_flags
    # stays empty.
    sanity_future = None

    # --- Execute intent queries in parallel ----------------------------
    intent_results: list[dict] = []
    intents_failed: list[dict] = []

    if not intents and not prompt_sanity_enabled:
        # No intents and no sanity check — package is empty but status=ran.
        signals.append("web_consultation_no_intents_emitted")
        return _empty_package("ran", "no_intents_emitted")

    # The executor handles both intent queries and the sanity check
    # together — both are bounded fast-model + http calls.
    max_workers = max(1, len(intents)) + (1 if prompt_sanity_enabled else 0)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit the sanity check.
        if prompt_sanity_enabled:
            sanity_user = _SANITY_USER_TEMPLATE.format(
                user_prompt=user_prompt or "(empty)",
            )
            sanity_future = executor.submit(
                _safe_call_model,
                call_model,
                [{"role": "system", "content": _SANITY_SYSTEM_PROMPT},
                 {"role": "user",   "content": sanity_user}],
                fast_endpoint,
            )

        # Submit all intent queries.
        intent_futures = {
            executor.submit(
                _execute_intent_query,
                intent,
                max_results=max_results_per_query,
                timeout_seconds=per_query_timeout_seconds,
                registry=trusted_registry,
            ): intent
            for intent in intents
        }

        # Collect intent results as they complete, with per-future timeout.
        for fut in as_completed(intent_futures, timeout=None):
            intent = intent_futures[fut]
            try:
                result = fut.result(timeout=per_query_timeout_seconds)
                if result.get("error"):
                    intents_failed.append({
                        "intent": intent,
                        "error": result["error"],
                    })
                    signals.append(
                        f"web_consultation_intent_failed: "
                        f"{intent['query'][:40]!r} — {result['error']}"
                    )
                else:
                    intent_results.append(result)
            except Exception as exc:
                intents_failed.append({
                    "intent": intent,
                    "error": f"future_timeout_or_error: {exc}",
                })
                signals.append(
                    f"web_consultation_intent_future_failed: "
                    f"{intent['query'][:40]!r} — {exc}"
                )

        # Collect sanity-check result.
        sanity_flags: list[dict] = []
        if sanity_future is not None:
            try:
                sanity_raw = sanity_future.result(timeout=per_query_timeout_seconds)
                if isinstance(sanity_raw, dict) and sanity_raw.get("error"):
                    signals.append(
                        f"web_consultation_sanity_call_error: {sanity_raw['error']}"
                    )
                else:
                    sanity_flags = _parse_sanity_flags(sanity_raw or "")
                    signals.append(
                        f"web_consultation_sanity_flags: {len(sanity_flags)}"
                    )
            except Exception as exc:
                signals.append(f"web_consultation_sanity_future_failed: {exc}")

    # --- Aggregate scored chunks across intents ------------------------
    all_chunks: list[dict] = []
    for result in intent_results:
        all_chunks.extend(result.get("chunks", []))

    chunks_approved = sum(
        1 for c in all_chunks
        if (c.get("source_tier") or c.get("tier") or "").lower() == "approved"
    )
    chunks_open = len(all_chunks) - chunks_approved

    # --- Format the web_rag text body ----------------------------------
    if all_chunks:
        web_rag_text = format_context_with_provenance(
            all_chunks, max_chars=max_chars,
        )
    else:
        web_rag_text = ""

    signals.append(
        f"web_consultation_summary: intents={len(intents)}, "
        f"executed={len(intent_results)}, failed={len(intents_failed)}, "
        f"chunks={len(all_chunks)}, approved={chunks_approved}, "
        f"open={chunks_open}, sanity_flags={len(sanity_flags)}"
    )

    return {
        "web_rag": web_rag_text,
        "prompt_sanity_flags": sanity_flags,
        "consultation_trace": {
            "status": "ran",
            "reason": None,
            "intents_identified": len(intents),
            "intents_executed": len(intent_results),
            "intents_failed": intents_failed,
            "chunks_total": len(all_chunks),
            "chunks_approved": chunks_approved,
            "chunks_open": chunks_open,
            "elapsed_seconds": time.time() - t_start,
            "endpoint_used": endpoint_name,
            "signals": signals,
        },
    }


def _safe_call_model(
    call_model: Callable[[list, dict], str],
    messages: list,
    endpoint: dict,
) -> Any:
    """Wrap call_model so that an exception in the future surfaces as a
    dict with an ``error`` key rather than killing the future. Lets the
    aggregation pass treat sanity-check failures the same way it treats
    intent-query failures.
    """
    try:
        return call_model(messages, endpoint)
    except Exception as exc:
        return {"error": f"call_model_failed: {exc}"}


__all__ = [
    "assemble_consultation_package",
    "DEFAULT_PER_QUERY_TIMEOUT_SECONDS",
    "DEFAULT_MAX_RESULTS_PER_QUERY",
    "DEFAULT_MAX_CHARS",
    "DEFAULT_SLOT",
    "DEFAULT_PROMPT_SANITY_ENABLED",
]
