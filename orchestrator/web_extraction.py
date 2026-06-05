"""web_extraction.py — orchestration-level extraction escalation.

The Step 2 web consultation (``web_consultation.assemble_consultation_package``)
is *snippet-only*: it searches, tier-classifies the results by source trust,
checks them against the vault, and hands the analyst the search snippets. It
never fetches a full page on its own. A snippet from a high-trust source is
often too thin to carry the detail the analysis needs — the page has the
answer, the snippet doesn't.

This module is the **extraction-failure escalation** (the middle of the three
failure modes — search / extraction / interaction). After the consultation has
snippet results, it:

    1. SELECT  — pick, cheaply and deterministically, which snippets warrant a
                 full-page fetch: high source-trust AND a thin/truncated
                 snippet, deduped to one fetch per domain, ranked by trust,
                 hard-capped at ``max_fetches`` (the cost ceiling).
    2. FETCH   — call ``web_fetch`` on each (its own 3-tier cascade handles the
                 interaction-failure mode — httpx → Chrome/Playwright → Jina —
                 for free).
    3. CHUNK   — split each returned page's markdown into passages.
    4. GATE    — run the passages through the SAME relevance fit-gate the vault
                 lanes use (``rag_fit_gate``), keeping only on-topic passages.
    5. FOLD    — format the kept passages into a ``### DEEP EXTRACTIONS`` block
                 that the consultation appends to its ``## WEB CONTEXT`` body,
                 alongside the snippets.

Design choices:
- **Dependency-injected.** ``fetch_fn`` (``web_fetch``) and ``fit_gate``
  (a ``fit_gate(chunks, query) -> chunks`` callable from
  ``rag_fit_gate.make_fit_gate``) are passed in, so this module imports no
  orchestrator model-dispatch code, has no circular-import risk, and is
  unit-testable with stubs.
- **Bounded.** ``max_fetches`` caps the expensive step; ``channel`` lets the
  operator forbid the browser tier entirely (``"httpx"``). One batched gate
  call covers all passages from all pages.
- **Fail-CLOSED on the fold (deliberately the opposite of the vault gate).**
  The vault fit-gate fails *open* (keep-all on error) because a gate failure
  there just reproduces the pre-gate similarity ranking, which is safe. Here
  there is no safe pre-gate state: the extracted passages exist only because
  we fetched them, and folding full pages in *ungated* would dump unvetted
  bulk content on the analyst. So when the gate is missing or errors, this
  module folds **nothing** and records why. The whole escalation also
  fails soft as a unit — any unexpected error returns an empty block and an
  ``errored`` trace, leaving the snippet package untouched.

See ``Book — RAG Architecture Report v2.0`` Process 14 and
``Specification — F-Consult`` for the design; this composes with Process 13
(the fit-gate it reuses).
"""

from __future__ import annotations

import re
import sys
import time
from typing import Any, Callable, Optional


# ---------------------------------------------------------------------------
# Defaults (overridable by the caller; boot.py resolves them from env so the
# operator can tune the cost posture without a code change).
# ---------------------------------------------------------------------------

DEFAULT_MIN_WEIGHT = 0.3        # whitelisted (0.7) + corroborated (0.3) qualify
DEFAULT_THIN_CHARS = 350        # snippet shorter than this is "too thin"
DEFAULT_MAX_FETCHES = 3         # hard ceiling on web_fetch calls per turn
DEFAULT_CHANNEL = "auto"        # web_fetch tier; "httpx" forbids the browser
DEFAULT_PER_PAGE_PASSAGES = 10  # passages chunked from one fetched page
DEFAULT_MAX_TOTAL_PASSAGES = 24  # gate-input cap across all fetched pages
DEFAULT_PASSAGE_TARGET_CHARS = 800
DEFAULT_PASSAGE_HARD_CAP = 1600
DEFAULT_MAX_BLOCK_CHARS = 8000  # char budget for the folded-in block

# A passage shorter than this is treated as boilerplate (nav crumb, lone
# link) and dropped before gating.
_MIN_FRAGMENT_CHARS = 40

# Fetch-callable type: web_fetch(url, channel=...) -> result dict.
FetchFn = Callable[..., dict]
# Gate-callable type: fit_gate(chunks, query) -> chunks annotated with
# gate_verdict / gate_reason (the shape rag_fit_gate.make_fit_gate produces).
FitGate = Callable[[list, str], list]


# ---------------------------------------------------------------------------
# Trigger: which snippets warrant a deep fetch
# ---------------------------------------------------------------------------


def _domain_of(url: str) -> str:
    """Root-domain proxy (last two dot-labels) for one-fetch-per-domain dedup.

    Mirrors ``web_corroboration._extract_root_domain``'s heuristic; kept local
    so this module is standalone-testable without loading the registry.
    """
    u = re.sub(r"^https?://", "", (url or "").strip(), flags=re.IGNORECASE)
    host = u.split("/", 1)[0].lower()
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) > 2 else host


def _snippet_is_thin(document: str, thin_chars: int) -> bool:
    """A snippet is thin when it is short OR visibly truncated.

    ``document`` is the chunk body the consultation built (``**title**\\n
    snippet``). Length is measured on the whole body — that is what the
    analyst actually sees. Trailing-ellipsis is an explicit truncation signal
    regardless of length.
    """
    text = (document or "").strip()
    if len(text) < thin_chars:
        return True
    return text.endswith("…") or text.endswith("...")


def _chunk_weight(chunk: dict[str, Any]) -> float:
    try:
        return float(chunk.get("weight") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def select_extraction_candidates(
    web_chunks: list[dict[str, Any]],
    *,
    min_weight: float = DEFAULT_MIN_WEIGHT,
    thin_chars: int = DEFAULT_THIN_CHARS,
    max_fetches: int = DEFAULT_MAX_FETCHES,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Decide which snippet chunks earn a full-page fetch — cheaply, no model.

    A chunk qualifies when ALL hold:
      1. source trust ``weight >= min_weight`` (whitelisted/corroborated by
         default; ``single`` 0.15 and ``excluded`` 0.0 never qualify),
      2. the snippet is thin or truncated (``_snippet_is_thin``),
      3. its domain has not already been chosen this turn (one fetch/domain).

    Survivors are ranked by trust weight (whitelisted before corroborated)
    and capped at ``max_fetches`` — the cost ceiling.

    Returns ``(selected, audit)``. ``audit`` carries one record per *input*
    chunk (url / weight / classification / selected / skip_reason) so the
    trigger decision is fully visible in the trace.
    """
    audit: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    for c in web_chunks or []:
        url = (c.get("url") or "").strip()
        weight = _chunk_weight(c)
        classification = c.get("classification") or ""
        rec = {
            "url": url,
            "weight": weight,
            "classification": classification,
            "selected": False,
            "skip_reason": None,
        }
        if not url:
            rec["skip_reason"] = "no_url"
        elif weight < min_weight:
            rec["skip_reason"] = f"below_trust({weight:.2f}<{min_weight:.2f})"
        elif not _snippet_is_thin(c.get("document") or "", thin_chars):
            rec["skip_reason"] = "snippet_sufficient"
        else:
            eligible.append(c)
        audit.append(rec)

    # Rank eligible by trust (stable — preserves search order within a tier),
    # then take one per domain up to the cap.
    eligible.sort(key=_chunk_weight, reverse=True)
    selected: list[dict[str, Any]] = []
    seen_domains: set[str] = set()
    audit_by_url = {r["url"]: r for r in audit if r["url"]}
    for c in eligible:
        if len(selected) >= max_fetches:
            audit_by_url.get(c.get("url", ""), {})["skip_reason"] = "fetch_cap"
            continue
        dom = _domain_of(c.get("url", ""))
        if dom in seen_domains:
            audit_by_url.get(c.get("url", ""), {})["skip_reason"] = "domain_dup"
            continue
        seen_domains.add(dom)
        selected.append(c)
        rec = audit_by_url.get(c.get("url", ""))
        if rec is not None:
            rec["selected"] = True
            rec["skip_reason"] = None
    return selected, audit


# ---------------------------------------------------------------------------
# Chunk a fetched page's markdown into passages
# ---------------------------------------------------------------------------


_PARA_SPLIT_RE = re.compile(r"\n\s*\n+")


def _chunk_markdown(
    markdown: str,
    *,
    target_chars: int = DEFAULT_PASSAGE_TARGET_CHARS,
    max_passages: int = DEFAULT_PER_PAGE_PASSAGES,
    hard_cap: int = DEFAULT_PASSAGE_HARD_CAP,
    min_fragment: int = _MIN_FRAGMENT_CHARS,
) -> list[str]:
    """Split page markdown into analyst-sized passages.

    Paragraph-boundary split, merging adjacent paragraphs up to
    ``target_chars`` so headings ride with the prose beneath them. Passages
    are taken from the top of the page (Trafilatura/Jina already strip most
    nav/footer boilerplate, and lead content carries the substance); the gate
    filters whatever boilerplate survives. Tiny fragments are dropped and each
    passage is hard-capped so one giant block can't blow the gate-input budget.
    """
    if not markdown or not markdown.strip():
        return []
    paras = [p.strip() for p in _PARA_SPLIT_RE.split(markdown) if p.strip()]
    passages: list[str] = []
    buf = ""
    for p in paras:
        if len(passages) >= max_passages:
            break
        if not buf:
            buf = p
        elif len(buf) + 2 + len(p) <= target_chars:
            buf = f"{buf}\n\n{p}"
        else:
            passages.append(buf)
            buf = p
    if buf and len(passages) < max_passages:
        passages.append(buf)
    out: list[str] = []
    for p in passages:
        if len(p) < min_fragment:
            continue
        out.append(p[:hard_cap])
    return out


def _passage_chunk(passage: str, parent: dict[str, Any], channel_used: str) -> dict[str, Any]:
    """Shape one extracted passage as a chunk the fit-gate + formatter read.

    Inherits the parent snippet's source trust (classification / weight) — a
    passage from a whitelisted page is whitelisted — and carries the parent's
    intent justification so the analyst sees why the source was consulted.
    """
    return {
        "document": passage,
        "metadata": {"source": parent.get("url", "")},
        "url": parent.get("url", ""),
        "title": parent.get("title", ""),
        "classification": parent.get("classification") or "single",
        "weight": _chunk_weight(parent),
        "intent_justification": parent.get("intent_justification", ""),
        "fetched_channel": channel_used,
        "extracted": True,
    }


# ---------------------------------------------------------------------------
# Format the folded-in block
# ---------------------------------------------------------------------------


def _format_extracted_block(
    kept_passages: list[dict[str, Any]],
    max_chars: int = DEFAULT_MAX_BLOCK_CHARS,
) -> str:
    """Render kept passages as the ``### DEEP EXTRACTIONS`` body.

    Marker convention matches ``web_consultation._format_web_consultation_body``
    so the analyst reads extracted passages in the same idiom as snippets, with
    an ``extracted`` flag and the source's trust weight. Honours ``max_chars``
    like the snippet formatter so the folded block fits the analytical budget.
    """
    if not kept_passages:
        return ""
    header = (
        "### DEEP EXTRACTIONS (full-page passages, fit-gated)\n"
        "_Selected high-trust sources whose search snippet was too thin; the "
        "full page was fetched, chunked, and relevance-filtered._\n\n"
    )
    parts: list[str] = []
    total = len(header)
    for c in kept_passages:
        classification = c.get("classification") or "single"
        weight = _chunk_weight(c)
        url = c.get("url") or c.get("metadata", {}).get("source") or "(no url)"
        intent = (c.get("intent_justification") or "").strip()
        document = (c.get("document") or "").strip()
        marker_lines = [
            f"[classification: {classification} | weight: {weight:.2f} "
            f"| source: {url} | extracted]"
        ]
        if intent:
            marker_lines.append(f"[intent: {intent}]")
        block = "\n".join(marker_lines) + "\n" + document + "\n\n"
        if total + len(block) > max_chars and parts:
            break
        parts.append(block)
        total += len(block)
    if not parts:
        return ""
    return header + "".join(parts).rstrip()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def escalate_extraction(
    web_chunks: list[dict[str, Any]],
    query: str,
    *,
    fetch_fn: FetchFn,
    fit_gate: Optional[FitGate],
    min_weight: float = DEFAULT_MIN_WEIGHT,
    thin_chars: int = DEFAULT_THIN_CHARS,
    max_fetches: int = DEFAULT_MAX_FETCHES,
    channel: str = DEFAULT_CHANNEL,
    per_page_passages: int = DEFAULT_PER_PAGE_PASSAGES,
    max_total_passages: int = DEFAULT_MAX_TOTAL_PASSAGES,
    max_block_chars: int = DEFAULT_MAX_BLOCK_CHARS,
) -> dict[str, Any]:
    """Run the extraction-failure escalation over the consultation's snippets.

    Returns::

        {
          "extracted_block": str,           # "" when nothing was folded
          "kept_passages":   list[dict],    # gate-kept passage chunks
          "trace": {
            "status":   "ran"|"skipped"|"errored",
            "reason":   Optional[str],
            "candidates": list[...],        # the trigger decision, per input url
            "fetches":  list[...],          # url, channel_used, passages, error
            "passages_extracted": int,
            "passages_kept": int,
            "passages_dropped": int,
            "verdicts": list[...],          # per-passage keep/drop + reason
            "elapsed_seconds": float,
            "signals": list[str],
          },
        }

    Fail-CLOSED on the fold: with no gate (``fit_gate is None``) or a gate
    error, nothing is folded (see module docstring). Fail-soft as a unit: any
    unexpected error returns an empty block and an ``errored`` trace.
    """
    t_start = time.time()
    signals: list[str] = []

    def _result(status: str, reason: Optional[str], block: str,
                kept: list, **trace_extra) -> dict[str, Any]:
        trace = {
            "status": status,
            "reason": reason,
            "elapsed_seconds": time.time() - t_start,
            "signals": signals,
        }
        trace.update(trace_extra)
        return {"extracted_block": block, "kept_passages": kept, "trace": trace}

    try:
        selected, audit = select_extraction_candidates(
            web_chunks, min_weight=min_weight, thin_chars=thin_chars,
            max_fetches=max_fetches,
        )
        signals.append(
            f"extraction_candidates: {len(selected)} selected "
            f"of {len(audit)} considered"
        )
        if not selected:
            return _result("skipped", "no_candidates", "", [],
                           candidates=audit, fetches=[],
                           passages_extracted=0, passages_kept=0,
                           passages_dropped=0, verdicts=[])

        # The gate is the relevance guarantee. No gate => fold nothing.
        if fit_gate is None:
            signals.append("extraction_no_fit_gate: folding nothing (fail-closed)")
            return _result("skipped", "no_fit_gate", "", [],
                           candidates=audit, fetches=[],
                           passages_extracted=0, passages_kept=0,
                           passages_dropped=0, verdicts=[])

        # --- FETCH + CHUNK ------------------------------------------------
        fetches: list[dict[str, Any]] = []
        passages: list[dict[str, Any]] = []
        for cand in selected:
            url = cand.get("url", "")
            fetch_rec = {"url": url, "channel_used": None,
                         "passages": 0, "error": None}
            try:
                res = fetch_fn(url, channel=channel)
            except Exception as exc:  # web_fetch is defensive, but be safe
                fetch_rec["error"] = f"fetch_raised: {str(exc)[:160]}"
                fetches.append(fetch_rec)
                signals.append(f"extraction_fetch_error: {url} — {exc}")
                continue
            res = res or {}
            fetch_rec["channel_used"] = res.get("channel")
            if res.get("error"):
                fetch_rec["error"] = str(res.get("error"))[:160]
                fetches.append(fetch_rec)
                continue
            page_passages = _chunk_markdown(
                res.get("markdown") or "",
                target_chars=DEFAULT_PASSAGE_TARGET_CHARS,
                max_passages=per_page_passages,
            )
            for p in page_passages:
                if len(passages) >= max_total_passages:
                    break
                passages.append(_passage_chunk(p, cand, res.get("channel") or channel))
            fetch_rec["passages"] = sum(
                1 for x in passages if x.get("url") == url
            )
            fetches.append(fetch_rec)
            if len(passages) >= max_total_passages:
                signals.append(
                    f"extraction_passage_cap: hit {max_total_passages}"
                )
                break

        if not passages:
            return _result("ran", "no_passages_extracted", "", [],
                           candidates=audit, fetches=fetches,
                           passages_extracted=0, passages_kept=0,
                           passages_dropped=0, verdicts=[])

        # --- GATE (one batched call across all passages) ------------------
        try:
            gated = fit_gate(passages, query or "")
        except Exception as exc:
            # Fail-CLOSED: an unusable gate means we cannot vouch for
            # relevance, so we fold nothing rather than dump full pages.
            signals.append(f"extraction_gate_error: {exc} — folding nothing")
            return _result("errored", f"gate_error: {str(exc)[:160]}", "", [],
                           candidates=audit, fetches=fetches,
                           passages_extracted=len(passages),
                           passages_kept=0,
                           passages_dropped=len(passages), verdicts=[])

        kept: list[dict[str, Any]] = []
        verdicts: list[dict[str, Any]] = []
        for c in gated:
            verdict = (c.get("gate_verdict") or "keep").lower()
            verdicts.append({
                "source": c.get("url", ""),
                "verdict": verdict,
                "reason": c.get("gate_reason", ""),
                "preview": " ".join((c.get("document") or "").split())[:80],
            })
            if verdict != "drop":
                kept.append(c)

        block = _format_extracted_block(kept, max_chars=max_block_chars)
        signals.append(
            f"extraction_summary: fetched={len(fetches)}, "
            f"passages={len(passages)}, kept={len(kept)}, "
            f"dropped={len(passages) - len(kept)}"
        )
        # A block can be empty even with kept passages only if the char budget
        # zeroed it out; treat presence of kept passages as the "ran" signal.
        status = "ran"
        reason = None if (kept or fetches) else "no_fold"
        return _result(status, reason, block, kept,
                       candidates=audit, fetches=fetches,
                       passages_extracted=len(passages),
                       passages_kept=len(kept),
                       passages_dropped=len(passages) - len(kept),
                       verdicts=verdicts)

    except Exception as exc:  # whole-escalation fail-soft
        print(f"[web_extraction] escalation failed, folding nothing: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        signals.append(f"extraction_unexpected_error: {exc}")
        return _result("errored", f"unexpected: {str(exc)[:200]}", "", [])


__all__ = [
    "escalate_extraction",
    "select_extraction_candidates",
    "DEFAULT_MIN_WEIGHT",
    "DEFAULT_THIN_CHARS",
    "DEFAULT_MAX_FETCHES",
    "DEFAULT_CHANNEL",
    "DEFAULT_PER_PAGE_PASSAGES",
    "DEFAULT_MAX_TOTAL_PASSAGES",
    "DEFAULT_MAX_BLOCK_CHARS",
]
