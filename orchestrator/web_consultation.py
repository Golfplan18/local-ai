"""Step 2 — Consultation-Augmented Generation (CAG) web stream.

Implements F-Consult's web consultation: parallel web search seeded from the
prompt, justification-gated intent identification, source tiering (approved
vs open), per-chunk provenance, optional prompt-sanity check. Runs alongside
vault/conversation/relationship RAG and produces the web portion of the
consultation package.

See ~/Documents/vault/Projects/Ora/Specification — F-Consult.md for the design.

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
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
    TimeoutError as FuturesTimeoutError,
)
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

# Extraction-failure escalation (Process 14) — optional deep-fetch of thin
# high-trust snippets, chunked + fit-gated + folded back in beside the
# snippets. Guarded so a missing/broken module never breaks the consultation;
# extraction simply stays unavailable and the stream remains snippet-only.
try:
    from tools.web_fetch import web_fetch  # noqa: E402
    from web_extraction import escalate_extraction  # noqa: E402
    WEB_EXTRACTION_AVAILABLE = True
except Exception:  # pragma: no cover - defensive import guard
    web_fetch = None  # type: ignore
    escalate_extraction = None  # type: ignore
    WEB_EXTRACTION_AVAILABLE = False


# ---------------------------------------------------------------------------
# Configuration constants (overridable at call site via kwargs)
# ---------------------------------------------------------------------------

DEFAULT_PER_QUERY_TIMEOUT_SECONDS = 15
DEFAULT_MAX_RESULTS_PER_QUERY = 6
DEFAULT_MAX_CHARS = 12_000
DEFAULT_SLOT = "step1_cleanup"   # fast slot for intent identification + sanity check
DEFAULT_PROMPT_SANITY_ENABLED = True
DEFAULT_CONFLICT_DETECTION_ENABLED = True
DEFAULT_CONFLICT_DETECTION_MAX_CHARS = 10_000  # input budget for the detector
DEFAULT_CONFLICT_DETECTION_MAX_VAULT_CHARS = 6_000  # cap on vault content sent in


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


_CONFLICT_DETECTOR_SYSTEM_PROMPT = """\
You are checking whether web search results contradict the user's vault \
knowledge on FACTUAL claims. The vault is the user's personal knowledge \
store; web results are independent search hits. Your job is to find places \
where the two disagree on a specific verifiable fact, NOT to enforce \
mainstream consensus on the user's interpretive or contrarian positions.

A conflict qualifies for flagging if ALL of these hold:
- The disagreement is on a SPECIFIC verifiable fact (date, number, named \
entity, established historical event, technical specification, attribution \
of a quote).
- Both the vault and the web make an unambiguous claim about it.
- They contradict each other.

A conflict does NOT qualify if:
- The vault carries a substantive disputed position, contrarian theory, \
or contested interpretation. Those are the user's analytical content, NOT \
"facts" subject to mainstream consensus enforcement. PASS THESE THROUGH \
UNTOUCHED.
- The web result merely adds context the vault doesn't cover.
- The vault and web express the same fact in different words.
- The disagreement is about which methodology / definition / vintage to \
use (interpretive, not factual).

Output format. No prose outside the format.

When you find one or more genuine factual conflicts:

CONFLICTS:
- web_chunk_index: <0-based index of the web chunk>
  vault_reference: <quote or short reference to the vault content that conflicts>
  contradiction: <one short sentence — what the two say differently>

When you find no conflicts (the normal case):

CONFLICTS:
(none)"""


_CONFLICT_DETECTOR_USER_TEMPLATE = """\
VAULT KNOWLEDGE:
{vault_rag_context}

WEB SEARCH RESULTS:
{web_chunks_text}"""


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

_CONFLICT_BLOCK_RE = re.compile(
    r"^\s*-\s+web_chunk_index:\s*(?P<idx>\d+)\s*\n"
    r"\s+vault_reference:\s*(?P<vref>.+?)\s*\n"
    r"\s+contradiction:\s*(?P<contra>.+?)\s*$",
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


def _parse_conflict_blocks(text: str) -> list[dict]:
    """Parse conflict blocks from the conflict-detector model output.

    Returns a list of {web_chunk_index (int), vault_reference, contradiction}
    dicts. Returns [] when "(none)" or the section is missing/malformed.
    """
    if not text or "(none)" in text.lower():
        return []
    out: list[dict] = []
    for m in _CONFLICT_BLOCK_RE.finditer(text):
        try:
            idx = int(m.group("idx"))
        except (ValueError, TypeError):
            continue
        out.append({
            "web_chunk_index": idx,
            "vault_reference": m.group("vref").strip().strip('"\''),
            "contradiction":   m.group("contra").strip().strip('"\''),
        })
    return out


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
            intent["query"], max_results=max_results, semantic_augment=True,
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
# Custom WEB CONTEXT formatter — surfaces intent_justification and
# consultation_conflict flags alongside the standard
# classification/weight/source marker. Used in place of
# rag_engine.format_context_with_provenance for web chunks so the
# analyst can see WHY each search was issued and whether any chunk
# contradicts vault knowledge.
# ---------------------------------------------------------------------------


def _format_web_consultation_body(
    chunks: list[dict],
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str:
    """Render web chunks for analyst-prompt injection.

    Each chunk emits:
      [classification: <class> | weight: <w> | source: <url>]
      [intent: <intent_justification>]               (when present)
      [CONFLICT: <vault_reference> — <contradiction>] (when present)
      <document body>

    Stops appending once ``max_chars`` is exceeded — matches
    rag_engine.format_context_with_provenance's character-budget
    behavior so the assembled package fits inside the analytical-floor
    budget.
    """
    if not chunks:
        return ""
    parts: list[str] = []
    total = 0
    for chunk in chunks:
        classification = chunk.get("classification") or "open"
        try:
            weight = float(chunk.get("weight") or 0.0)
        except (TypeError, ValueError):
            weight = 0.0
        url = chunk.get("url") or chunk.get("source") or "(no url)"
        document = chunk.get("document") or "(no content)"
        intent = (chunk.get("intent_justification") or "").strip()
        conflict_flag = bool(chunk.get("consultation_conflict"))
        conflicts_with = (chunk.get("conflicts_with") or "").strip()

        marker_lines = [
            f"[classification: {classification} | weight: {weight:.2f} | source: {url}]"
        ]
        if intent:
            marker_lines.append(f"[intent: {intent}]")
        if conflict_flag and conflicts_with:
            marker_lines.append(f"[CONFLICT: {conflicts_with}]")

        block = "\n".join(marker_lines) + "\n" + document.strip() + "\n\n"
        if total + len(block) > max_chars and parts:
            break
        parts.append(block)
        total += len(block)
        # Execution Review Phase 8 (Chunk A §2.4): mark the chunks that
        # actually entered the prompt body — the char-budget break means
        # all_chunks can be a SUPERSET of what any model saw, and the
        # provenance registry must never let an un-injected chunk support
        # a claim (that would be fabricated provenance). In-place stamp;
        # chunks the loop never reached stay unstamped (falsy).
        chunk["injected"] = True
    return "".join(parts).rstrip()


# ---------------------------------------------------------------------------
# Vault-vs-web conflict detection (F-Consult spec §4)
# ---------------------------------------------------------------------------


def _detect_conflicts_against_vault(
    web_chunks: list[dict],
    vault_rag_context: str,
    *,
    call_model: Callable[[list, dict], str],
    fast_endpoint: dict,
    max_input_chars: int = DEFAULT_CONFLICT_DETECTION_MAX_CHARS,
    max_vault_chars: int = DEFAULT_CONFLICT_DETECTION_MAX_VAULT_CHARS,
) -> dict:
    """Detect contradictions between web chunks and vault content.

    One fast-model call compares the web chunks to the vault knowledge
    package and identifies specific factual disagreements. Discipline
    in the prompt: only flag SPECIFIC verifiable factual contradictions;
    do NOT flag substantive disputed positions or contrarian content
    in the vault as "wrong" — those pass through untouched (this is
    the Big Bang case from F-Revise's §disputed-but-defensible).

    Returns:
        {
          "annotated_chunks": list[dict],  # web_chunks with
                                            # consultation_conflict and
                                            # conflicts_with added where
                                            # the detector found a conflict
          "conflicts_count": int,
          "trace": dict (status, reason, conflicts, signals),
        }

    Failure modes — fail-soft:
      - Empty web_chunks → status=skipped, reason=no_web_chunks.
      - Empty vault_rag_context → status=skipped, reason=no_vault_context.
      - call_model raises → status=errored, annotated_chunks unchanged.
      - Parse failure → status=ran with conflicts_count=0.
    """
    t_start = time.time()
    signals: list[str] = []
    annotated = list(web_chunks)

    if not web_chunks:
        return {
            "annotated_chunks": annotated,
            "conflicts_count": 0,
            "trace": {
                "status": "skipped",
                "reason": "no_web_chunks",
                "conflicts": [],
                "elapsed_seconds": time.time() - t_start,
                "signals": signals,
            },
        }
    if not (vault_rag_context or "").strip():
        return {
            "annotated_chunks": annotated,
            "conflicts_count": 0,
            "trace": {
                "status": "skipped",
                "reason": "no_vault_context",
                "conflicts": [],
                "elapsed_seconds": time.time() - t_start,
                "signals": signals,
            },
        }
    if fast_endpoint is None:
        return {
            "annotated_chunks": annotated,
            "conflicts_count": 0,
            "trace": {
                "status": "skipped",
                "reason": "no_fast_endpoint",
                "conflicts": [],
                "elapsed_seconds": time.time() - t_start,
                "signals": signals,
            },
        }

    # Build the detector input: a truncated vault context + numbered
    # web chunks with their document bodies. The numbering aligns with
    # the detector's web_chunk_index output.
    vault_trim = vault_rag_context[:max_vault_chars]
    web_lines: list[str] = []
    char_budget = max_input_chars - len(vault_trim)
    for i, chunk in enumerate(web_chunks):
        url = chunk.get("url") or "(no url)"
        document = (chunk.get("document") or "").strip()
        block = f"[{i}] (source: {url})\n{document}\n"
        if char_budget - len(block) < 0 and web_lines:
            break
        web_lines.append(block)
        char_budget -= len(block)
    web_chunks_text = "\n".join(web_lines)

    user_msg = _CONFLICT_DETECTOR_USER_TEMPLATE.format(
        vault_rag_context=vault_trim,
        web_chunks_text=web_chunks_text,
    )

    try:
        raw = call_model(
            [{"role": "system", "content": _CONFLICT_DETECTOR_SYSTEM_PROMPT},
             {"role": "user",   "content": user_msg}],
            fast_endpoint,
        )
    except Exception as exc:
        signals.append(f"conflict_detector_call_error: {exc}")
        return {
            "annotated_chunks": annotated,
            "conflicts_count": 0,
            "trace": {
                "status": "errored",
                "reason": f"detector_call_error: {str(exc)[:200]}",
                "conflicts": [],
                "elapsed_seconds": time.time() - t_start,
                "signals": signals,
            },
        }

    conflicts = _parse_conflict_blocks(raw or "")
    signals.append(f"conflict_detector_found: {len(conflicts)} conflicts")

    # Annotate the affected web chunks.
    for c in conflicts:
        idx = c["web_chunk_index"]
        if 0 <= idx < len(annotated):
            annotated[idx] = {
                **annotated[idx],
                "consultation_conflict": True,
                "conflicts_with": (
                    f"{c['vault_reference']} — {c['contradiction']}"
                ),
            }

    return {
        "annotated_chunks": annotated,
        "conflicts_count": len(conflicts),
        "trace": {
            "status": "ran",
            "reason": None,
            "conflicts": conflicts,
            "elapsed_seconds": time.time() - t_start,
            "signals": signals,
        },
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def assemble_consultation_package(
    user_prompt: str,
    *,
    call_model: Callable[[list, dict], str],
    fast_endpoint: Optional[dict],
    conversation_context: str = "",
    vault_rag_context: str = "",
    trusted_registry: Optional[web_corroboration.TrustedSourcesRegistry] = None,
    per_query_timeout_seconds: int = DEFAULT_PER_QUERY_TIMEOUT_SECONDS,
    max_results_per_query: int = DEFAULT_MAX_RESULTS_PER_QUERY,
    max_chars: int = DEFAULT_MAX_CHARS,
    prompt_sanity_enabled: bool = DEFAULT_PROMPT_SANITY_ENABLED,
    conflict_detection_enabled: bool = DEFAULT_CONFLICT_DETECTION_ENABLED,
    extraction_enabled: bool = False,
    extraction_fit_gate: Optional[Callable[[list, str], list]] = None,
    extraction_min_weight: float = 0.3,
    extraction_thin_chars: int = 350,
    extraction_max_fetches: int = 3,
    extraction_channel: str = "auto",
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
            "chunks": [],
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
                "extraction": {"status": "skipped",
                               "reason": "consultation_not_run"},
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
    t_intent_start = time.time()
    try:
        intent_raw = call_model(
            [{"role": "system", "content": _INTENT_SYSTEM_PROMPT},
             {"role": "user",   "content": intent_user}],
            fast_endpoint,
        )
    except Exception as exc:
        signals.append(f"web_consultation_intent_call_error: {exc}")
        return _empty_package("errored", f"intent_call_error: {exc}")
    intent_elapsed = time.time() - t_intent_start

    intents = _parse_intents(intent_raw or "")
    signals.append(f"web_consultation_intents_identified: {len(intents)}")
    # Observability fix #3 — flag slow intent calls. The intent extractor
    # runs on the step1_cleanup slot (fast cloud model). Anything over 10s
    # is unusual (cold-start, rate-limit backoff, network stall). Flag so
    # the trace surfaces the latency without needing per-call timestamps.
    if intent_elapsed > 10:
        signals.append(
            f"web_consultation_intent_slow: {intent_elapsed:.1f}s "
            f"(expected <5s for fast cloud model; check endpoint cold-start "
            f"/ rate-limit / network stall)"
        )
    # Observability fix #2 — preserve raw model response (first 500 chars)
    # so trace consumers can distinguish "model said (none)" from "model
    # returned malformed output that didn't match the parser regex".
    intent_raw_preview = (intent_raw or "")[:500]
    intent_raw_chars = len(intent_raw or "")

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
    #
    # Overall budget: per_query_timeout_seconds * 2. Queries fire in
    # parallel, so even N intents should all complete in roughly
    # per_query_timeout_seconds; the 2x buffer covers scheduling
    # overhead and slow connections. as_completed's timeout argument is
    # the *overall* bound on the loop — any future not done by then is
    # cancelled and recorded as failed, preventing one hung
    # web_search_structured call (the DDG library has no native
    # timeout) from blocking the whole consultation.
    overall_budget_seconds = per_query_timeout_seconds * 2
    max_workers = max(1, len(intents)) + (1 if prompt_sanity_enabled else 0)
    sanity_flags: list[dict] = []
    # Manually managed executor so the budget-exceeded path can
    # shutdown(wait=False) and return without waiting for hung futures
    # to drain. See claim_verification.assemble_claim_verification_
    # evidence for the same pattern.
    executor = ThreadPoolExecutor(max_workers=max_workers)
    budget_exceeded = False
    try:
        # 2026-05-28: ContextVar propagation. Wrap submit so the
        # per-turn rag_isolation + trace_dir ContextVars set by
        # boot.run_step2_context_assembly survive into the worker
        # thread. Without this, model calls made inside web
        # consultation lose token capture and any flag-based gating.
        import contextvars as _ctxvars
        def _ctx_submit(fn, *args, **kwargs):
            ctx = _ctxvars.copy_context()
            _s = executor.submit
            return _s(ctx.run, fn, *args, **kwargs)

        # Submit the sanity check.
        if prompt_sanity_enabled:
            sanity_user = _SANITY_USER_TEMPLATE.format(
                user_prompt=user_prompt or "(empty)",
            )
            sanity_future = _ctx_submit(
                _safe_call_model,
                call_model,
                [{"role": "system", "content": _SANITY_SYSTEM_PROMPT},
                 {"role": "user",   "content": sanity_user}],
                fast_endpoint,
            )

        # Submit all intent queries.
        intent_futures = {
            _ctx_submit(
                _execute_intent_query,
                intent,
                max_results=max_results_per_query,
                timeout_seconds=per_query_timeout_seconds,
                registry=trusted_registry,
            ): intent
            for intent in intents
        }

        # Collect intent results as they complete. The overall_budget
        # bounds the entire loop; any future not done by then is
        # cancelled and recorded as a timeout failure.
        try:
            for fut in as_completed(intent_futures,
                                     timeout=overall_budget_seconds):
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
        except FuturesTimeoutError:
            # Overall budget exhausted. Cancel + record any pending futures.
            budget_exceeded = True
            for fut, intent in intent_futures.items():
                if not fut.done():
                    fut.cancel()
                    intents_failed.append({
                        "intent": intent,
                        "error": (
                            f"overall_budget_exceeded: "
                            f"{overall_budget_seconds}s"
                        ),
                    })
                    signals.append(
                        f"web_consultation_intent_budget_exceeded: "
                        f"{intent['query'][:40]!r}"
                    )

        # Collect sanity-check result. Bounded by per_query_timeout — if
        # the sanity model hangs we degrade to no flags rather than
        # blocking the package return.
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
            except FuturesTimeoutError:
                sanity_future.cancel()
                signals.append(
                    f"web_consultation_sanity_future_timed_out: "
                    f"{per_query_timeout_seconds}s"
                )
            except Exception as exc:
                signals.append(f"web_consultation_sanity_future_failed: {exc}")
    finally:
        # On the budget-exceeded path, don't wait for hung futures.
        executor.shutdown(wait=not budget_exceeded)

    # --- Aggregate scored chunks across intents ------------------------
    all_chunks: list[dict] = []
    for result in intent_results:
        all_chunks.extend(result.get("chunks", []))

    # rag_engine.score_external_chunks annotates each chunk with a
    # `classification` field whose values come from
    # web_corroboration.classify_web_source: ``whitelisted`` (in the
    # trusted-source registry — F-Consult's "approved tier"),
    # ``corroborated`` (open-web but multiple sources agree), or
    # ``single`` (open-web, one source). Whitelisted maps to approved;
    # everything else is open-tier for trace-metadata purposes.
    chunks_approved = sum(
        1 for c in all_chunks
        if (c.get("classification") or "").lower() == "whitelisted"
    )
    chunks_open = len(all_chunks) - chunks_approved

    # --- Vault-vs-web conflict detection (F-Consult spec §4) ----------
    # When vault context + web chunks are both present, one fast-model
    # call checks for specific factual contradictions. Conflicting web
    # chunks get consultation_conflict + conflicts_with annotations
    # that the formatter surfaces as a [CONFLICT: ...] marker line.
    # The detector is instructed NOT to flag substantive disputed
    # vault content as "wrong" — those pass through untouched.
    #
    # Observability fix #1 — distinct skip reasons per gate. Previously
    # all skips collapsed to "disabled_or_no_inputs" which made it
    # impossible to tell which gate fired. Now: disabled_by_config /
    # no_web_chunks / no_vault_context are emitted separately so the
    # trace tells operators exactly why the detector skipped.
    conflicts_count = 0
    if not conflict_detection_enabled:
        conflict_trace = {
            "status": "skipped",
            "reason": "disabled_by_config",
            "conflicts": [],
        }
    elif not all_chunks:
        conflict_trace = {
            "status": "skipped",
            "reason": "no_web_chunks",
            "conflicts": [],
        }
    elif not (vault_rag_context or "").strip():
        conflict_trace = {
            "status": "skipped",
            "reason": "no_vault_context",
            "conflicts": [],
        }
    else:
        try:
            detect_result = _detect_conflicts_against_vault(
                all_chunks, vault_rag_context,
                call_model=call_model,
                fast_endpoint=fast_endpoint,
            )
            all_chunks = detect_result["annotated_chunks"]
            conflicts_count = detect_result["conflicts_count"]
            conflict_trace = detect_result["trace"]
            signals.append(
                f"web_consultation_conflict_detection: "
                f"{conflicts_count} conflicts flagged"
            )
        except Exception as exc:
            # Fail-soft: detector errors do not block the consultation.
            conflict_trace = {
                "status": "errored",
                "reason": f"detector_wrapper_error: {str(exc)[:200]}",
                "conflicts": [],
            }
            signals.append(f"web_consultation_conflict_wrapper_error: {exc}")

    # --- Format the web_rag text body via the web-specific formatter --
    # Custom formatter (not rag_engine.format_context_with_provenance)
    # so intent_justification + consultation_conflict markers surface
    # to the analyst alongside the standard classification/weight/source
    # line. See F-Consult spec §4 for the per-chunk provenance contract.
    if all_chunks:
        web_rag_text = _format_web_consultation_body(
            all_chunks, max_chars=max_chars,
        )
    else:
        web_rag_text = ""

    # --- Extraction escalation (Process 14) ---------------------------
    # The middle of the three failure modes: a high-trust snippet that is too
    # thin to carry the detail the analysis needs. escalate_extraction selects
    # those (cheap, deterministic, capped), fetches the full page via web_fetch,
    # chunks the markdown, runs the passages through the SAME relevance gate the
    # vault lanes use, and folds the survivors in beside the snippets. Bounded
    # and fail-CLOSED (no gate / gate error => fold nothing). See
    # orchestrator/web_extraction.py and Book — RAG Architecture Report Process 14.
    extraction_trace: dict = {"status": "skipped", "reason": "disabled"}
    if extraction_enabled and not WEB_EXTRACTION_AVAILABLE:
        extraction_trace = {"status": "skipped", "reason": "module_unavailable"}
    elif extraction_enabled and all_chunks:
        try:
            ex = escalate_extraction(
                all_chunks, user_prompt,
                fetch_fn=web_fetch,
                fit_gate=extraction_fit_gate,
                min_weight=extraction_min_weight,
                thin_chars=extraction_thin_chars,
                max_fetches=extraction_max_fetches,
                channel=extraction_channel,
            )
            extraction_trace = ex.get("trace") or {"status": "ran"}
            block = ex.get("extracted_block") or ""
            if block:
                web_rag_text = (
                    f"{web_rag_text}\n\n{block}" if web_rag_text else block
                )
            signals.append(
                f"web_consultation_extraction: "
                f"status={extraction_trace.get('status')}, "
                f"kept={extraction_trace.get('passages_kept', 0)}, "
                f"dropped={extraction_trace.get('passages_dropped', 0)}"
            )
        except Exception as exc:
            # Fail-soft: extraction must never block the consultation.
            extraction_trace = {"status": "errored", "reason": str(exc)[:200]}
            signals.append(f"web_consultation_extraction_error: {exc}")

    signals.append(
        f"web_consultation_summary: intents={len(intents)}, "
        f"executed={len(intent_results)}, failed={len(intents_failed)}, "
        f"chunks={len(all_chunks)}, approved={chunks_approved}, "
        f"open={chunks_open}, conflicts={conflicts_count}, "
        f"sanity_flags={len(sanity_flags)}"
    )

    return {
        "web_rag": web_rag_text,
        # Execution Review Phase 8 (Chunk A §2.2): the structured chunks were
        # historically DISCARDED at this return boundary (only the formatted
        # string survived). Retained additively for the provenance registry —
        # url/title/document/retrieved_at/weight/classification per chunk,
        # plus the `injected` stamp from the formatter (§2.4: only injected
        # chunks may support a claim). Zero new fetches.
        "chunks": all_chunks,
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
            "conflicts_count": conflicts_count,
            "conflict_detection": conflict_trace,
            "extraction": extraction_trace,
            # Observability fix #2/#3 — preserve the intent-call diagnostic
            # data so trace consumers can debug 0-intent outcomes and slow
            # cloud-model calls without needing per-call instrumentation.
            "intent_call_elapsed_seconds": intent_elapsed,
            "intent_raw_chars": intent_raw_chars,
            "intent_raw_preview": intent_raw_preview,
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
