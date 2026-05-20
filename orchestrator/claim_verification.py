"""Claim verification pre-flight for Steps 5 (Reviser) and 8 (Verifier).

Implements F-Revise's claim verification + F-Verify's V8/V9 evidence path
via Pattern B (pre-flight injection): the orchestrator parses the
evaluator's ``## FLAGGED CLAIMS`` section, runs every challenge_query in
parallel via DuckDuckGo, and injects the per-claim evidence into the
reviser's and verifier's system prompts as a ``## FLAGGED CLAIM
EVIDENCE`` block. The reviser produces ``## CLAIM RESOLUTIONS``
classifying each claim into one of the five states; the verifier audits
the resolutions against the same evidence (V9) and uses the evidence for
its own V8 factual scan.

Pattern B chosen over Pattern A (tool-use round trips) for:
  - Provider-agnostic (works with any model that accepts a system prompt;
    local MLX models with weak tool-use support included).
  - Trivially traceable (data is visible in the prompt; not buried in
    tool_call/tool_result message turns).
  - Aligns with the user's "first revise surfaces 99%" observation —
    single pre-flight pass is sufficient.

See ``Specification — F-Revise.md`` §Claim verification and
``Specification — F-Verify.md`` V9 for the consumer contracts.
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

from rag_engine import score_external_chunks  # noqa: E402
from tools import web_corroboration  # noqa: E402
from tools.web_search import web_search_structured  # noqa: E402


# ---------------------------------------------------------------------------
# Configuration constants (overridable at call site via kwargs)
# ---------------------------------------------------------------------------

DEFAULT_PER_QUERY_TIMEOUT_SECONDS = 15
DEFAULT_MAX_RESULTS_PER_QUERY = 6


# ---------------------------------------------------------------------------
# Parser — extracts FLAGGED CLAIMS from evaluator output
# ---------------------------------------------------------------------------

# Match the FLAGGED CLAIMS section header. Permissive about leading/
# trailing whitespace and surrounding sections.
_FLAGGED_CLAIMS_HEADER_RE = re.compile(
    r"^##\s+FLAGGED\s+CLAIMS\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Match each claim entry inside the section. The evaluator emission shape
# from F-Evaluate's CLAIM RESOLUTIONS template:
#
#   - **Claim N — `<claim_type>` — risk: <level>**
#     - claim: "<quoted passage>"
#     - why_flagged: <one sentence>
#     - challenge_query: <one line>
#
# Permissive about bold markers, escape characters around the claim type,
# and whitespace. We anchor on the load-bearing field names
# (claim, why_flagged, challenge_query) to survive surface variation.
_CLAIM_HEADER_RE = re.compile(
    r"^\s*-\s+\*\*\s*Claim\s+(?P<num>\d+)\s*[—\-]\s*"
    # claim_type: anything except backticks/em-dash, non-greedy.
    # Older regex required `[a-z\-]+` (single hyphenated word), which
    # silently dropped headers like `named-entity / quantitative` —
    # the eval model legitimately emits multi-word/combined types and
    # the parser must accept them (F-Evaluate spec lists single types
    # but evaluators in the wild compose them).
    r"`?(?P<type>[^`—]+?)`?\s*[—\-]\s*"
    r"risk\s*:\s*(?P<risk>high|moderate|low)\s*\*\*\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_CLAIM_FIELD_RE = re.compile(
    r"^\s+-\s+(?P<field>claim|why_flagged|challenge_query)\s*:\s*(?P<value>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def parse_flagged_claims(evaluator_output: str) -> list[dict]:
    """Parse the ``## FLAGGED CLAIMS`` section from evaluator output.

    Returns a list of dicts with keys: ``claim`` (quoted passage),
    ``claim_type``, ``risk_level``, ``why_flagged``, ``challenge_query``,
    and ``claim_num`` (integer 1-indexed).

    Returns an empty list when:
      - The section is missing from the evaluator output.
      - The section body is the literal ``None.`` line (no claims flagged).
      - The section body has no parseable claim entries.

    Parsing is tolerant — missing fields default to empty strings, so a
    partially-malformed claim entry still appears with whatever was
    recoverable. Claims with no challenge_query are useless for
    verification and are dropped at the model layer (the regex requires
    the field) rather than here.
    """
    if not evaluator_output:
        return []

    # Locate the section.
    header_match = _FLAGGED_CLAIMS_HEADER_RE.search(evaluator_output)
    if not header_match:
        return []

    # Slice from after the header to the next H2 header (or EOF).
    body_start = header_match.end()
    next_header = re.search(
        r"^##\s+\S",
        evaluator_output[body_start:],
        re.MULTILINE,
    )
    body_end = body_start + next_header.start() if next_header else len(evaluator_output)
    body = evaluator_output[body_start:body_end]

    if not body.strip() or body.strip().lower() in {"none.", "none", "(none)"}:
        return []

    # Split body into per-claim chunks anchored on the claim header.
    claims: list[dict] = []
    header_matches = list(_CLAIM_HEADER_RE.finditer(body))
    if not header_matches:
        return []

    for i, hm in enumerate(header_matches):
        chunk_start = hm.end()
        chunk_end = (
            header_matches[i + 1].start()
            if i + 1 < len(header_matches)
            else len(body)
        )
        chunk = body[chunk_start:chunk_end]

        fields: dict[str, str] = {}
        for fm in _CLAIM_FIELD_RE.finditer(chunk):
            field = fm.group("field").lower()
            value = fm.group("value").strip().strip('"\'')
            fields[field] = value

        claims.append({
            "claim_num":        int(hm.group("num")),
            "claim_type":       hm.group("type").lower(),
            "risk_level":       hm.group("risk").lower(),
            "claim":            fields.get("claim", ""),
            "why_flagged":      fields.get("why_flagged", ""),
            "challenge_query":  fields.get("challenge_query", ""),
        })

    # Drop entries that have no challenge_query — without one, there's
    # nothing to verify.
    return [c for c in claims if c["challenge_query"]]


# ---------------------------------------------------------------------------
# Per-claim query execution (reuses the same scoring infrastructure as
# web_consultation; intent-shape adapted to claim-shape).
# ---------------------------------------------------------------------------

def _execute_claim_query(
    claim: dict,
    *,
    max_results: int,
    registry: web_corroboration.TrustedSourcesRegistry,
) -> dict:
    """Run one claim's challenge_query and return per-claim evidence.

    Returns:
        {
          "claim": <original claim dict>,
          "query": <effective query>,
          "results": list[dict],            # raw DDG results
          "chunks": list[dict],             # scored chunks with provenance
          "elapsed_seconds": float,
          "error": Optional[str],
        }
    """
    t_start = time.time()
    out: dict = {
        "claim": claim,
        "query": claim["challenge_query"],
        "results": [],
        "chunks": [],
        "elapsed_seconds": 0.0,
        "error": None,
    }
    try:
        results = web_search_structured(
            claim["challenge_query"], max_results=max_results,
        )
    except Exception as exc:
        out["error"] = f"web_search_failed: {exc}"
        out["elapsed_seconds"] = time.time() - t_start
        return out

    out["results"] = results or []
    if not results:
        out["elapsed_seconds"] = time.time() - t_start
        return out

    raw_chunks: list[dict] = []
    for r in results:
        raw_chunks.append({
            "url":        r.get("url", ""),
            "similarity": 1.0,
            "document":   _result_to_document(r),
            "title":      r.get("title", ""),
            "claim_ref":  f"Claim {claim['claim_num']}",
            "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })

    all_urls = [c["url"] for c in raw_chunks]
    scored = score_external_chunks(
        raw_chunks, all_urls=all_urls, registry=registry,
    )
    out["chunks"] = scored
    out["elapsed_seconds"] = time.time() - t_start
    return out


def _result_to_document(result: dict) -> str:
    """Render one DDG result as the chunk document body."""
    title = (result.get("title") or "").strip()
    snippet = (result.get("snippet") or "").strip()
    if title and snippet:
        return f"**{title}**\n{snippet}"
    return title or snippet or "(no content)"


# ---------------------------------------------------------------------------
# Public entry point — assemble the per-claim evidence package
# ---------------------------------------------------------------------------

def assemble_claim_verification_evidence(
    flagged_claims: list[dict],
    *,
    trusted_registry: Optional[web_corroboration.TrustedSourcesRegistry] = None,
    per_query_timeout_seconds: int = DEFAULT_PER_QUERY_TIMEOUT_SECONDS,
    max_results_per_query: int = DEFAULT_MAX_RESULTS_PER_QUERY,
) -> dict:
    """Run claim-verification web searches in parallel and return the
    evidence package the reviser and verifier consume.

    Args:
        flagged_claims: list of parsed claim dicts from
            ``parse_flagged_claims``. Each must have a non-empty
            ``challenge_query`` (the parser already enforces this).
        trusted_registry: tier-classification registry. Defaults to a
            freshly-loaded instance.
        per_query_timeout_seconds: per-query timeout. Default 15s.
        max_results_per_query: how many DDG results to fetch per claim.

    Returns:
        {
          "evidence_text": str,            # ## FLAGGED CLAIM EVIDENCE body
                                           # ready for prompt injection
          "per_claim_evidence": list[dict],# per-claim trace + chunks
          "trace": dict,                   # operational metadata
        }

    Failure modes:
      - Empty flagged_claims → empty evidence_text, empty per_claim_evidence,
        trace.status="skipped".
      - Individual claim query times out / errors → that claim's evidence
        records the error; remaining claims still process.
    """
    t_start = time.time()
    signals: list[str] = []

    if not flagged_claims:
        return {
            "evidence_text": "",
            "per_claim_evidence": [],
            "trace": {
                "status": "skipped",
                "reason": "no_flagged_claims",
                "claims_total": 0,
                "claims_succeeded": 0,
                "claims_failed": 0,
                "chunks_total": 0,
                "elapsed_seconds": time.time() - t_start,
                "signals": signals,
            },
        }

    if trusted_registry is None:
        trusted_registry = web_corroboration.TrustedSourcesRegistry()

    # --- Parallel claim-query execution --------------------------------
    # Overall budget: per_query_timeout_seconds * 2. Queries fire in
    # parallel so all should finish in roughly per_query_timeout_seconds;
    # the 2x buffer covers scheduling + slow connections. The timeout
    # on as_completed is the load-bearing bound — web_search_structured
    # has no native timeout, so a hung DDG request would otherwise hold
    # the iterator forever.
    per_claim_evidence: list[dict] = []
    claims_failed = 0
    chunks_total = 0
    max_workers = max(1, len(flagged_claims))
    overall_budget_seconds = per_query_timeout_seconds * 2

    # Manually managed executor (not a `with` block) so the
    # budget-exceeded path can call shutdown(wait=False) and return
    # without waiting for hung futures to drain. The hung threads
    # continue in the background until DDG times out at the HTTP layer
    # (typically within seconds-to-minutes), but the pipeline isn't
    # blocked on them.
    executor = ThreadPoolExecutor(max_workers=max_workers)
    budget_exceeded = False
    try:
        future_to_claim = {
            executor.submit(
                _execute_claim_query,
                claim,
                max_results=max_results_per_query,
                registry=trusted_registry,
            ): claim
            for claim in flagged_claims
        }

        try:
            for fut in as_completed(future_to_claim,
                                     timeout=overall_budget_seconds):
                claim = future_to_claim[fut]
                try:
                    result = fut.result(timeout=per_query_timeout_seconds)
                except Exception as exc:
                    result = {
                        "claim": claim,
                        "query": claim["challenge_query"],
                        "results": [],
                        "chunks": [],
                        "elapsed_seconds": per_query_timeout_seconds,
                        "error": f"future_timeout_or_error: {exc}",
                    }
                per_claim_evidence.append(result)
                if result.get("error"):
                    claims_failed += 1
                    signals.append(
                        f"claim_verification_failed: claim_num="
                        f"{claim.get('claim_num')}, error={result['error']}"
                    )
                else:
                    chunks_total += len(result.get("chunks", []))
        except FuturesTimeoutError:
            # Overall budget exhausted. Cancel + record any pending
            # futures as timeout failures.
            budget_exceeded = True
            for fut, claim in future_to_claim.items():
                if not fut.done():
                    fut.cancel()
                    per_claim_evidence.append({
                        "claim": claim,
                        "query": claim["challenge_query"],
                        "results": [],
                        "chunks": [],
                        "elapsed_seconds": overall_budget_seconds,
                        "error": (
                            f"overall_budget_exceeded: "
                            f"{overall_budget_seconds}s"
                        ),
                    })
                    claims_failed += 1
                    signals.append(
                        f"claim_verification_budget_exceeded: claim_num="
                        f"{claim.get('claim_num')}"
                    )
    finally:
        # On the budget-exceeded path, don't wait for hung futures to
        # drain — that defeats the budget. Hung threads continue in
        # the background until their network call eventually times out.
        executor.shutdown(wait=not budget_exceeded)

    # Sort per-claim evidence by claim_num so the prompt block reads in
    # the same order the evaluator emitted.
    per_claim_evidence.sort(
        key=lambda r: r.get("claim", {}).get("claim_num", 0)
    )

    # --- Format the evidence block for prompt injection ----------------
    evidence_text = _format_evidence_block(per_claim_evidence)

    signals.append(
        f"claim_verification_summary: claims={len(flagged_claims)}, "
        f"succeeded={len(flagged_claims) - claims_failed}, "
        f"failed={claims_failed}, chunks={chunks_total}"
    )

    return {
        "evidence_text": evidence_text,
        "per_claim_evidence": per_claim_evidence,
        "trace": {
            "status": "ran",
            "reason": None,
            "claims_total": len(flagged_claims),
            "claims_succeeded": len(flagged_claims) - claims_failed,
            "claims_failed": claims_failed,
            "chunks_total": chunks_total,
            "elapsed_seconds": time.time() - t_start,
            "signals": signals,
        },
    }


# ---------------------------------------------------------------------------
# Prompt-block formatter
# ---------------------------------------------------------------------------

def _format_evidence_block(
    per_claim_evidence: list[dict],
    label_prefix: str = "Claim",
) -> str:
    """Render the per-claim evidence as a prompt-ready body.

    For each claim, emit:
      ### <label_prefix> N — `<claim_type>` — risk: <level>
      **Claim:** "<text>"
      **Challenge query:** "<query>"
      **Evidence:**
        - [<tier> | weight: <n> | source: <url>] <document body>
        - ...
      <or: "**Evidence:** _no results returned_" / "_error: <msg>_">

    The ``label_prefix`` distinguishes evidence blocks when the verifier
    sees both the original flagged-claim evidence (default "Claim") and
    the V8 unflagged-claim evidence (caller passes "Unflagged Claim").

    Returns empty string when per_claim_evidence is empty.
    """
    if not per_claim_evidence:
        return ""

    blocks: list[str] = []
    for entry in per_claim_evidence:
        claim = entry.get("claim", {})
        claim_num = claim.get("claim_num", "?")
        claim_type = claim.get("claim_type", "unknown")
        risk = claim.get("risk_level", "unknown")
        claim_text = claim.get("claim", "")
        query = entry.get("query", "")

        header = (
            f"### {label_prefix} {claim_num} — `{claim_type}` — risk: {risk}\n"
            f"**Claim:** \"{claim_text}\"  \n"
            f"**Challenge query:** \"{query}\""
        )

        if entry.get("error"):
            body = f"**Evidence:** _query failed: {entry['error']}_"
        elif not entry.get("chunks"):
            body = "**Evidence:** _no results returned_"
        else:
            chunk_lines = ["**Evidence:**"]
            for chunk in entry["chunks"]:
                tier = (
                    chunk.get("source_tier")
                    or chunk.get("classification")
                    or chunk.get("tier")
                    or "open"
                )
                weight = chunk.get("weight", 0.0)
                url = chunk.get("url") or chunk.get("source") or "(no url)"
                doc = chunk.get("document") or "(no content)"
                # Compact provenance prefix + the chunk's document body.
                # Body may be multi-line; indent continuation lines so the
                # bullet visual stays clean.
                doc_lines = doc.strip().splitlines()
                first_line = doc_lines[0] if doc_lines else ""
                rest = "\n  ".join(doc_lines[1:]) if len(doc_lines) > 1 else ""
                chunk_lines.append(
                    f"- [{tier} | weight: {weight:.2f} | source: {url}] "
                    f"{first_line}"
                    + (f"\n  {rest}" if rest else "")
                )
            body = "\n".join(chunk_lines)

        blocks.append(f"{header}\n{body}")

    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# V8 unflagged-claim scan — F-Verify §V8 §3 (Unflagged-claim scan)
# ---------------------------------------------------------------------------

_EXTRACT_UNFLAGGED_SYSTEM_PROMPT = """\
You are scanning a revised analysis for high-risk factual claims that the \
evaluator did NOT flag for verification. The verifier (Step 8) will use \
your extracted claims to issue last-gate verification queries.

A claim qualifies for extraction if ALL of these hold:
- It is a SPECIFIC factual assertion (dates, numbers, percentages, \
named entities, direct quotations, technical specifications, established \
historical events).
- It is NOT already in the LIST OF ALREADY-FLAGGED CLAIMS shown below.
- It is NOT a substantive disputed position, contrarian theory, or the \
analyst's analytical conclusion — those pass through untouched (they ARE \
the analysis, not facts to be verified).
- It is NOT an interpretive claim that depends on methodological choice.

Output format. No prose outside the format.

When you find one or more unflagged claims:

EXTRACTED:
- claim: "<quoted assertion from the revised draft>"
  claim_type: <dated-event | quantitative-figure | named-entity | quoted-attribution | cause-effect | technical-spec | general-reference>
  risk_level: <high|moderate|low>
  challenge_query: <search-engine-style query, 3-7 keywords>

When you find no unflagged high-risk claims:

EXTRACTED:
(none)"""


_EXTRACT_UNFLAGGED_USER_TEMPLATE = """\
REVISED ANALYSIS:
{revised_draft}

LIST OF ALREADY-FLAGGED CLAIMS (do not re-extract these):
{already_flagged_summary}"""


_EXTRACTED_BLOCK_RE = re.compile(
    r"^\s*-\s+claim:\s*(?P<claim>.+?)\s*\n"
    # Same tolerance fix as _CLAIM_HEADER_RE — accept multi-word /
    # composite claim_type values the model legitimately emits.
    r"\s+claim_type:\s*(?P<type>.+?)\s*\n"
    r"\s+risk_level:\s*(?P<risk>high|moderate|low)\s*\n"
    r"\s+challenge_query:\s*(?P<query>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _parse_extracted_claims(text: str) -> list[dict]:
    """Parse extracted unflagged claims from the fast-model output.

    Returns a list of {claim_type, risk_level, claim, challenge_query}
    dicts. The claim_num is assigned by the caller — extractor output
    has no numbering, the caller decides the sequence.

    Returns an empty list when "(none)" is the body or no claims parse.
    """
    if not text:
        return []
    out: list[dict] = []
    for m in _EXTRACTED_BLOCK_RE.finditer(text):
        out.append({
            "claim":           m.group("claim").strip().strip('"\''),
            "claim_type":      m.group("type").lower(),
            "risk_level":      m.group("risk").lower(),
            "challenge_query": m.group("query").strip().strip('"\''),
        })
    return out


def _summarize_flagged_claims_for_extractor(
    flagged_claims: list[dict],
) -> str:
    """Render the already-flagged-claims list compactly for the extractor
    prompt. The extractor sees claim text + claim_type so it can detect
    overlap; the per-claim search results are not needed.
    """
    if not flagged_claims:
        return "(no claims were flagged at evaluation)"
    lines = []
    for c in flagged_claims:
        lines.append(
            f"- [{c.get('claim_type', 'unknown')}] "
            f"\"{c.get('claim', '')}\""
        )
    return "\n".join(lines)


def extract_and_verify_unflagged_claims(
    revised_draft: str,
    flagged_claims: list[dict],
    *,
    call_model: Callable[[list, dict], str],
    fast_endpoint: Optional[dict],
    trusted_registry: Optional[web_corroboration.TrustedSourcesRegistry] = None,
    per_query_timeout_seconds: int = DEFAULT_PER_QUERY_TIMEOUT_SECONDS,
    max_results_per_query: int = DEFAULT_MAX_RESULTS_PER_QUERY,
) -> dict:
    """V8 unflagged-claim scan (F-Verify §V8.3).

    A fast-model call extracts high-risk factual claims from the revised
    draft that were NOT in the evaluator's FLAGGED CLAIMS list, then the
    same parallel-search infrastructure used for flagged claims runs the
    extractor's challenge_queries.

    Args:
        revised_draft: the reviser's `## REVISED DRAFT` body (extracted
            from the reviser's full output by the caller).
        flagged_claims: the parsed FLAGGED CLAIMS list from the
            evaluator. Passed to the extractor so it can avoid
            re-extracting already-verified claims.
        call_model: callable for the extractor model call.
        fast_endpoint: endpoint dict for the extractor (typically
            step1_cleanup slot). When None, the scan returns empty.

    Returns same shape as ``assemble_claim_verification_evidence``:
        {
          "evidence_text": str,            # ## UNFLAGGED CLAIM EVIDENCE
          "per_claim_evidence": list[dict],
          "trace": dict,                   # includes "extracted_count"
        }

    Failure modes:
      - fast_endpoint is None → status=skipped, reason=no_fast_endpoint.
      - Empty revised_draft → status=skipped, reason=empty_revised_draft.
      - Extractor model call raises → status=errored.
      - Extractor returns "(none)" → status=ran, extracted_count=0,
        evidence_text="".
    """
    t_start = time.time()
    signals: list[str] = []

    if not fast_endpoint:
        return _empty_unflagged_result(
            "skipped", "no_fast_endpoint", t_start, signals,
        )

    if not revised_draft or not revised_draft.strip():
        return _empty_unflagged_result(
            "skipped", "empty_revised_draft", t_start, signals,
        )

    # --- Extractor call -------------------------------------------------
    user = _EXTRACT_UNFLAGGED_USER_TEMPLATE.format(
        revised_draft=revised_draft,
        already_flagged_summary=_summarize_flagged_claims_for_extractor(
            flagged_claims
        ),
    )
    try:
        raw = call_model(
            [{"role": "system", "content": _EXTRACT_UNFLAGGED_SYSTEM_PROMPT},
             {"role": "user",   "content": user}],
            fast_endpoint,
        )
    except Exception as exc:
        signals.append(f"unflagged_scan_extractor_call_error: {exc}")
        return _empty_unflagged_result(
            "errored", f"extractor_call_error: {str(exc)[:200]}",
            t_start, signals,
        )

    extracted = _parse_extracted_claims(raw or "")
    signals.append(
        f"unflagged_scan_extracted: {len(extracted)} claims"
    )

    if not extracted:
        return {
            "evidence_text": "",
            "per_claim_evidence": [],
            "trace": {
                "status": "ran",
                "reason": None,
                "extracted_count": 0,
                "claims_total": 0,
                "claims_succeeded": 0,
                "claims_failed": 0,
                "chunks_total": 0,
                "elapsed_seconds": time.time() - t_start,
                "signals": signals,
            },
        }

    # Synthesize claim_num for each extracted claim (1-indexed) and a
    # standardized why_flagged so the per-claim evidence renders cleanly.
    numbered: list[dict] = []
    for i, c in enumerate(extracted, 1):
        numbered.append({
            "claim_num":       i,
            "claim_type":      c["claim_type"],
            "risk_level":      c["risk_level"],
            "claim":           c["claim"],
            "why_flagged":     "unflagged at evaluation; verifier pre-flight extracted",
            "challenge_query": c["challenge_query"],
        })

    # Run the same parallel verification path as flagged claims.
    evidence = assemble_claim_verification_evidence(
        numbered,
        trusted_registry=trusted_registry,
        per_query_timeout_seconds=per_query_timeout_seconds,
        max_results_per_query=max_results_per_query,
    )

    # Re-render the evidence block with "Unflagged Claim N" labels so
    # the verifier can distinguish from the FLAGGED CLAIM EVIDENCE block.
    evidence_text = _format_evidence_block(
        evidence["per_claim_evidence"],
        label_prefix="Unflagged Claim",
    )

    # Stitch traces — keep the inner trace's per-claim numbers and add
    # the extractor's extracted_count.
    inner_trace = evidence.get("trace", {})
    return {
        "evidence_text": evidence_text,
        "per_claim_evidence": evidence["per_claim_evidence"],
        "trace": {
            "status": inner_trace.get("status", "ran"),
            "reason": inner_trace.get("reason"),
            "extracted_count": len(extracted),
            "claims_total": inner_trace.get("claims_total", 0),
            "claims_succeeded": inner_trace.get("claims_succeeded", 0),
            "claims_failed": inner_trace.get("claims_failed", 0),
            "chunks_total": inner_trace.get("chunks_total", 0),
            "elapsed_seconds": time.time() - t_start,
            "signals": signals + (inner_trace.get("signals") or []),
        },
    }


def _empty_unflagged_result(
    status: str, reason: str,
    t_start: float, signals: list[str],
) -> dict:
    return {
        "evidence_text": "",
        "per_claim_evidence": [],
        "trace": {
            "status": status,
            "reason": reason,
            "extracted_count": 0,
            "claims_total": 0,
            "claims_succeeded": 0,
            "claims_failed": 0,
            "chunks_total": 0,
            "elapsed_seconds": time.time() - t_start,
            "signals": signals,
        },
    }


# ---------------------------------------------------------------------------
# Revised-draft extractor — pulls the ## REVISED DRAFT section body
# ---------------------------------------------------------------------------

_REVISED_DRAFT_HEADER_RE = re.compile(
    r"^##\s+REVISED\s+DRAFT\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_CHANGELOG_HEADER_RE = re.compile(
    r"^##\s+CHANGELOG\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def extract_revised_draft_section(reviser_output: str) -> str:
    """Extract the body of the ``## REVISED DRAFT`` section from reviser
    output.

    The revised draft can contain its own H2 headings (it's the full
    rewritten analysis), so this stops at ``## CHANGELOG`` specifically
    rather than the next H2. Returns the stripped body, or empty string
    when the section is missing.
    """
    if not reviser_output:
        return ""
    m = _REVISED_DRAFT_HEADER_RE.search(reviser_output)
    if not m:
        return ""
    body_start = m.end()
    cl = _CHANGELOG_HEADER_RE.search(reviser_output[body_start:])
    body_end = body_start + cl.start() if cl else len(reviser_output)
    return reviser_output[body_start:body_end].strip()


__all__ = [
    "parse_flagged_claims",
    "assemble_claim_verification_evidence",
    "extract_and_verify_unflagged_claims",
    "extract_revised_draft_section",
    "DEFAULT_PER_QUERY_TIMEOUT_SECONDS",
    "DEFAULT_MAX_RESULTS_PER_QUERY",
]
