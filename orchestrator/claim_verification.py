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
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

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
    r"`?(?P<type>[a-z\-]+)`?\s*[—\-]\s*"
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
    per_claim_evidence: list[dict] = []
    claims_failed = 0
    chunks_total = 0
    max_workers = max(1, len(flagged_claims))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_claim = {
            executor.submit(
                _execute_claim_query,
                claim,
                max_results=max_results_per_query,
                registry=trusted_registry,
            ): claim
            for claim in flagged_claims
        }

        for fut in as_completed(future_to_claim, timeout=None):
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

def _format_evidence_block(per_claim_evidence: list[dict]) -> str:
    """Render the per-claim evidence as a ``## FLAGGED CLAIM EVIDENCE``
    body suitable for direct injection into a model system prompt.

    For each claim, emit:
      ### Claim N — `<claim_type>` — risk: <level>
      **Claim:** "<text>"
      **Challenge query:** "<query>"
      **Evidence:**
        - [<tier> | weight: <n> | source: <url>] <document body>
        - ...
      <or: "**Evidence:** _no results returned_" / "_error: <msg>_">

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
            f"### Claim {claim_num} — `{claim_type}` — risk: {risk}\n"
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


__all__ = [
    "parse_flagged_claims",
    "assemble_claim_verification_evidence",
    "DEFAULT_PER_QUERY_TIMEOUT_SECONDS",
    "DEFAULT_MAX_RESULTS_PER_QUERY",
]
