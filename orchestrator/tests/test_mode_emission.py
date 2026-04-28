#!/usr/bin/env python3
"""
Tier A mode-emission harness — Mode Specification Rebuild.

Simulates ``build_system_prompt_for_gear`` (including the new
``EMISSION CONTRACT`` + ``SUCCESS CRITERIA`` sections that the current
``boot.py`` does not yet extract), sends the resulting prompt to a fast
commercial model (Gemini 2.5 Flash by default; Claude Haiku 4.5 as a
fallback), and checks whether the model emits a schema-valid,
mode-correct envelope that passes the mode's structural + composite
success criteria.

Phase 1 added root-cause-analysis.
Phase 2 adds systems-dynamics, decision-under-uncertainty, competing-hypotheses.

Always-on unit tests (no network) live in ``TestModeFileStructure_*``;
the live-network Tier A test is gated by ``ORA_TIER_A_LIVE=1`` + a
Gemini API key in the keyring.

A CLI entry point drives the Tier A harness directly:

    python3 orchestrator/tests/test_mode_emission.py --mode systems-dynamics --runs 6
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))

WORKSPACE = ORCHESTRATOR.parent  # ~/ora
MODES_DIR = WORKSPACE / "modes"
BOOT_MD_PATH = WORKSPACE / "boot" / "boot.md"

from visual_validator import validate_envelope  # noqa: E402
from visual_adversarial import review_envelope  # noqa: E402

# WP-4.2: structural checkers + shared helpers live in the production
# ``mode_success_criteria`` module so the adversarial reviewer can reuse
# them. This test file imports the dispatch + the per-mode functions
# rather than redefining them.
from mode_success_criteria import (  # noqa: E402
    CriterionResult,
    RCA_CANONICAL,
    BANNED_EFFECT_PREFIXES,
    ACH_VOCAB,
    _LOOP_ID_RE,
    _first_error_detail,
    _short_alt_len,
    _semantic_description_complete,
    _preamble_checks,
    _concept_map_shape_ok,
    _pro_con_shape_ok,
    _mermaid_dsl_ok,
    _fishbone_max_depth,
    check_rca_structural,
    check_sd_structural,
    check_duu_structural,
    check_ch_structural,
    check_tm_structural,
    check_synthesis_structural,
    check_pe_structural,
    check_rm_structural,
    check_sp_structural,
    check_cm_structural,
    check_ba_structural,
    check_da_structural,
    check_cb_structural,
    check_cs_structural,
    check_si_structural,
    check_dc_structural,
    check_rt_structural,
)


# ---------------------------------------------------------------------------
# Canonical user queries per mode
# ---------------------------------------------------------------------------

CANONICAL_QUERIES: dict[str, list[str]] = {
    "root-cause-analysis": [
        "Draw a fishbone diagram explaining why software deployments fail "
        "intermittently. Keep it concise.",
        "A customer keeps getting duplicate charges on their monthly "
        "subscription. We've tried fixing the payment retry logic twice "
        "and it keeps happening. Walk me through the root causes.",
        "Our team ships a feature, it breaks in production, we roll back, "
        "fix it, ship again, and then a different thing breaks. Why does "
        "this keep happening?",
    ],
    "systems-dynamics": [
        "Map the feedback structure behind 'we keep hiring senior "
        "engineers to fix the problem, but the problem keeps getting "
        "worse.' What are the loops?",
        "Why does increasing our marketing spend briefly grow signups and "
        "then flatten them back below where we started? Show me the "
        "feedback loops.",
        "We've been running a 'zero-bug' sprint for three quarters and "
        "bug count keeps climbing. Give me the systems-dynamics view — "
        "variables, loops, and leverage points.",
    ],
    "decision-under-uncertainty": [
        "Should we launch the new product now or run a 3-month pilot "
        "first? The launch window closes in Q3 and a competitor is "
        "approaching. Walk me through the decision tree with payoffs.",
        "We're deciding whether to migrate to a new vector database. "
        "Build the decision with alternatives, probabilities, and "
        "expected outcomes in USD.",
        "Which of the five parameters below swings the NPV of our "
        "capital investment the most: discount rate, ramp time, launch "
        "price, COGS, churn? Give me the sensitivity analysis.",
    ],
    "competing-hypotheses": [
        "An admin user exfiltrated 40 GB of customer data overnight from "
        "an account that passed all MFA checks. Build me an ACH matrix "
        "of plausible explanations and rate the evidence.",
        "Our on-call paged at 03:00 for a database CPU spike; by 03:15 "
        "it was back to normal and nothing downstream alerted. Build "
        "competing hypotheses for what happened and score them.",
        "A portfolio startup missed their revenue projection by 60% "
        "despite reporting 'strong pipeline' last month. Build an ACH "
        "matrix of competing explanations and score the evidence.",
    ],
}


# ---------------------------------------------------------------------------
# Mode-file section extraction (mirrors boot.py's regex plus new sections)
# ---------------------------------------------------------------------------

SIMULATED_SECTIONS = [
    "DEPTH MODEL INSTRUCTIONS",
    "BREADTH MODEL INSTRUCTIONS",
    "CONTENT CONTRACT",
    "EMISSION CONTRACT",
    "GUARD RAILS",
    "SUCCESS CRITERIA",
]

REQUIRED_SECTIONS_11 = [
    "TRIGGER CONDITIONS",
    "EPISTEMOLOGICAL POSTURE",
    "DEFAULT GEAR",
    "RAG PROFILE",
    "DEPTH MODEL INSTRUCTIONS",
    "BREADTH MODEL INSTRUCTIONS",
    "CONTENT CONTRACT",
    "EMISSION CONTRACT",
    "GUARD RAILS",
    "SUCCESS CRITERIA",
    "KNOWN FAILURE MODES",
]


def _extract_section(text: str, heading: str) -> str:
    pattern = rf"## {re.escape(heading)}\s*\n(.*?)(?=\n## |\Z)"
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1).strip() if m else ""


def build_simulated_system_prompt(mode_name: str,
                                   emit_last: bool = False) -> str:
    """Simulate the Phase-4-updated ``build_system_prompt_for_gear`` output.

    Phase 6 ``emit_last`` flag (Track A5 — prompt-reordering experiment):
    when True, move the ``EMISSION CONTRACT`` block to after
    ``SUCCESS CRITERIA`` and ``GUARD RAILS`` so the emission spec sits at
    the tail of the prompt (recency-bias attention hypothesis). The
    default ordering preserves Phase 4 behaviour.
    """
    mode_text = (MODES_DIR / f"{mode_name}.md").read_text()
    boot_md = BOOT_MD_PATH.read_text()
    parts: list[str] = [boot_md]

    if emit_last:
        ordering = [
            "DEPTH MODEL INSTRUCTIONS",
            "BREADTH MODEL INSTRUCTIONS",
            "CONTENT CONTRACT",
            "SUCCESS CRITERIA",
            "GUARD RAILS",
            "EMISSION CONTRACT",  # moved to the tail
        ]
    else:
        ordering = SIMULATED_SECTIONS

    for heading in ordering:
        section = _extract_section(mode_text, heading)
        if section:
            parts.append(f"\n## {heading}\n\n{section}")
    parts.append(
        "\n## PIPELINE SIMULATION\n\n"
        "You are the analysis model in the Ora Gear-3 pipeline. Emit your "
        "full analytical response (prose sections in the order specified "
        "by CONTENT CONTRACT, then exactly one fenced `ora-visual` block "
        "per EMISSION CONTRACT). Do not include chain-of-thought markers, "
        "do not preface with meta-commentary, and do not ask clarifying "
        "questions; where the user's prompt is ambiguous, make plausible "
        "assumptions about the domain and state them in prose."
    )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Envelope extraction
# ---------------------------------------------------------------------------

FENCE_RE = re.compile(r"```ora-visual\s*\n(.*?)\n```", re.DOTALL)


def extract_envelopes(response: str) -> list[dict]:
    """Pull every ``ora-visual`` fenced block out of ``response`` and parse."""
    out: list[dict] = []
    for block in FENCE_RE.findall(response):
        try:
            out.append(json.loads(block))
        except json.JSONDecodeError as e:
            out.append({"__parse_error": True, "error": str(e), "raw": block})
    return out


# ---------------------------------------------------------------------------
# Phase 6 — cascade helpers (reused by TestCascade_* and by
# ``run_cascade_tier_a`` below). Kept at module scope so both the live
# tests and the CLI sweep harness can import them.
# ---------------------------------------------------------------------------

EMISSION_REMINDER_SUFFIX = (
    "\n\n**EMISSION REMINDER:** The fenced `ora-visual` block is REQUIRED "
    "as the final block of your response. Emit the envelope now."
)


def _load_framework_text(name: str) -> str:
    from boot import load_framework  # type: ignore
    return load_framework(name)


def _build_cascade_prompt(mode_name: str, step: str,
                          slot: str = "breadth") -> str:
    """Build a full cascade system prompt by combining the mode-specific
    subsections (via ``build_system_prompt_for_gear`` with the step param)
    and the appropriate universal F-* scaffolding.

    Phase 5 design: F-* files carry the universal contract; mode files
    carry per-step mode-specific content. This helper reassembles them in
    the order the model sees at live inference.
    """
    from boot import build_system_prompt_for_gear  # type: ignore
    mode_text = (MODES_DIR / f"{mode_name}.md").read_text()
    ctx = {
        "mode_text": mode_text,
        "mode_name": mode_name,
        "conversation_rag": "",
        "concept_rag": "",
        "relationship_rag": "",
        "rag_utilization": "",
    }
    step_prompt = build_system_prompt_for_gear(ctx, slot=slot, step=step)
    framework_map = {
        "analyst": None,  # mode directives replace F-ANALYSIS-*
        "evaluator": "f-evaluate.md",
        "reviser": "f-revise.md",
        "verifier": "f-verify.md",
        "consolidator": "f-consolidate.md",
    }
    framework_name = framework_map.get(step)
    if framework_name:
        framework_text = _load_framework_text(framework_name)
        return (
            f"{step_prompt}\n\n"
            f"## F-* UNIVERSAL SCAFFOLDING — {framework_name}\n\n"
            f"{framework_text}"
        )
    return step_prompt


def _extract_revised_draft(reviser_response: str) -> str:
    """Extract the body of the ``## REVISED DRAFT`` section from a
    reviser response per the Phase 5 mirror contract (ADDRESSED /
    NOT ADDRESSED / INCORPORATED / DECLINED / REMAINING UNCERTAINTIES
    / REVISED DRAFT / CHANGELOG). The revised analyst output inside
    this section may itself use ``##`` headings for mode-specific
    prose structure (e.g. RCA's "Chosen framework"), so we specifically
    stop at ``## CHANGELOG`` — the final mirror-contract heading — and
    fall through to end of text when CHANGELOG is absent. Returns empty
    string only when the REVISED DRAFT heading itself is missing; the
    cascade-aware harness treats that as a cascade failure.
    """
    m = re.search(
        r"##\s+REVISED DRAFT\s*\n(.*?)(?=\n##\s+CHANGELOG\b|\Z)",
        reviser_response,
        re.DOTALL,
    )
    return m.group(1).strip() if m else ""


# ---------------------------------------------------------------------------
# Shared criterion-result + structural checkers live in
# ``orchestrator/mode_success_criteria`` (see import block at top of file).
# This file keeps only the prose-aware **composite** checkers and the
# ``_all_leaves`` helper the RCA composite checker uses.
# ---------------------------------------------------------------------------


def _all_leaves(categories: list[dict]) -> list[tuple[str, ...]]:
    leaves: list[tuple[str, ...]] = []

    def walk(causes, trail: tuple[str, ...] = ()) -> None:
        for c in causes or []:
            sub = c.get("sub_causes")
            if sub:
                walk(sub, trail + (c.get("text", ""),))
            else:
                leaves.append(trail + (c.get("text", ""),))

    for cat in categories:
        walk(cat.get("causes", []))
    return leaves


def check_rca_composite(prose: str, envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []

    def add(id_: str, passed: bool, detail: str = "") -> None:
        results.append(CriterionResult(id=id_, passed=passed, detail=detail))

    if envelope.get("type") != "fishbone":
        for cid in ("C1", "C2", "C3", "C4"):
            add(cid, True, "cld: composite checks deferred to systems-dynamics")
        return results

    spec = envelope.get("spec") or {}
    framework = spec.get("framework") or ""
    add("C1", bool(framework) and framework in prose,
        f"framework={framework}")

    effect = (spec.get("effect") or "").strip()

    def _stems(text: str) -> set[str]:
        return {w[:5] for w in re.findall(r"[a-zA-Z]{3,}", text.lower())}
    stems_effect = _stems(effect)
    stopwords = {"the", "and", "for", "with", "that", "this",
                 "from", "into", "onto", "are", "have", "has", "had",
                 "whe", "wha"}
    stems_effect -= {w[:5] for w in stopwords}
    stems_prose = _stems(prose[:2000])
    overlap = (
        len(stems_effect & stems_prose) / len(stems_effect)
        if stems_effect else 0.0
    )
    add("C2", overlap >= 0.6, f"stem_overlap={overlap:.2f}")

    cats = spec.get("categories") or []
    missing_in_prose = [c.get("name") for c in cats
                        if c.get("name") and c.get("name") not in prose]
    add("C3", len(missing_in_prose) == 0,
        f"categories_not_in_prose={missing_in_prose}")

    root_section = re.search(
        r"(?:root cause|root causes?)[:\s\-]*\n?(.{0,1500})",
        prose, re.IGNORECASE | re.DOTALL,
    )
    if root_section:
        rs = root_section.group(1).lower()
        leaves = _all_leaves(cats)
        sample = [leaf[-1] for leaf in leaves[:8] if leaf[-1]]
        hits = [s for s in sample
                if s and any(tok in rs for tok in
                             re.findall(r"[a-zA-Z]{4,}", s.lower())[:3])]
        add("C4", len(hits) >= 1,
            f"prose-root-hits={len(hits)}/{len(sample)}")
    else:
        add("C4", False, "no prose 'Root cause' section found")

    return results


def check_sd_composite(prose: str, envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []

    def add(id_: str, passed: bool, detail: str = "") -> None:
        results.append(CriterionResult(id=id_, passed=passed, detail=detail))

    spec = envelope.get("spec") or {}
    if envelope.get("type") != "causal_loop_diagram":
        for cid in ("C1", "C2", "C3", "C4"):
            add(cid, True, "s&f: composite checks deferred")
        return results

    loops = spec.get("loops") or []
    variables = spec.get("variables") or []
    var_labels = {v.get("id"): (v.get("label") or "") for v in variables}

    # C1 loop name traceability — id OR label mentioned in prose
    loop_hits = [lp for lp in loops
                 if (lp.get("id") and lp.get("id") in prose)
                 or (lp.get("label") and lp.get("label") in prose)]
    add("C1", len(loop_hits) == len(loops),
        f"loops_in_prose={len(loop_hits)}/{len(loops)}")

    # C2 variable coverage — every loop member exists in variables and is in prose
    loop_members: set[str] = set()
    for lp in loops:
        for m in lp.get("members") or []:
            loop_members.add(m)
    missing_in_prose: list[str] = []
    for m in loop_members:
        if m in prose:
            continue
        label = var_labels.get(m, "")
        if label and label in prose:
            continue
        missing_in_prose.append(m)
    add("C2", len(missing_in_prose) == 0,
        f"loop_members_not_in_prose={missing_in_prose}")

    # C3 polarity consistency
    prose_low = prose.lower()
    mentions_balancing = any(tok in prose_low
                             for tok in ("balancing", "balance loop"))
    mentions_reinforcing = any(tok in prose_low
                               for tok in ("reinforcing", "reinforce"))
    has_B = any(lp.get("type") == "B" for lp in loops)
    has_R = any(lp.get("type") == "R" for lp in loops)
    c3_ok = True
    if mentions_balancing and not has_B:
        c3_ok = False
    if mentions_reinforcing and not has_R:
        c3_ok = False
    add("C3", c3_ok,
        f"prose_bal={mentions_balancing} bal={has_B} "
        f"prose_reinf={mentions_reinforcing} reinf={has_R}")

    # C4 boundary in prose
    add("C4",
        any(tok in prose_low
            for tok in ("boundar", "outside the system",
                        "inside the system", "in scope", "out of scope")),
        "")
    return results


def check_duu_composite(prose: str, envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []

    def add(id_: str, passed: bool, detail: str = "") -> None:
        results.append(CriterionResult(id=id_, passed=passed, detail=detail))

    spec = envelope.get("spec") or {}
    vtype = envelope.get("type")
    prose_low = prose.lower()

    if vtype == "decision_tree":
        root = spec.get("root") or {}
        first_branches = [c.get("edge_label", "") or ""
                          for c in (root.get("children") or [])]
        # C1 recommendation: ≥1 first-level branch label appears in prose
        recommended = [b for b in first_branches
                       if b and b.lower() in prose_low]
        add("C1", len(recommended) >= 1,
            f"branches={first_branches} matched={recommended}")
        # C2 alternatives coverage: most first branches mentioned (by any 4+ char token)
        hits = []
        for b in first_branches:
            if not b:
                continue
            toks = [t.lower() for t in re.findall(r"[a-zA-Z]{4,}", b)]
            if any(t in prose_low for t in toks):
                hits.append(b)
        add("C2", len(hits) >= max(1, len(first_branches) - 1),
            f"alternatives_covered={len(hits)}/{len(first_branches)}")
        # C3 probabilities addressed in prose
        probs_in_spec: list[float] = []

        def walk(node: dict) -> None:
            for c in node.get("children") or []:
                if "probability" in c:
                    probs_in_spec.append(float(c["probability"]))
                inner = c.get("node")
                if isinstance(inner, dict):
                    walk(inner)
        walk(root)
        signals = ("probability", "likelihood", "chance", "odds", "%",
                   "likely", "unlikely")
        add("C3",
            len(probs_in_spec) == 0
            or any(t in prose_low for t in signals),
            f"probs_in_spec={len(probs_in_spec)} "
            f"prose_signals={any(t in prose_low for t in signals)}")
        # C4 units agreement when mode=decision
        if spec.get("mode") == "decision":
            units = spec.get("utility_units") or ""
            toks = [t.lower() for t in re.findall(r"[a-zA-Z]{3,}", units)]
            hit = any(t in prose_low for t in toks) if toks else False
            add("C4", hit, f"units={units!r}")
        else:
            add("C4", True, "mode=probability; units n/a")
    else:
        # influence_diagram and tornado get lighter composite checks
        for cid in ("C1", "C2", "C3", "C4"):
            add(cid, True, f"{vtype}: composite checks light")

    return results


def check_ch_composite(prose: str, envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []

    def add(id_: str, passed: bool, detail: str = "") -> None:
        results.append(CriterionResult(id=id_, passed=passed, detail=detail))

    spec = envelope.get("spec") or {}
    hypotheses = spec.get("hypotheses") or []
    evidence = spec.get("evidence") or []
    cells = spec.get("cells") or {}

    # C1 hypothesis traceability
    hyp_hits = [h for h in hypotheses
                if (h.get("id") and h.get("id") in prose)
                or (h.get("label") and h.get("label") in prose)]
    add("C1", len(hyp_hits) >= max(1, len(hypotheses) - 1),
        f"hyp_in_prose={len(hyp_hits)}/{len(hypotheses)}")

    # C2 evidence traceability — match id OR any first-3 words of text
    ev_hits = []
    for e in evidence:
        eid = e.get("id") or ""
        text = e.get("text") or ""
        if eid and eid in prose:
            ev_hits.append(e)
            continue
        words = re.findall(r"[a-zA-Z]{4,}", text)[:3]
        if words and any(w in prose for w in words):
            ev_hits.append(e)
    add("C2", len(ev_hits) >= max(1, len(evidence) - 1),
        f"ev_in_prose={len(ev_hits)}/{len(evidence)}")

    # C3 conclusion tally: winner = fewest (I+II), tie-break on fewer II
    if hypotheses:
        scores: dict[str, tuple[int, int]] = {}
        for h in hypotheses:
            hid = h.get("id") or ""
            negs = 0
            neg2 = 0
            for e in evidence:
                v = cells.get(e.get("id"), {}).get(hid)
                if v in ("I", "II"):
                    negs += 1
                if v == "II":
                    neg2 += 1
            scores[hid] = (negs, neg2)
        winner_id = min(scores, key=lambda k: scores[k])
        winner_label = next((h.get("label") for h in hypotheses
                             if h.get("id") == winner_id), "") or ""
        conc_match = re.search(
            r"(?:tentative conclusion|conclusion|surviv|survives)"
            r"[^\n]*\n(.{0,1500})",
            prose, re.IGNORECASE | re.DOTALL,
        )
        conc_region = conc_match.group(1) if conc_match else prose[-1500:]
        winner_found = (
            (winner_id in conc_region)
            or (winner_label and winner_label in conc_region)
        )
        add("C3", winner_found,
            f"winner={winner_id}({winner_label!r}) "
            f"found_in_conclusion={winner_found}")
    else:
        add("C3", False, "no hypotheses")

    # C4 non-diagnostic evidence claim matches uniform row
    nondiag = re.search(r"non[- ]diagnostic", prose, re.IGNORECASE)
    if nondiag:
        window = prose[max(0, nondiag.start() - 50): nondiag.end() + 200]
        ref = re.search(r"E\d+", window)
        if ref:
            rid = ref.group(0)
            row = cells.get(rid, {})
            values = set(row.values()) if row else set()
            uniform = len(values) <= 1
            add("C4", uniform, f"ref={rid} uniform={uniform}")
        else:
            add("C4", True,
                "non-diagnostic claim present, no specific E-id cited")
    else:
        add("C4", True, "no non-diagnostic claim in prose")

    return results


# ---------------------------------------------------------------------------
# Phase 3 composite checkers — use shared helpers from
# ``mode_success_criteria`` (imported at top of this file).
# ---------------------------------------------------------------------------

def _tokens_in_prose(prose: str, label: str, min_chars: int = 4) -> bool:
    """Return True if any ≥min_chars substring of label appears in prose."""
    for tok in re.findall(rf"[a-zA-Z]{{{min_chars},}}", label):
        if tok in prose:
            return True
    return bool(label) and label in prose


def check_tm_composite(prose: str, envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    spec = envelope.get("spec") or {}
    fq = (spec.get("focus_question") or "").lower()
    prose_low = prose.lower()
    fq_tokens = set(re.findall(r"[a-zA-Z]{4,}", fq))
    prose_tokens = set(re.findall(r"[a-zA-Z]{4,}", prose_low))
    overlap = (len(fq_tokens & prose_tokens) / len(fq_tokens)
               if fq_tokens else 0.0)
    add("C1", overlap >= 0.5, f"focus_overlap={overlap:.2f}")
    concepts = spec.get("concepts") or []
    missing = [c.get("label") for c in concepts
               if c.get("label") and not _tokens_in_prose(prose, c.get("label"))]
    add("C2", len(missing) <= 1,
        f"concept_labels_missing={len(missing)}/{len(concepts)}")
    cross = [p for p in (spec.get("propositions") or []) if p.get("is_cross_link")]
    add("C3", len(cross) >= 1, f"cross_links={len(cross)}")
    return results


def check_synthesis_composite(prose: str, envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    spec = envelope.get("spec") or {}
    concepts = spec.get("concepts") or []
    missing = [c.get("label") for c in concepts
               if c.get("label") and not _tokens_in_prose(prose, c.get("label"))]
    add("C1", len(missing) <= 2,
        f"missing={len(missing)}/{len(concepts)}")
    cross = [p for p in (spec.get("propositions") or []) if p.get("is_cross_link")]
    add("C2", len(cross) >= 1, f"cross_links={len(cross)}")
    prose_low = prose.lower()
    has_parallel_word = any(
        w in prose_low for w in ("parallel", "correspond", "isomorph", "map", "analog")
    )
    add("C3", has_parallel_word, "mentions structural parallelism")
    return results


def check_pe_composite(prose: str, envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    spec = envelope.get("spec") or {}
    concepts = spec.get("concepts") or []
    missing = [c.get("label") for c in concepts
               if c.get("label") and not _tokens_in_prose(prose, c.get("label"))]
    add("C1", len(missing) <= 2, f"missing={len(missing)}/{len(concepts)}")
    prose_low = prose.lower()
    open_q_count = sum(1 for sig in ("?", "wonder", "question", "could we", "what if")
                       if sig in prose_low)
    add("C2", open_q_count >= 2, f"open_q_signals={open_q_count}")
    for cid in ("C3", "C4"):
        add(cid, True, "passion: reduced composite")
    return results


def check_rm_composite(prose: str, envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    prose_low = prose.lower()
    add("C1", any(w in prose_low for w in ("caus", "depend", "corrrelat", "influenc")),
        "connection types mentioned")
    add("C2", "boundar" in prose_low or "out of scope" in prose_low or
        "does not include" in prose_low, "boundary mentioned")
    add("C3", True, "rm: C3 reserved")
    add("C4", True, "rm: C4 reserved")
    return results


def check_sp_composite(prose: str, envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    spec = envelope.get("spec") or {}
    quadrants = spec.get("quadrants") or {}
    names = [quadrants.get(k, {}).get("name", "")
             for k in ("TL", "TR", "BL", "BR")]
    missing = [n for n in names if n and not _tokens_in_prose(prose, n)]
    add("C1", len(missing) <= 1,
        f"quadrant_names_missing={len(missing)}/4")
    ind_in_prose = 0
    for k in ("TL", "TR", "BL", "BR"):
        for ind in quadrants.get(k, {}).get("indicators") or []:
            if _tokens_in_prose(prose, ind):
                ind_in_prose += 1
    add("C2", ind_in_prose >= 2, f"indicators_in_prose={ind_in_prose}")
    x_axis = (spec.get("x_axis") or {}).get("label", "")
    y_axis = (spec.get("y_axis") or {}).get("label", "")
    add("C3",
        _tokens_in_prose(prose, x_axis) and _tokens_in_prose(prose, y_axis),
        f"x_axis={x_axis!r} y_axis={y_axis!r}")
    return results


def check_cm_composite(prose: str, envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    spec = envelope.get("spec") or {}
    vtype = envelope.get("type")
    if vtype == "quadrant_matrix":
        items = spec.get("items") or []
        in_prose = [it for it in items
                    if _tokens_in_prose(prose, it.get("label") or "")]
        add("C1", len(in_prose) >= max(1, len(items) - 1),
            f"items_in_prose={len(in_prose)}/{len(items)}")
        for cid in ("C2", "C3"):
            add(cid, True, "qm: C2/C3 reserved")
    else:  # pro_con
        pros = spec.get("pros") or []
        cons = spec.get("cons") or []
        p_in = sum(1 for p in pros if _tokens_in_prose(prose, p.get("text", "")))
        c_in = sum(1 for c in cons if _tokens_in_prose(prose, c.get("text", "")))
        add("C1",
            p_in >= max(1, len(pros) - 1) and c_in >= max(1, len(cons) - 1),
            f"pros_in_prose={p_in}/{len(pros)} cons={c_in}/{len(cons)}")
        for cid in ("C2", "C3"):
            add(cid, True, "pc: C2/C3 reserved")
    return results


def check_ba_composite(prose: str, envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    spec = envelope.get("spec") or {}
    vtype = envelope.get("type")
    if vtype == "pro_con":
        claim = spec.get("claim") or ""
        add("C1", _tokens_in_prose(prose, claim), f"claim_in_prose")
        pros = spec.get("pros") or []
        cons = spec.get("cons") or []
        p_in = sum(1 for p in pros if _tokens_in_prose(prose, p.get("text", "")))
        c_in = sum(1 for c in cons if _tokens_in_prose(prose, c.get("text", "")))
        add("C2",
            p_in >= max(1, len(pros) - 1) and c_in >= max(1, len(cons) - 1),
            f"pros={p_in}/{len(pros)} cons={c_in}/{len(cons)}")
    else:
        for cid in ("C1", "C2"):
            add(cid, True, "tornado: C1/C2 reserved")
    for cid in ("C3", "C4"):
        add(cid, True, "ba: C3/C4 reserved")
    return results


def check_da_composite(prose: str, envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    spec = envelope.get("spec") or {}
    nodes = spec.get("nodes") or []
    ideas = [n for n in nodes if n.get("type") == "idea"]
    if ideas:
        hits = sum(1 for n in ideas if _tokens_in_prose(prose, n.get("text", "")))
        add("C1", hits >= max(1, len(ideas) - 1),
            f"ideas_in_prose={hits}/{len(ideas)}")
    else:
        add("C1", False, "no idea nodes")
    cons = [n for n in nodes if n.get("type") == "con"]
    if cons:
        hits_c = sum(1 for n in cons if _tokens_in_prose(prose, n.get("text", "")))
        add("C2", hits_c >= 1, f"cons_in_prose={hits_c}/{len(cons)}")
    else:
        add("C2", False, "no con nodes")
    for cid in ("C3", "C4"):
        add(cid, True, "da: C3/C4 reserved")
    return results


def check_cb_composite(prose: str, envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    prose_low = prose.lower()
    add("C1", any(w in prose_low for w in ("author", "advocat", "institution")),
        "authorship named")
    add("C2", any(w in prose_low for w in ("benefic", "exempt", "bears cost", "loses")),
        "beneficiaries/cost-bearers named")
    for cid in ("C3", "C4"):
        add(cid, True, "cb: C3/C4 reserved")
    return results


def check_cs_composite(prose: str, envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    spec = envelope.get("spec") or {}
    vtype = envelope.get("type")
    if vtype == "causal_dag":
        exposure = spec.get("focal_exposure") or ""
        outcome = spec.get("focal_outcome") or ""
        add("C1", _tokens_in_prose(prose, exposure), f"exposure={exposure}")
        add("C2", _tokens_in_prose(prose, outcome), f"outcome={outcome}")
    else:
        for cid in ("C1", "C2"):
            add(cid, True, "fc: C1/C2 reserved")
    for cid in ("C3", "C4"):
        add(cid, True, "cs: C3/C4 reserved")
    return results


def check_si_composite(prose: str, envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    # light composite — the heavy lifting is in the semantic layer
    for cid in ("C1", "C2", "C3"):
        add(cid, True, "si: composite light for Phase 1")
    return results


# No-visual modes: envelope absence is the pass condition
def check_no_visual_structural(mode_name: str) -> Callable[[dict], list[CriterionResult]]:
    """Return a structural checker that treats envelope ABSENCE as pass.

    Used by steelman-construction and paradigm-suspension. The checker
    is called with an envelope dict, but in these modes the caller's
    path should normally be "no envelope extracted" → S1 fails. That
    means `run_tier_a` needs special handling: see the dispatch below.
    """
    def _checker(envelope: dict) -> list[CriterionResult]:
        # If this is called, envelope WAS extracted, which is a failure.
        return [
            CriterionResult(id="S1", passed=False,
                            detail=f"{mode_name}: envelope present but mode is no-visual"),
        ]
    return _checker


def _no_visual_composite(prose: str, envelope: dict) -> list[CriterionResult]:
    return []


def _light_composite(prose: str, envelope: dict) -> list[CriterionResult]:
    return []


# Project-mode and structured-output: treat as dispatch / passthrough
# For Tier A we skip them (they are validated via the always-on tests only).


# ---------------------------------------------------------------------------
# Mode dispatch
# ---------------------------------------------------------------------------

@dataclass
class ModeSpec:
    name: str
    structural: Callable[[dict], list[CriterionResult]]
    composite: Callable[[str, dict], list[CriterionResult]]
    canonical_queries: list[str]
    expected_envelope_types: set[str]
    expected_criterion_ids: list[str]


# Canonical queries for Phase 3 modes (for CLI / Tier A entry)
CANONICAL_QUERIES.update({
    "terrain-mapping": [
        "Give me the lay of the land on retrieval-augmented generation — "
        "what's settled, what's contested, what I need to know to build with it.",
        "Map the domain of Bayesian statistics for me — major sub-areas, "
        "schools, and the key debates.",
        "I'm new to monetary policy. Walk me through the landscape.",
    ],
    "synthesis": [
        "Synthesise organisational ecology (Hannan & Freeman) with gene-drift "
        "population biology. Where do they structurally correspond?",
        "How does Clausewitz's concept of friction map onto modern incident "
        "management in software operations?",
        "Connect Marcus Aurelius's premeditatio malorum with modern scenario "
        "planning — what's the structural parallel?",
    ],
    "passion-exploration": [
        "I've been wondering about cities as metabolic organisms. Help me "
        "think about this.",
        "What's the link between ritual and software rollouts? I want to "
        "explore this openly.",
        "I've been thinking about musical improvisation lately, especially "
        "how soloists choose to play inside or outside the changes.",
    ],
    "relationship-mapping": [
        "Map the causal DAG for job satisfaction at a tech company — "
        "compensation, autonomy, manager quality, team dynamics, career "
        "growth. What's the causal structure?",
        "Draw the dependency graph for our backend services: auth, billing, "
        "notifications, search, recommendations. What's the relational structure?",
        "Map the relationship structure between the concepts: skill, "
        "deliberate practice, feedback loops, domain knowledge, mentorship.",
    ],
    "scenario-planning": [
        "Build four scenarios for the US-China semiconductor relationship "
        "over the next decade. What are the driving uncertainties?",
        "Construct a scenario matrix for AI labs in 2030 — what two "
        "uncertainties dominate?",
        "Scenario matrix for the future of remote work — what critical "
        "uncertainties shape 2028?",
    ],
    "constraint-mapping": [
        "We need to pick a database: Postgres, DynamoDB, or CockroachDB. "
        "Map the tradeoffs.",
        "Compare three approaches to incident postmortems: blameless-written, "
        "blameless-live, and accountability-based. Map the alternatives.",
        "Hiring tradeoffs: senior generalist, senior specialist, or mid-level "
        "generalist. Lay out the constraints.",
    ],
    "benefits-analysis": [
        "PMI on adopting a four-day work week across engineering. Plus, "
        "minus, interesting — don't recommend, just surface the envelope.",
        "Benefits analysis of open-sourcing our core library. What are "
        "the Plus, Minus, and Interesting implications?",
        "Evaluate the proposal to move from quarterly to monthly planning "
        "cycles — full PMI.",
    ],
    "dialectical-analysis": [
        "Thesis: software security and developer velocity are in fundamental "
        "tension. Work through this dialectically.",
        "Drive freedom vs security dialectically — thesis, antithesis, "
        "sublation if possible.",
        "Open-source vs proprietary AI models: is this a genuine dialectic "
        "or a false dichotomy? Drive it through to sublation or declare "
        "irreducibility.",
    ],
    "cui-bono": [
        "The SEC's materiality threshold for financial reporting disclosure "
        "is 5% of earnings. Cui bono — who benefits from that specific number?",
        "Carbon offsetting standards set at 1-tonne CO2 as the unit of trading. "
        "Whose interests does that serve?",
        "The ASVAB military entrance exam cuts candidates at a specific score. "
        "Cui bono? Who's the institutional author and who benefits?",
    ],
    "consequences-and-sequel": [
        "We're raising our pricing by 40%. Trace the forward cascade — first, "
        "second, and third order.",
        "The city raises minimum wage in urban centres to $22/hr. Cascade "
        "out three orders.",
        "We're deprecating our v1 API in 90 days. What's the forward cascade "
        "on customers, on internal teams, on our roadmap?",
    ],
    "strategic-interaction": [
        "We're competing with Firm B on pricing. They know our price first. "
        "Model this as a game tree with backward induction.",
        "Two labs are deciding whether to release a capability jump publicly "
        "or keep it private. Model the game and find the equilibrium.",
        "Regulator and incumbent in a new rulemaking cycle. Model the "
        "strategic interaction with credibility assessment.",
    ],
    "steelman-construction": [
        "Steelman the position that large language models are a dead end "
        "for AGI. I want the strongest version before I critique it.",
        "Build the strongest case for permitting self-modifying code in "
        "production. Steelman the 'yes' position.",
        "Steelman the argument that universities should be abolished. "
        "Strongest possible version, then critique it.",
    ],
    "deep-clarification": [
        "Explain how TCP retransmission actually works — not the surface, "
        "the mechanism beneath it.",
        "Why does the expected value of a lottery ticket differ from its "
        "price? Push past the surface.",
        "How does modular arithmetic actually underpin RSA — not just the "
        "equations, the mechanism.",
    ],
    "paradigm-suspension": [
        "Suspend the paradigm that growth is the metric of economic health. "
        "What assumptions is that claim load-bearing on?",
        "Question the standard view that memory is stored in neurons. "
        "Identify the foundational assumptions.",
        "The consensus is that intelligence is primarily biological. "
        "Suspend the paradigm — what's load-bearing?",
    ],
    "red-team": [
        "Here's my plan to migrate the customer database from Postgres to "
        "DynamoDB over a 90-day window. Stress-test it before I commit.",
        "Pre-mortem this product launch — assume we're going to fail, tell "
        "me how, and rank the failure modes by severity.",
        "I'm about to send this team-reorg proposal to leadership. Pick it "
        "apart — what's weak, what am I missing, where would a hostile "
        "reviewer attack first?",
    ],
})


MODE_SPECS: dict[str, ModeSpec] = {
    # Phase 1
    "root-cause-analysis": ModeSpec(
        name="root-cause-analysis",
        structural=check_rca_structural,
        composite=check_rca_composite,
        canonical_queries=CANONICAL_QUERIES["root-cause-analysis"],
        expected_envelope_types={"fishbone", "causal_loop_diagram"},
        expected_criterion_ids=["S1", "S6", "S10", "S12",
                                "M1", "M4", "C1", "C4"],
    ),
    # Phase 2
    "systems-dynamics": ModeSpec(
        name="systems-dynamics",
        structural=check_sd_structural,
        composite=check_sd_composite,
        canonical_queries=CANONICAL_QUERIES["systems-dynamics"],
        expected_envelope_types={"causal_loop_diagram", "stock_and_flow"},
        expected_criterion_ids=["S1", "S6", "S9", "S10", "S12",
                                "M1", "M5", "C1", "C4"],
    ),
    "decision-under-uncertainty": ModeSpec(
        name="decision-under-uncertainty",
        structural=check_duu_structural,
        composite=check_duu_composite,
        canonical_queries=CANONICAL_QUERIES["decision-under-uncertainty"],
        expected_envelope_types={"decision_tree", "influence_diagram",
                                 "tornado"},
        expected_criterion_ids=["S1", "S6", "S7", "S8", "S12",
                                "M1", "M4", "C1", "C4"],
    ),
    "competing-hypotheses": ModeSpec(
        name="competing-hypotheses",
        structural=check_ch_structural,
        composite=check_ch_composite,
        canonical_queries=CANONICAL_QUERIES["competing-hypotheses"],
        expected_envelope_types={"ach_matrix"},
        expected_criterion_ids=["S1", "S7", "S9", "S10", "S12",
                                "M1", "M2", "C1", "C3"],
    ),
    # Phase 3
    "terrain-mapping": ModeSpec(
        name="terrain-mapping",
        structural=check_tm_structural,
        composite=check_tm_composite,
        canonical_queries=CANONICAL_QUERIES["terrain-mapping"],
        expected_envelope_types={"concept_map"},
        expected_criterion_ids=["S1", "S7", "S10", "S11",
                                "M1", "M4", "C1", "C3"],
    ),
    "synthesis": ModeSpec(
        name="synthesis",
        structural=check_synthesis_structural,
        composite=check_synthesis_composite,
        canonical_queries=CANONICAL_QUERIES["synthesis"],
        expected_envelope_types={"concept_map"},
        expected_criterion_ids=["S1", "S7", "S10", "S12",
                                "M2", "M4", "C1", "C2"],
    ),
    "passion-exploration": ModeSpec(
        name="passion-exploration",
        structural=check_pe_structural,
        composite=check_pe_composite,
        canonical_queries=CANONICAL_QUERIES["passion-exploration"],
        expected_envelope_types={"concept_map"},
        expected_criterion_ids=["S1", "S7", "M1", "M3", "C1"],
    ),
    "relationship-mapping": ModeSpec(
        name="relationship-mapping",
        structural=check_rm_structural,
        composite=check_rm_composite,
        canonical_queries=CANONICAL_QUERIES["relationship-mapping"],
        expected_envelope_types={"concept_map", "causal_dag"},
        expected_criterion_ids=["S1", "S7", "S8", "M1", "M4", "C1"],
    ),
    "scenario-planning": ModeSpec(
        name="scenario-planning",
        structural=check_sp_structural,
        composite=check_sp_composite,
        canonical_queries=CANONICAL_QUERIES["scenario-planning"],
        expected_envelope_types={"quadrant_matrix"},
        expected_criterion_ids=["S1", "S7", "S8", "S10",
                                "M2", "M5", "C1", "C3"],
    ),
    "constraint-mapping": ModeSpec(
        name="constraint-mapping",
        structural=check_cm_structural,
        composite=check_cm_composite,
        canonical_queries=CANONICAL_QUERIES["constraint-mapping"],
        expected_envelope_types={"quadrant_matrix", "pro_con"},
        expected_criterion_ids=["S1", "S7", "S10", "M1", "M5", "C1"],
    ),
    "benefits-analysis": ModeSpec(
        name="benefits-analysis",
        structural=check_ba_structural,
        composite=check_ba_composite,
        canonical_queries=CANONICAL_QUERIES["benefits-analysis"],
        expected_envelope_types={"pro_con", "tornado"},
        expected_criterion_ids=["S1", "S7", "M1", "M5", "C1"],
    ),
    "dialectical-analysis": ModeSpec(
        name="dialectical-analysis",
        structural=check_da_structural,
        composite=check_da_composite,
        canonical_queries=CANONICAL_QUERIES["dialectical-analysis"],
        expected_envelope_types={"ibis"},
        expected_criterion_ids=["S1", "S7", "S8", "S10",
                                "M2", "M3", "C1", "C2"],
    ),
    "cui-bono": ModeSpec(
        name="cui-bono",
        structural=check_cb_structural,
        composite=check_cb_composite,
        canonical_queries=CANONICAL_QUERIES["cui-bono"],
        expected_envelope_types={"flowchart", "concept_map"},
        expected_criterion_ids=["S1", "S7", "S10", "M1", "M4", "C1"],
    ),
    "consequences-and-sequel": ModeSpec(
        name="consequences-and-sequel",
        structural=check_cs_structural,
        composite=check_cs_composite,
        canonical_queries=CANONICAL_QUERIES["consequences-and-sequel"],
        expected_envelope_types={"causal_dag", "flowchart"},
        expected_criterion_ids=["S1", "S8", "S9", "M1", "M2", "C1"],
    ),
    "strategic-interaction": ModeSpec(
        name="strategic-interaction",
        structural=check_si_structural,
        composite=check_si_composite,
        canonical_queries=CANONICAL_QUERIES["strategic-interaction"],
        expected_envelope_types={"decision_tree", "influence_diagram"},
        expected_criterion_ids=["S1", "S7", "S8", "M1", "M3", "C1"],
    ),
    # Phase 3 — no-visual modes (envelope absence is the pass condition)
    "steelman-construction": ModeSpec(
        name="steelman-construction",
        structural=check_no_visual_structural("steelman-construction"),
        composite=_no_visual_composite,
        canonical_queries=CANONICAL_QUERIES["steelman-construction"],
        expected_envelope_types=set(),  # no envelope expected
        expected_criterion_ids=["S1", "S2", "M1", "M3", "M5"],
    ),
    "deep-clarification": ModeSpec(
        name="deep-clarification",
        structural=check_dc_structural,
        composite=_light_composite,
        canonical_queries=CANONICAL_QUERIES["deep-clarification"],
        expected_envelope_types={"flowchart"},
        expected_criterion_ids=["S1", "S3", "M1", "M2", "M3"],
    ),
    "red-team": ModeSpec(
        name="red-team",
        structural=check_rt_structural,
        composite=_light_composite,
        canonical_queries=CANONICAL_QUERIES["red-team"],
        expected_envelope_types={"concept_map", "flowchart", "causal_loop_diagram"},
        expected_criterion_ids=["S1", "M1", "M2", "M3", "M4", "M6"],
    ),
    "paradigm-suspension": ModeSpec(
        name="paradigm-suspension",
        structural=check_no_visual_structural("paradigm-suspension"),
        composite=_no_visual_composite,
        canonical_queries=CANONICAL_QUERIES["paradigm-suspension"],
        expected_envelope_types=set(),  # no envelope expected
        expected_criterion_ids=["S1", "S3", "M1", "M2", "M4"],
    ),
    # project-mode and structured-output are dispatch / passthrough specs;
    # we do not register ModeSpec entries for Tier A (they're covered by
    # the always-on file-structure tests only).
}


# ---------------------------------------------------------------------------
# Run-per-query data structure + aggregation
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    query: str
    raw_response: str
    envelope: dict | None
    structural: list[CriterionResult] = field(default_factory=list)
    composite: list[CriterionResult] = field(default_factory=list)
    adversarial_blocks: int = 0
    # Phase 6 — capture block content, not just count, so DUU-tornado-style
    # failures can be diagnosed without a separate instrumented re-run.
    adversarial_block_detail: list[dict] = field(default_factory=list)
    # Phase 6 cascade mode — preserved when ``run_cascade_tier_a``
    # scores the reviser's REVISED DRAFT so the sweep output can report
    # analyst-vs-cascade differences.
    cascade_stage: str = "analyst"  # "analyst" | "cascade-revised"
    cascade_analyst_response: str = ""
    cascade_evaluator_response: str = ""
    cascade_revised_draft: str = ""
    envelope_retry_used: bool = False
    # Phase 7 — Tier C end-to-end pipeline fields. Populated by
    # ``run_tier_c_pipeline`` which chains the verifier (Gear 3) or
    # verifier → consolidator → final verifier (Gear 4) onto the
    # cascade-aware analyst → evaluator → reviser flow.
    tier_c_verdict: str = ""           # VERIFIED / VERIFIED_WITH_CORRECTIONS / VERIFICATION_FAILED / UNKNOWN
    tier_c_verifier_response: str = ""
    tier_c_consolidator_response: str = ""
    tier_c_final_verifier_response: str = ""
    tier_c_gear: int = 0               # 3 or 4 (0 = not a Tier C run)
    error: str = ""


def _aggregate(results: list[RunResult]) -> dict:
    total = len(results)
    if total == 0:
        return {"total_runs": 0, "overall_pass_rate": 0.0,
                "structural_pass_rate": 0.0,
                "composite_pass_rate": None,
                "per_criterion_pass_rate": {}, "runs": []}

    def pct(bools: list[bool]) -> float:
        return (sum(1 for b in bools if b) / len(bools)) if bools else 0.0

    # WP-4.3 — No-visual and envelope-optional modes pass when
    # ``envelope is None`` but ``S1`` is True. The bool(r.envelope) gate
    # from the Phase-1 harness rejected these runs as structural
    # failures. Drop it: the structural criteria list now fully encodes
    # whether envelope presence/absence is legal for this mode.
    structural_full = [
        all(c.passed for c in r.structural) and bool(r.structural)
        for r in results
    ]
    composite_full = [
        all(c.passed for c in r.composite)
        for r in results if r.composite
    ]
    overall = [
        all(c.passed for c in r.structural)
        and bool(r.structural)
        and all(c.passed for c in r.composite)
        and r.adversarial_blocks == 0
        for r in results
    ]
    per_criterion: dict[str, list[bool]] = {}
    for r in results:
        for c in r.structural + r.composite:
            per_criterion.setdefault(c.id, []).append(c.passed)

    # Phase 7 — Tier C verdict distribution across the sweep.
    verdict_counts: dict[str, int] = {}
    tier_c_runs_seen = 0
    for r in results:
        if r.tier_c_verdict:
            tier_c_runs_seen += 1
            verdict_counts[r.tier_c_verdict] = \
                verdict_counts.get(r.tier_c_verdict, 0) + 1

    out = {
        "total_runs": total,
        "overall_pass_rate": pct(overall),
        "structural_pass_rate": pct(structural_full),
        "composite_pass_rate": pct(composite_full) if composite_full else None,
        "per_criterion_pass_rate":
            {k: pct(v) for k, v in sorted(per_criterion.items())},
        "runs": [
            {
                "query": r.query[:100],
                "has_envelope": r.envelope is not None,
                "error": r.error,
                "structural":
                    [(c.id, c.passed, c.detail) for c in r.structural],
                "composite":
                    [(c.id, c.passed, c.detail) for c in r.composite],
                "adversarial_blocks": r.adversarial_blocks,
                "adversarial_block_detail": r.adversarial_block_detail,
                "cascade_stage": r.cascade_stage,
                "envelope_retry_used": r.envelope_retry_used,
                "response_excerpt": (r.raw_response or "")[:400],
                **(
                    {
                        "cascade_analyst_excerpt":
                            (r.cascade_analyst_response or "")[:400],
                        "cascade_evaluator_excerpt":
                            (r.cascade_evaluator_response or "")[:400],
                        "cascade_revised_draft_excerpt":
                            (r.cascade_revised_draft or "")[:400],
                    }
                    if r.cascade_stage == "cascade-revised" else {}
                ),
                **(
                    {
                        "tier_c_verdict": r.tier_c_verdict,
                        "tier_c_gear": r.tier_c_gear,
                        "tier_c_verifier_excerpt":
                            (r.tier_c_verifier_response or "")[:400],
                        "tier_c_consolidator_excerpt":
                            (r.tier_c_consolidator_response or "")[:400],
                        "tier_c_final_verifier_excerpt":
                            (r.tier_c_final_verifier_response or "")[:400],
                    }
                    if r.tier_c_verdict else {}
                ),
            }
            for r in results
        ],
    }
    if tier_c_runs_seen:
        out["tier_c_verdict_distribution"] = verdict_counts
        out["tier_c_verified_rate"] = (
            (verdict_counts.get("VERIFIED", 0)
             + verdict_counts.get("VERIFIED_WITH_CORRECTIONS", 0))
            / tier_c_runs_seen
        )
    return out


# ---------------------------------------------------------------------------
# Model callers
# ---------------------------------------------------------------------------

def _get_gemini_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        return key
    try:
        import keyring
        return keyring.get_password("ora", "gemini-api-key") or ""
    except Exception:
        return ""


def _get_anthropic_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    try:
        import keyring
        return keyring.get_password("ora", "anthropic-api-key") or ""
    except Exception:
        return ""


# WP-4.3 — default per-call timeout (seconds). ``ORA_TIER_A_TIMEOUT``
# env var overrides; CLI --timeout flag overrides both.
_DEFAULT_CALL_TIMEOUT_S = float(os.environ.get("ORA_TIER_A_TIMEOUT", "60"))


def _estimate_tokens(text: str) -> int:
    """Rough token estimate — char-count / 4 is a long-standing ballpark
    for Latin-script English prose. Good enough for 'is this prompt
    dangerously large' telemetry; not good enough to pick batch sizes."""
    return max(1, len(text) // 4)


def _call_with_timeout(fn, timeout_s: float, *args, **kwargs) -> str:
    """Run ``fn(*args, **kwargs)`` in a worker thread and raise
    ``TimeoutError`` if it doesn't return inside ``timeout_s`` seconds.

    Prior versions of this harness called the Gemini / Anthropic
    clients directly and inherited their default (effectively
    unbounded) timeouts. Two Phase-2-3 live runs hung > 10 min on
    Gemini; catching that as a specific TimeoutError here — instead of
    a stuck thread — lets ``run_tier_a`` keep going.
    """
    import concurrent.futures as _cf
    with _cf.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn, *args, **kwargs)
        try:
            return fut.result(timeout=timeout_s)
        except _cf.TimeoutError as te:
            # Best-effort cancel — API clients don't interrupt cleanly,
            # but future.result stops waiting so the harness proceeds.
            fut.cancel()
            raise TimeoutError(
                f"model call exceeded {timeout_s:.1f}s") from te


def _call_gemini(system_prompt: str, user_prompt: str,
                 model_id: str = "models/gemini-2.5-flash",
                 timeout_s: float | None = None) -> str:
    from google import genai
    client = genai.Client(api_key=_get_gemini_key())
    t = timeout_s if timeout_s is not None else _DEFAULT_CALL_TIMEOUT_S

    def _invoke() -> str:
        resp = client.models.generate_content(
            model=model_id,
            contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
            config={"system_instruction": system_prompt},
        )
        return resp.text or ""

    return _call_with_timeout(_invoke, t)


def _call_claude(system_prompt: str, user_prompt: str,
                 model_id: str = "claude-haiku-4-5-20251001",
                 timeout_s: float | None = None) -> str:
    import anthropic
    t = timeout_s if timeout_s is not None else _DEFAULT_CALL_TIMEOUT_S
    client = anthropic.Anthropic(api_key=_get_anthropic_key(), timeout=t)

    def _invoke() -> str:
        resp = client.messages.create(
            model=model_id,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return resp.content[0].text

    return _call_with_timeout(_invoke, t)


def _call_model(system_prompt: str, user_prompt: str, model: str,
                timeout_s: float | None = None) -> str:
    if model == "gemini":
        return _call_gemini(system_prompt, user_prompt, timeout_s=timeout_s)
    if model == "claude":
        return _call_claude(system_prompt, user_prompt, timeout_s=timeout_s)
    raise ValueError(f"unknown model: {model}")


# ---------------------------------------------------------------------------
# Main Tier A entry point
# ---------------------------------------------------------------------------

# WP-4.3 — modes where envelope absence is a valid outcome. Imported
# from the shared success-criteria module so the two definitions stay
# in lockstep.
from mode_success_criteria import (  # noqa: E402
    NO_VISUAL_MODES as _NO_VISUAL_MODES,
    OPTIONAL_ENVELOPE_MODES as _OPTIONAL_ENVELOPE_MODES,
)


def run_tier_a(
    mode_name: str,
    queries: list[str] | None = None,
    runs_per_query: int = 3,
    model: str = "gemini",
    delay_seconds: float = 1.0,
    timeout_s: float | None = None,
    verbose: bool = False,
    envelope_retry: bool = False,
) -> dict:
    """Analyst-only Tier A sweep. Phase 6 additions: adversarial block
    detail capture, and an opt-in ``envelope_retry`` flag that reruns
    once with an EMISSION REMINDER suffix when the first call doesn't
    emit an ``ora-visual`` fence (eliminates the attention-tail
    truncation class of S1 failures per Phase 5 Handoff §8.2).
    """
    if mode_name not in MODE_SPECS:
        raise ValueError(
            f"No ModeSpec for {mode_name!r}. "
            f"Known: {sorted(MODE_SPECS)}"
        )
    spec = MODE_SPECS[mode_name]
    queries = queries or spec.canonical_queries
    emit_last = bool(os.environ.get("ORA_TIER_A_EMIT_LAST"))
    system_prompt = build_simulated_system_prompt(mode_name,
                                                   emit_last=emit_last)
    run_results: list[RunResult] = []

    # WP-4.3 — prompt-length instrumentation. Print once per run so the
    # operator can correlate latency / timeouts with prompt size.
    sys_chars = len(system_prompt)
    sys_tokens = _estimate_tokens(system_prompt)
    print(
        f"[tier-a] mode={mode_name} model={model} "
        f"system_prompt_chars={sys_chars} est_tokens≈{sys_tokens} "
        f"timeout={timeout_s or _DEFAULT_CALL_TIMEOUT_S:.0f}s",
        flush=True,
    )

    is_no_visual = mode_name in _NO_VISUAL_MODES
    is_envelope_optional = mode_name in _OPTIONAL_ENVELOPE_MODES

    for q_idx, q in enumerate(queries):
        for run_i in range(runs_per_query):
            if q_idx + run_i > 0:
                time.sleep(delay_seconds)

            call_start = time.monotonic()
            try:
                reply = _call_model(system_prompt, q, model=model,
                                    timeout_s=timeout_s)
            except TimeoutError as te:
                dur = time.monotonic() - call_start
                print(f"[tier-a] TIMEOUT @{dur:.1f}s mode={mode_name} "
                      f"q='{q[:60]}…'", flush=True)
                run_results.append(RunResult(
                    query=q, raw_response="", envelope=None,
                    structural=[CriterionResult(
                        id="S1", passed=False,
                        detail=f"timeout: {te}")],
                    error=str(te),
                ))
                continue
            except Exception as e:
                dur = time.monotonic() - call_start
                print(f"[tier-a] ERROR @{dur:.1f}s mode={mode_name}: "
                      f"{type(e).__name__}: {e}", flush=True)
                run_results.append(RunResult(
                    query=q, raw_response="", envelope=None,
                    structural=[CriterionResult(
                        id="S1", passed=False, detail=f"call_error: {e}")],
                    error=str(e),
                ))
                continue

            dur = time.monotonic() - call_start
            if verbose:
                print(f"[tier-a] ok @{dur:.1f}s mode={mode_name} "
                      f"reply_chars={len(reply)}", flush=True)

            envelopes = extract_envelopes(reply)
            retry_used = False

            # Phase 6 — retry-on-S1 (opt-in). When the analyst doesn't
            # emit a fence and the mode requires one, rerun once with an
            # explicit EMISSION REMINDER appended to the user prompt.
            if (envelope_retry and not envelopes and not is_no_visual
                    and not is_envelope_optional):
                retry_user = q + EMISSION_REMINDER_SUFFIX
                try:
                    retry_reply = _call_model(system_prompt, retry_user,
                                              model=model,
                                              timeout_s=timeout_s)
                    retry_envs = extract_envelopes(retry_reply)
                    if retry_envs:
                        reply = retry_reply
                        envelopes = retry_envs
                        retry_used = True
                        if verbose:
                            print(f"[tier-a] envelope-retry succeeded "
                                  f"mode={mode_name}", flush=True)
                except Exception as e:
                    if verbose:
                        print(f"[tier-a] envelope-retry failed "
                              f"mode={mode_name}: {type(e).__name__}: {e}",
                              flush=True)

            # WP-4.3 — No-visual modes (steelman-construction,
            # paradigm-suspension) pass when NO envelope is extracted.
            # If an envelope slips through, that is itself an S1 fail.
            if is_no_visual:
                if not envelopes:
                    run_results.append(RunResult(
                        query=q, raw_response=reply, envelope=None,
                        structural=[CriterionResult(
                            id="S1", passed=True,
                            detail="no-visual mode: absence is pass")],
                        composite=[],
                    ))
                else:
                    run_results.append(RunResult(
                        query=q, raw_response=reply, envelope=None,
                        structural=[CriterionResult(
                            id="S1", passed=False,
                            detail="no-visual mode: envelope present")],
                    ))
                continue

            # WP-4.3 — Envelope-optional modes (deep-clarification,
            # passion-exploration): absence is pass; presence triggers
            # the usual structural / composite pipeline.
            if not envelopes:
                if is_envelope_optional:
                    run_results.append(RunResult(
                        query=q, raw_response=reply, envelope=None,
                        structural=[CriterionResult(
                            id="S1", passed=True,
                            detail="envelope optional: absence ok")],
                        composite=[],
                    ))
                else:
                    run_results.append(RunResult(
                        query=q, raw_response=reply, envelope=None,
                        structural=[CriterionResult(
                            id="S1", passed=False,
                            detail="no envelope in reply")],
                    ))
                continue

            first = envelopes[0]
            if "__parse_error" in first:
                run_results.append(RunResult(
                    query=q, raw_response=reply, envelope=None,
                    structural=[CriterionResult(
                        id="S1", passed=False,
                        detail=f"parse_error: {first['error']}")],
                ))
                continue

            structural = ([CriterionResult(id="S1", passed=True, detail="")]
                          + spec.structural(first))
            composite = spec.composite(reply, first)
            # Adversarial review — the per-mode structural hook is now
            # redundant with the harness dispatch above, so we only count
            # T-rule / LLM-prior-inversion blocks here (the mode-criterion
            # findings would otherwise double-count).
            t_rule_only_review = review_envelope(
                {k: v for k, v in first.items()}, None  # no mode → skip mode checker
            )
            run_results.append(RunResult(
                query=q, raw_response=reply, envelope=first,
                structural=structural, composite=composite,
                adversarial_blocks=len(t_rule_only_review.blocks),
                adversarial_block_detail=[
                    f.as_dict() for f in t_rule_only_review.blocks
                ],
                envelope_retry_used=retry_used,
            ))

    return _aggregate(run_results)


# ---------------------------------------------------------------------------
# Phase 6 — cascade-aware Tier A harness
# ---------------------------------------------------------------------------

def run_cascade_tier_a(
    mode_name: str,
    queries: list[str] | None = None,
    runs_per_query: int = 3,
    model: str = "gemini",
    delay_seconds: float = 1.0,
    timeout_s: float | None = None,
    verbose: bool = False,
    envelope_retry: bool = False,
) -> dict:
    """Cascade-aware Tier A — chains analyst → evaluator → reviser and
    scores the reviser's REVISED DRAFT against the same structural +
    composite checkers ``run_tier_a`` applies to analyst-only output.

    This is the harness Phase 5's cascade architecture is actually
    measured by: the analyst-only ``run_tier_a`` reports the first draft
    quality, but the production pipeline delivers the reviser's revised
    output. Per Phase 5 Handoff §8.1 the cascade's value is measured by
    reusing existing checkers on the revised draft — any "fixed during
    revision" signalling is out-of-scope; only the final output quality
    counts.

    Produces the same aggregate shape as ``run_tier_a`` with the
    ``cascade_stage="cascade-revised"`` marker on every run so sweep
    consumers can tell the two harnesses apart.

    No-visual modes and envelope-optional modes pass through the same
    absence-is-pass logic as the analyst-only harness; their revised
    drafts are scored the same way because the criteria are identical.
    """
    if mode_name not in MODE_SPECS:
        raise ValueError(
            f"No ModeSpec for {mode_name!r}. "
            f"Known: {sorted(MODE_SPECS)}"
        )
    spec = MODE_SPECS[mode_name]
    queries = queries or spec.canonical_queries

    # Build the three cascade prompts once — they're mode-level invariants.
    analyst_prompt = _build_cascade_prompt(mode_name, step="analyst")
    evaluator_prompt = _build_cascade_prompt(mode_name, step="evaluator")
    reviser_prompt = _build_cascade_prompt(mode_name, step="reviser")

    run_results: list[RunResult] = []
    sys_chars = (len(analyst_prompt)
                 + len(evaluator_prompt)
                 + len(reviser_prompt))
    sys_tokens = _estimate_tokens(
        analyst_prompt + evaluator_prompt + reviser_prompt
    )
    print(
        f"[cascade-tier-a] mode={mode_name} model={model} "
        f"total_prompt_chars={sys_chars} est_tokens≈{sys_tokens} "
        f"timeout={timeout_s or _DEFAULT_CALL_TIMEOUT_S:.0f}s "
        f"envelope_retry={envelope_retry}",
        flush=True,
    )

    is_no_visual = mode_name in _NO_VISUAL_MODES
    is_envelope_optional = mode_name in _OPTIONAL_ENVELOPE_MODES

    for q_idx, q in enumerate(queries):
        for run_i in range(runs_per_query):
            if q_idx + run_i > 0:
                time.sleep(delay_seconds)

            t0 = time.monotonic()
            # --- 1. Analyst ---
            try:
                analyst_response = _call_model(
                    analyst_prompt, q, model=model, timeout_s=timeout_s
                )
            except (TimeoutError, Exception) as e:  # noqa: BLE001
                dur = time.monotonic() - t0
                print(f"[cascade-tier-a] analyst FAIL @{dur:.1f}s "
                      f"mode={mode_name}: {type(e).__name__}: {e}",
                      flush=True)
                run_results.append(RunResult(
                    query=q, raw_response="", envelope=None,
                    structural=[CriterionResult(
                        id="S1", passed=False,
                        detail=f"analyst_call_error: {e}")],
                    error=f"analyst:{e}",
                    cascade_stage="cascade-revised",
                ))
                continue

            retry_used = False
            # Envelope retry is applied at the analyst stage — a better
            # analyst draft gives the cascade more to work with.
            if (envelope_retry
                    and not is_no_visual and not is_envelope_optional
                    and not extract_envelopes(analyst_response)):
                retry_user = q + EMISSION_REMINDER_SUFFIX
                try:
                    retry_resp = _call_model(
                        analyst_prompt, retry_user, model=model,
                        timeout_s=timeout_s,
                    )
                    if extract_envelopes(retry_resp):
                        analyst_response = retry_resp
                        retry_used = True
                        if verbose:
                            print(f"[cascade-tier-a] analyst envelope-retry "
                                  f"succeeded mode={mode_name}", flush=True)
                except Exception:
                    pass  # keep original analyst_response

            # --- 2. Evaluator ---
            try:
                evaluator_response = _call_model(
                    evaluator_prompt,
                    f"## ORIGINAL QUERY\n\n{q}\n\n"
                    f"## ANALYST OUTPUT\n\n{analyst_response}",
                    model=model, timeout_s=timeout_s,
                )
            except (TimeoutError, Exception) as e:  # noqa: BLE001
                dur = time.monotonic() - t0
                print(f"[cascade-tier-a] evaluator FAIL @{dur:.1f}s "
                      f"mode={mode_name}: {type(e).__name__}: {e}",
                      flush=True)
                run_results.append(RunResult(
                    query=q, raw_response=analyst_response, envelope=None,
                    structural=[CriterionResult(
                        id="S1", passed=False,
                        detail=f"evaluator_call_error: {e}")],
                    error=f"evaluator:{e}",
                    cascade_stage="cascade-revised",
                    cascade_analyst_response=analyst_response,
                    envelope_retry_used=retry_used,
                ))
                continue

            # --- 3. Reviser ---
            try:
                reviser_response = _call_model(
                    reviser_prompt,
                    f"## ORIGINAL QUERY\n\n{q}\n\n"
                    f"## YOUR ORIGINAL ANALYSIS\n\n{analyst_response}\n\n"
                    f"## EVALUATOR'S CRITIQUE\n\n{evaluator_response}\n\n"
                    "Revise your analysis per the universal reviser "
                    "output contract. Emit all seven mirror-contract "
                    "sections (ADDRESSED, NOT ADDRESSED, INCORPORATED, "
                    "DECLINED, REMAINING UNCERTAINTIES, REVISED DRAFT, "
                    "CHANGELOG) in order. The REVISED DRAFT section must "
                    "contain the full revised analysis — prose sections "
                    "per the mode's CONTENT CONTRACT followed by exactly "
                    "one fenced `ora-visual` block per its EMISSION "
                    "CONTRACT.",
                    model=model, timeout_s=timeout_s,
                )
            except (TimeoutError, Exception) as e:  # noqa: BLE001
                dur = time.monotonic() - t0
                print(f"[cascade-tier-a] reviser FAIL @{dur:.1f}s "
                      f"mode={mode_name}: {type(e).__name__}: {e}",
                      flush=True)
                run_results.append(RunResult(
                    query=q, raw_response=analyst_response, envelope=None,
                    structural=[CriterionResult(
                        id="S1", passed=False,
                        detail=f"reviser_call_error: {e}")],
                    error=f"reviser:{e}",
                    cascade_stage="cascade-revised",
                    cascade_analyst_response=analyst_response,
                    cascade_evaluator_response=evaluator_response,
                    envelope_retry_used=retry_used,
                ))
                continue

            dur = time.monotonic() - t0
            if verbose:
                print(f"[cascade-tier-a] ok @{dur:.1f}s mode={mode_name} "
                      f"reviser_chars={len(reviser_response)}", flush=True)

            # --- 4. Extract REVISED DRAFT and score it ---
            revised_draft = _extract_revised_draft(reviser_response)
            if not revised_draft:
                # Reviser didn't emit the mirror contract's REVISED DRAFT
                # header. Treat as a cascade failure equivalent to
                # envelope absence — the reviser's output structure broke.
                run_results.append(RunResult(
                    query=q, raw_response=reviser_response, envelope=None,
                    structural=[CriterionResult(
                        id="S1", passed=False,
                        detail="reviser output missing '## REVISED DRAFT' "
                               "header (mirror-contract violation)")],
                    cascade_stage="cascade-revised",
                    cascade_analyst_response=analyst_response,
                    cascade_evaluator_response=evaluator_response,
                    cascade_revised_draft="",
                    envelope_retry_used=retry_used,
                ))
                continue

            envelopes = extract_envelopes(revised_draft)

            if is_no_visual:
                if not envelopes:
                    run_results.append(RunResult(
                        query=q, raw_response=reviser_response, envelope=None,
                        structural=[CriterionResult(
                            id="S1", passed=True,
                            detail="no-visual mode: absence is pass")],
                        composite=[],
                        cascade_stage="cascade-revised",
                        cascade_analyst_response=analyst_response,
                        cascade_evaluator_response=evaluator_response,
                        cascade_revised_draft=revised_draft,
                        envelope_retry_used=retry_used,
                    ))
                else:
                    run_results.append(RunResult(
                        query=q, raw_response=reviser_response, envelope=None,
                        structural=[CriterionResult(
                            id="S1", passed=False,
                            detail="no-visual mode: envelope present in "
                                   "revised draft")],
                        cascade_stage="cascade-revised",
                        cascade_analyst_response=analyst_response,
                        cascade_evaluator_response=evaluator_response,
                        cascade_revised_draft=revised_draft,
                        envelope_retry_used=retry_used,
                    ))
                continue

            if not envelopes:
                if is_envelope_optional:
                    run_results.append(RunResult(
                        query=q, raw_response=reviser_response, envelope=None,
                        structural=[CriterionResult(
                            id="S1", passed=True,
                            detail="envelope optional: absence ok")],
                        composite=[],
                        cascade_stage="cascade-revised",
                        cascade_analyst_response=analyst_response,
                        cascade_evaluator_response=evaluator_response,
                        cascade_revised_draft=revised_draft,
                        envelope_retry_used=retry_used,
                    ))
                else:
                    run_results.append(RunResult(
                        query=q, raw_response=reviser_response, envelope=None,
                        structural=[CriterionResult(
                            id="S1", passed=False,
                            detail="no envelope in revised draft")],
                        cascade_stage="cascade-revised",
                        cascade_analyst_response=analyst_response,
                        cascade_evaluator_response=evaluator_response,
                        cascade_revised_draft=revised_draft,
                        envelope_retry_used=retry_used,
                    ))
                continue

            first = envelopes[0]
            if "__parse_error" in first:
                run_results.append(RunResult(
                    query=q, raw_response=reviser_response, envelope=None,
                    structural=[CriterionResult(
                        id="S1", passed=False,
                        detail=f"parse_error: {first['error']}")],
                    cascade_stage="cascade-revised",
                    cascade_analyst_response=analyst_response,
                    cascade_evaluator_response=evaluator_response,
                    cascade_revised_draft=revised_draft,
                    envelope_retry_used=retry_used,
                ))
                continue

            structural = ([CriterionResult(id="S1", passed=True, detail="")]
                          + spec.structural(first))
            composite = spec.composite(revised_draft, first)
            t_rule_only_review = review_envelope(
                {k: v for k, v in first.items()}, None
            )
            run_results.append(RunResult(
                query=q, raw_response=reviser_response, envelope=first,
                structural=structural, composite=composite,
                adversarial_blocks=len(t_rule_only_review.blocks),
                adversarial_block_detail=[
                    f.as_dict() for f in t_rule_only_review.blocks
                ],
                cascade_stage="cascade-revised",
                cascade_analyst_response=analyst_response,
                cascade_evaluator_response=evaluator_response,
                cascade_revised_draft=revised_draft,
                envelope_retry_used=retry_used,
            ))

    return _aggregate(run_results)


# ---------------------------------------------------------------------------
# Phase 7 — Tier C end-to-end pipeline harness
# ---------------------------------------------------------------------------

_GEAR_HEADING_RE = re.compile(
    r"^##\s*DEFAULT\s*GEAR\s*\n+([\s\S]*?)(?=\n##\s|\Z)",
    re.MULTILINE | re.IGNORECASE,
)


def _extract_default_gear(mode_text: str) -> int:
    """Extract the integer from the mode file's ``## DEFAULT GEAR``
    section. Falls back to 3 when not parseable (Gear 3 is the
    Phase-5 canonical analytical pipeline; harmless default)."""
    m = _GEAR_HEADING_RE.search(mode_text)
    if not m:
        return 3
    body = m.group(1)
    # Look for a standalone "Gear <n>." or "<n>" pattern.
    tok = re.search(r"\b(?:Gear\s*)?([2-4])\b", body, re.IGNORECASE)
    if tok:
        try:
            return int(tok.group(1))
        except ValueError:
            pass
    return 3


def _classify_verdict(text: str) -> str:
    """Map verifier output to one of the four verdicts in the universal
    verifier contract (Phase 5 §5 / Phase 6 ``_verifier_passed``).

    Returns one of:
    - ``VERIFIED`` — pass without corrections; "VERIFIED" present without
      the "VERIFIED WITH CORRECTIONS" or "VERIFICATION FAILED" markers.
    - ``VERIFIED_WITH_CORRECTIONS`` — pass with corrections applied
      (corrections included in the verifier's output).
    - ``VERIFICATION_FAILED`` — explicit failure.
    - ``UNKNOWN`` — neither marker found (contract violation or model
      went off-contract).
    """
    if not text:
        return "UNKNOWN"
    if "VERIFICATION FAILED" in text:
        return "VERIFICATION_FAILED"
    if "VERIFIED WITH CORRECTIONS" in text:
        return "VERIFIED_WITH_CORRECTIONS"
    if "VERIFIED" in text:
        return "VERIFIED"
    return "UNKNOWN"


def run_tier_c_pipeline(
    mode_name: str,
    queries: list[str] | None = None,
    runs_per_query: int = 3,
    model: str = "gemini",
    delay_seconds: float = 1.0,
    timeout_s: float | None = None,
    verbose: bool = False,
    envelope_retry: bool = False,
) -> dict:
    """Tier C — end-to-end pipeline harness (Phase 7).

    Extends the cascade-aware harness by running the verifier (Gear 3)
    or the verifier → consolidator → final verifier (Gear 4) steps.
    Tracks the verifier's verdict — ``VERIFIED`` /
    ``VERIFIED_WITH_CORRECTIONS`` / ``VERIFICATION_FAILED`` / ``UNKNOWN``
    per the universal verifier contract in ``f-verify.md``.

    Aims:

    1. Validate that the refactored ``run_gear3`` / ``run_gear4``
       contract (universal verifier verdicts replacing the pre-Phase-5
       ``VERDICT: PASS/FAIL``) reaches the model and produces the
       expected verdict distribution.
    2. Measure how often a structurally-passing cascade-revised draft
       is ALSO marked VERIFIED — cross-signal validation.

    Gear 4 modes (per the mode file's ``## DEFAULT GEAR`` section) run
    two additional steps after the verifier: a consolidator (combining
    the revised draft with a second perspective — here the analyst's
    original output stands in as the "second stream" since we don't
    run two parallel analysts in the harness) and a final verifier
    over the consolidated output. The final verifier's verdict
    supersedes the initial verifier's for verdict-distribution
    accounting.
    """
    if mode_name not in MODE_SPECS:
        raise ValueError(
            f"No ModeSpec for {mode_name!r}. "
            f"Known: {sorted(MODE_SPECS)}"
        )
    spec = MODE_SPECS[mode_name]
    queries = queries or spec.canonical_queries

    mode_text = (MODES_DIR / f"{mode_name}.md").read_text()
    gear = _extract_default_gear(mode_text)

    analyst_prompt = _build_cascade_prompt(mode_name, step="analyst")
    evaluator_prompt = _build_cascade_prompt(mode_name, step="evaluator")
    reviser_prompt = _build_cascade_prompt(mode_name, step="reviser")
    verifier_prompt = _build_cascade_prompt(mode_name, step="verifier")
    consolidator_prompt = (
        _build_cascade_prompt(mode_name, step="consolidator")
        if gear == 4 else ""
    )

    run_results: list[RunResult] = []
    is_no_visual = mode_name in _NO_VISUAL_MODES
    is_envelope_optional = mode_name in _OPTIONAL_ENVELOPE_MODES
    print(
        f"[tier-c] mode={mode_name} gear={gear} model={model} "
        f"runs={runs_per_query} queries={len(queries)} "
        f"timeout={timeout_s or _DEFAULT_CALL_TIMEOUT_S:.0f}s",
        flush=True,
    )

    def _record_fail(q: str, stage: str, analyst: str,
                     evaluator: str, reviser: str,
                     verifier: str, err: str) -> RunResult:
        return RunResult(
            query=q, raw_response=reviser or analyst, envelope=None,
            structural=[CriterionResult(
                id="S1", passed=False,
                detail=f"tier_c_{stage}_error: {err}")],
            error=f"tier_c_{stage}:{err}",
            cascade_stage="cascade-revised",
            cascade_analyst_response=analyst,
            cascade_evaluator_response=evaluator,
            cascade_revised_draft="",
            tier_c_verdict="UNKNOWN",
            tier_c_verifier_response=verifier,
            tier_c_gear=gear,
        )

    for q_idx, q in enumerate(queries):
        for run_i in range(runs_per_query):
            if q_idx + run_i > 0:
                time.sleep(delay_seconds)

            t0 = time.monotonic()
            # --- 1. Analyst ---
            try:
                analyst_response = _call_model(
                    analyst_prompt, q, model=model, timeout_s=timeout_s
                )
            except Exception as e:  # noqa: BLE001
                run_results.append(_record_fail(
                    q, "analyst", "", "", "", "", str(e)))
                continue

            retry_used = False
            if (envelope_retry
                    and not is_no_visual and not is_envelope_optional
                    and not extract_envelopes(analyst_response)):
                try:
                    retry_resp = _call_model(
                        analyst_prompt, q + EMISSION_REMINDER_SUFFIX,
                        model=model, timeout_s=timeout_s,
                    )
                    if extract_envelopes(retry_resp):
                        analyst_response = retry_resp
                        retry_used = True
                except Exception:
                    pass

            # --- 2. Evaluator ---
            try:
                evaluator_response = _call_model(
                    evaluator_prompt,
                    f"## ORIGINAL QUERY\n\n{q}\n\n"
                    f"## ANALYST OUTPUT\n\n{analyst_response}",
                    model=model, timeout_s=timeout_s,
                )
            except Exception as e:  # noqa: BLE001
                run_results.append(_record_fail(
                    q, "evaluator", analyst_response, "", "", "", str(e)))
                continue

            # --- 3. Reviser ---
            try:
                reviser_response = _call_model(
                    reviser_prompt,
                    f"## ORIGINAL QUERY\n\n{q}\n\n"
                    f"## YOUR ORIGINAL ANALYSIS\n\n{analyst_response}\n\n"
                    f"## EVALUATOR'S CRITIQUE\n\n{evaluator_response}\n\n"
                    "Revise your analysis per the universal reviser "
                    "output contract. Emit all seven mirror-contract "
                    "sections (ADDRESSED, NOT ADDRESSED, INCORPORATED, "
                    "DECLINED, REMAINING UNCERTAINTIES, REVISED DRAFT, "
                    "CHANGELOG) in order. The REVISED DRAFT section must "
                    "contain the full revised analysis — prose per "
                    "CONTENT CONTRACT and exactly one fenced `ora-visual` "
                    "block per EMISSION CONTRACT (where applicable).",
                    model=model, timeout_s=timeout_s,
                )
            except Exception as e:  # noqa: BLE001
                run_results.append(_record_fail(
                    q, "reviser", analyst_response, evaluator_response,
                    "", "", str(e)))
                continue

            revised_draft = _extract_revised_draft(reviser_response)

            # --- 4. Verifier ---
            try:
                verifier_response = _call_model(
                    verifier_prompt,
                    f"## ORIGINAL QUERY\n\n{q}\n\n"
                    f"## ORIGINAL ANALYSIS\n\n{analyst_response}\n\n"
                    f"## EVALUATOR'S MANDATORY FIXES\n\n{evaluator_response}\n\n"
                    f"## REVISED ANALYSIS (reviser output)\n\n{reviser_response}\n\n"
                    "Run the universal V1-V8 checklist plus mode-specific "
                    "verifier checks. Conclude with VERIFIED / VERIFIED WITH "
                    "CORRECTIONS / VERIFICATION FAILED.",
                    model=model, timeout_s=timeout_s,
                )
            except Exception as e:  # noqa: BLE001
                run_results.append(_record_fail(
                    q, "verifier", analyst_response, evaluator_response,
                    reviser_response, "", str(e)))
                continue

            verdict = _classify_verdict(verifier_response)
            consolidator_response = ""
            final_verifier_response = ""

            # --- 5. Gear 4 extras: consolidator + final verifier ---
            if gear == 4 and verdict != "VERIFICATION_FAILED":
                try:
                    # In the harness we don't run two parallel analysts;
                    # pass the analyst's original as the Depth stream and
                    # the revised draft as the Breadth stream for the
                    # consolidator to reconcile. This is a faithful
                    # approximation of what Gear 4's consolidator sees
                    # once each stream has been verified.
                    consolidator_response = _call_model(
                        consolidator_prompt,
                        f"## ORIGINAL QUERY\n\n{q}\n\n"
                        f"## DEPTH STREAM (original analyst)\n\n"
                        f"{analyst_response}\n\n"
                        f"## BREADTH STREAM (revised draft)\n\n"
                        f"{revised_draft or reviser_response}\n\n"
                        "Consolidate per this mode's consolidator "
                        "guidance. Emit ## CONSOLIDATED and "
                        "## CONTINUITY PROMPT sections.",
                        model=model, timeout_s=timeout_s,
                    )
                    final_verifier_response = _call_model(
                        verifier_prompt,
                        f"## ORIGINAL QUERY\n\n{q}\n\n"
                        f"## CONSOLIDATED OUTPUT\n\n{consolidator_response}\n\n"
                        "Final verifier pass over the consolidated "
                        "output. Conclude with VERIFIED / VERIFIED "
                        "WITH CORRECTIONS / VERIFICATION FAILED.",
                        model=model, timeout_s=timeout_s,
                    )
                    verdict = _classify_verdict(final_verifier_response)
                except Exception as e:  # noqa: BLE001
                    # Consolidator / final-verifier failures leave the
                    # initial verifier's verdict intact; record the error.
                    if verbose:
                        print(f"[tier-c] gear4 extras failed "
                              f"mode={mode_name}: {e}", flush=True)

            dur = time.monotonic() - t0
            if verbose:
                print(f"[tier-c] ok @{dur:.1f}s mode={mode_name} "
                      f"verdict={verdict}", flush=True)

            # --- 6. Score the REVISED DRAFT structurally (same as
            # cascade-aware Tier A) so we can cross-reference structural
            # pass vs verifier verdict.
            if not revised_draft:
                run_results.append(RunResult(
                    query=q, raw_response=reviser_response, envelope=None,
                    structural=[CriterionResult(
                        id="S1", passed=False,
                        detail="reviser missing '## REVISED DRAFT' header")],
                    cascade_stage="cascade-revised",
                    cascade_analyst_response=analyst_response,
                    cascade_evaluator_response=evaluator_response,
                    cascade_revised_draft="",
                    envelope_retry_used=retry_used,
                    tier_c_verdict=verdict,
                    tier_c_verifier_response=verifier_response,
                    tier_c_consolidator_response=consolidator_response,
                    tier_c_final_verifier_response=final_verifier_response,
                    tier_c_gear=gear,
                ))
                continue

            envelopes = extract_envelopes(revised_draft)

            if is_no_visual:
                s1_pass = not envelopes
                run_results.append(RunResult(
                    query=q, raw_response=reviser_response, envelope=None,
                    structural=[CriterionResult(
                        id="S1", passed=s1_pass,
                        detail=("no-visual mode: absence is pass"
                                if s1_pass else
                                "no-visual mode: envelope present"))],
                    composite=[],
                    cascade_stage="cascade-revised",
                    cascade_analyst_response=analyst_response,
                    cascade_evaluator_response=evaluator_response,
                    cascade_revised_draft=revised_draft,
                    envelope_retry_used=retry_used,
                    tier_c_verdict=verdict,
                    tier_c_verifier_response=verifier_response,
                    tier_c_consolidator_response=consolidator_response,
                    tier_c_final_verifier_response=final_verifier_response,
                    tier_c_gear=gear,
                ))
                continue

            if not envelopes:
                s1_pass = is_envelope_optional
                run_results.append(RunResult(
                    query=q, raw_response=reviser_response, envelope=None,
                    structural=[CriterionResult(
                        id="S1", passed=s1_pass,
                        detail=("envelope optional: absence ok"
                                if s1_pass else
                                "no envelope in revised draft"))],
                    composite=[],
                    cascade_stage="cascade-revised",
                    cascade_analyst_response=analyst_response,
                    cascade_evaluator_response=evaluator_response,
                    cascade_revised_draft=revised_draft,
                    envelope_retry_used=retry_used,
                    tier_c_verdict=verdict,
                    tier_c_verifier_response=verifier_response,
                    tier_c_consolidator_response=consolidator_response,
                    tier_c_final_verifier_response=final_verifier_response,
                    tier_c_gear=gear,
                ))
                continue

            first = envelopes[0]
            if "__parse_error" in first:
                run_results.append(RunResult(
                    query=q, raw_response=reviser_response, envelope=None,
                    structural=[CriterionResult(
                        id="S1", passed=False,
                        detail=f"parse_error: {first['error']}")],
                    cascade_stage="cascade-revised",
                    cascade_analyst_response=analyst_response,
                    cascade_evaluator_response=evaluator_response,
                    cascade_revised_draft=revised_draft,
                    envelope_retry_used=retry_used,
                    tier_c_verdict=verdict,
                    tier_c_verifier_response=verifier_response,
                    tier_c_consolidator_response=consolidator_response,
                    tier_c_final_verifier_response=final_verifier_response,
                    tier_c_gear=gear,
                ))
                continue

            structural = ([CriterionResult(id="S1", passed=True, detail="")]
                          + spec.structural(first))
            composite = spec.composite(revised_draft, first)
            t_rule_only_review = review_envelope(
                {k: v for k, v in first.items()}, None
            )
            run_results.append(RunResult(
                query=q, raw_response=reviser_response, envelope=first,
                structural=structural, composite=composite,
                adversarial_blocks=len(t_rule_only_review.blocks),
                adversarial_block_detail=[
                    f.as_dict() for f in t_rule_only_review.blocks
                ],
                cascade_stage="cascade-revised",
                cascade_analyst_response=analyst_response,
                cascade_evaluator_response=evaluator_response,
                cascade_revised_draft=revised_draft,
                envelope_retry_used=retry_used,
                tier_c_verdict=verdict,
                tier_c_verifier_response=verifier_response,
                tier_c_consolidator_response=consolidator_response,
                tier_c_final_verifier_response=final_verifier_response,
                tier_c_gear=gear,
            ))

    return _aggregate(run_results)


# ---------------------------------------------------------------------------
# Always-on unit tests — one class per mode via a shared base
# ---------------------------------------------------------------------------

class _ModeFileTestBase(unittest.TestCase):
    """Base class for per-mode structural tests. Subclasses set MODE_NAME;
    discovery only picks up subclasses (this class name starts with _)."""

    MODE_NAME: str = ""

    @classmethod
    def setUpClass(cls) -> None:
        if not cls.MODE_NAME:
            raise unittest.SkipTest("base class")
        cls.text = (MODES_DIR / f"{cls.MODE_NAME}.md").read_text()
        cls.spec = MODE_SPECS[cls.MODE_NAME]

    def test_has_all_eleven_spec_sections(self) -> None:
        for h in REQUIRED_SECTIONS_11:
            self.assertIn(f"## {h}", self.text,
                          f"{self.MODE_NAME}: missing section {h}")

    def test_emission_contract_mentions_expected_types(self) -> None:
        ec = _extract_section(self.text, "EMISSION CONTRACT")
        # No-visual modes: EMISSION CONTRACT section must exist but its
        # content is a suppression rule, not a type list.
        if not self.spec.expected_envelope_types:
            self.assertTrue(
                len(ec) > 0,
                f"{self.MODE_NAME}: EMISSION CONTRACT section is empty"
            )
            self.assertTrue(
                "no" in ec.lower() and ("envelope" in ec.lower() or "ora-visual" in ec.lower()),
                f"{self.MODE_NAME}: no-visual mode should state suppression in EMISSION CONTRACT"
            )
            return
        self.assertIn("canvas_action", ec,
                      f"{self.MODE_NAME}: EMISSION CONTRACT missing canvas_action")
        self.assertIn("mode_context", ec,
                      f"{self.MODE_NAME}: EMISSION CONTRACT missing mode_context")
        for t in self.spec.expected_envelope_types:
            self.assertIn(f'"{t}"', ec,
                          f"{self.MODE_NAME}: EMISSION CONTRACT missing type {t}")

    def test_success_criteria_lists_tiers_and_ids(self) -> None:
        sc = _extract_section(self.text, "SUCCESS CRITERIA")
        # Structural and Semantic always expected.
        for tier in ("Structural", "Semantic"):
            self.assertIn(tier, sc,
                          f"{self.MODE_NAME}: SUCCESS CRITERIA missing {tier}")
        # Composite only expected when envelope is expected (there's
        # something to compare prose against). No-visual modes and
        # envelope-optional modes like deep-clarification may omit it.
        envelope_expected = bool(self.spec.expected_envelope_types)
        mode_is_optional_envelope = self.MODE_NAME in {
            "deep-clarification", "passion-exploration"
        }
        if envelope_expected and not mode_is_optional_envelope:
            self.assertIn("Composite", sc,
                          f"{self.MODE_NAME}: SUCCESS CRITERIA missing Composite")
        for cid in self.spec.expected_criterion_ids:
            self.assertIn(cid, sc,
                          f"{self.MODE_NAME}: SUCCESS CRITERIA missing {cid}")

    def test_canonical_envelope_example_is_valid(self) -> None:
        # No-visual modes (steelman-construction, paradigm-suspension) skip
        # this check — their EMISSION CONTRACT legitimately contains no
        # envelope to validate.
        if not self.spec.expected_envelope_types:
            return

        ec = _extract_section(self.text, "EMISSION CONTRACT")
        fence = re.search(r"```ora-visual\s*\n(.*?)\n```",
                          ec, re.DOTALL)
        self.assertIsNotNone(
            fence,
            f"{self.MODE_NAME}: EMISSION CONTRACT lacks canonical envelope",
        )
        env = json.loads(fence.group(1))
        v = validate_envelope(env)
        self.assertTrue(
            v.valid,
            f"{self.MODE_NAME}: canonical envelope fails schema: "
            f"{[e.as_dict() for e in v.errors]}",
        )
        structural = self.spec.structural(env)
        failed = [c for c in structural if not c.passed]
        self.assertEqual(
            [], failed,
            f"{self.MODE_NAME}: canonical envelope fails success criteria: "
            f"{[(c.id, c.detail) for c in failed]}",
        )

    def test_build_simulated_system_prompt_includes_rebuild_sections(self) -> None:
        prompt = build_simulated_system_prompt(self.MODE_NAME)
        for section in ("## EMISSION CONTRACT", "## SUCCESS CRITERIA",
                        "## CONTENT CONTRACT"):
            self.assertIn(section, prompt,
                          f"{self.MODE_NAME}: simulated prompt missing {section}")


class TestModeFileStructure_RCA(_ModeFileTestBase):
    MODE_NAME = "root-cause-analysis"


class TestModeFileStructure_SD(_ModeFileTestBase):
    MODE_NAME = "systems-dynamics"


class TestModeFileStructure_DUU(_ModeFileTestBase):
    MODE_NAME = "decision-under-uncertainty"


class TestModeFileStructure_CH(_ModeFileTestBase):
    MODE_NAME = "competing-hypotheses"


class TestModeFileStructure_TM(_ModeFileTestBase):
    MODE_NAME = "terrain-mapping"


class TestModeFileStructure_SYN(_ModeFileTestBase):
    MODE_NAME = "synthesis"


class TestModeFileStructure_PE(_ModeFileTestBase):
    MODE_NAME = "passion-exploration"


class TestModeFileStructure_RM(_ModeFileTestBase):
    MODE_NAME = "relationship-mapping"


class TestModeFileStructure_SP(_ModeFileTestBase):
    MODE_NAME = "scenario-planning"


class TestModeFileStructure_CM(_ModeFileTestBase):
    MODE_NAME = "constraint-mapping"


class TestModeFileStructure_BA(_ModeFileTestBase):
    MODE_NAME = "benefits-analysis"


class TestModeFileStructure_DA(_ModeFileTestBase):
    MODE_NAME = "dialectical-analysis"


class TestModeFileStructure_CB(_ModeFileTestBase):
    MODE_NAME = "cui-bono"


class TestModeFileStructure_CS(_ModeFileTestBase):
    MODE_NAME = "consequences-and-sequel"


class TestModeFileStructure_SI(_ModeFileTestBase):
    MODE_NAME = "strategic-interaction"


class TestModeFileStructure_Steelman(_ModeFileTestBase):
    MODE_NAME = "steelman-construction"


class TestModeFileStructure_DC(_ModeFileTestBase):
    MODE_NAME = "deep-clarification"


class TestModeFileStructure_PS(_ModeFileTestBase):
    MODE_NAME = "paradigm-suspension"


# Project Mode and Structured Output are dispatch / passthrough specs.
# They still have the 11-section structure but not a full MODE_SPECS entry.
# Validate the file structure directly.

class TestModeFileStructure_PM(unittest.TestCase):
    """Project Mode structural checks (dispatch spec)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = (MODES_DIR / "project-mode.md").read_text()

    def test_has_all_eleven_spec_sections(self) -> None:
        for h in REQUIRED_SECTIONS_11:
            self.assertIn(f"## {h}", self.text,
                          f"project-mode: missing section {h}")

    def test_emission_contract_describes_dispatch(self) -> None:
        ec = _extract_section(self.text, "EMISSION CONTRACT")
        self.assertIn("dispatch", ec.lower(),
                      "project-mode EMISSION CONTRACT should describe dispatch")


class TestModeFileStructure_SO(unittest.TestCase):
    """Structured Output structural checks (passthrough spec)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = (MODES_DIR / "structured-output.md").read_text()

    def test_has_all_eleven_spec_sections(self) -> None:
        for h in REQUIRED_SECTIONS_11:
            self.assertIn(f"## {h}", self.text,
                          f"structured-output: missing section {h}")

    def test_emission_contract_describes_passthrough(self) -> None:
        ec = _extract_section(self.text, "EMISSION CONTRACT")
        self.assertIn("passthrough", ec.lower(),
                      "structured-output EMISSION CONTRACT should describe passthrough")


# ---------------------------------------------------------------------------
# Phase 6 — always-on unit tests for the cascade helpers (no network)
# ---------------------------------------------------------------------------


class TestExtractRevisedDraft(unittest.TestCase):
    """``_extract_revised_draft`` pulls the revised-analysis body out of a
    reviser response shaped per the Phase 5 mirror contract."""

    MIRROR_CONTRACT = (
        "## ADDRESSED\n\n- S12 short_alt trimmed\n\n"
        "## NOT ADDRESSED\n\nNone.\n\n"
        "## INCORPORATED\n\n- Tufte suggestion #2\n\n"
        "## DECLINED\n\nNone.\n\n"
        "## REMAINING UNCERTAINTIES\n\nNone.\n\n"
        "## REVISED DRAFT\n\n"
        "# Root causes of deployment failures\n\n"
        "The presented problem is that deployments fail intermittently...\n"
        "```ora-visual\n{\"schema_version\": \"0.2\"}\n```\n\n"
        "## CHANGELOG\n\n- trimmed short_alt from 182 → 98 chars\n"
    )

    def test_happy_path_returns_revised_body_only(self) -> None:
        body = _extract_revised_draft(self.MIRROR_CONTRACT)
        self.assertIn("Root causes of deployment failures", body)
        self.assertIn("```ora-visual", body)
        self.assertNotIn("## CHANGELOG", body,
                         "extract must stop at CHANGELOG, not include it")
        self.assertNotIn("## ADDRESSED", body,
                         "extract must not include pre-REVISED-DRAFT sections")

    def test_missing_header_returns_empty_string(self) -> None:
        self.assertEqual(_extract_revised_draft("no mirror contract here"), "")
        self.assertEqual(
            _extract_revised_draft("## ADDRESSED\n\nNone.\n\n"
                                    "## CHANGELOG\n\nNone.\n"),
            "",
        )

    def test_extract_survives_missing_changelog(self) -> None:
        text = (
            "## REVISED DRAFT\n\n"
            "The revised analysis body.\n\n"
            "```ora-visual\n{\"schema_version\":\"0.2\"}\n```\n"
        )
        body = _extract_revised_draft(text)
        self.assertIn("revised analysis body", body)
        self.assertIn("ora-visual", body)

    def test_envelope_extractable_from_revised_draft(self) -> None:
        body = _extract_revised_draft(self.MIRROR_CONTRACT)
        envs = extract_envelopes(body)
        self.assertEqual(len(envs), 1)
        self.assertEqual(envs[0].get("schema_version"), "0.2")

    def test_extract_handles_h2_headings_inside_revised_body(self) -> None:
        """The revised analyst output can carry its own ``##`` headings
        (e.g. RCA's "Chosen framework" section); the extractor must NOT
        truncate at them — only at ``## CHANGELOG``."""
        text = (
            "## REVISED DRAFT\n\n"
            "## Presented problem\n\n"
            "Deployments fail intermittently in production.\n\n"
            "## Chosen framework and rationale\n\n"
            "6M fits because failures span process and infrastructure.\n\n"
            "```ora-visual\n{\"schema_version\":\"0.2\"}\n```\n\n"
            "## CHANGELOG\n\n- trimmed short_alt to 98 chars\n"
        )
        body = _extract_revised_draft(text)
        self.assertIn("Deployments fail intermittently", body)
        self.assertIn("6M fits because failures span", body)
        self.assertIn("ora-visual", body)
        self.assertNotIn("CHANGELOG", body)
        self.assertNotIn("trimmed short_alt", body)


class TestEmissionReminderSuffix(unittest.TestCase):
    """The reminder must be stable — the sweep analysis looks for it in
    the retry-history output and the iteration doc cites the exact
    phrasing."""

    def test_suffix_contains_required_markers(self) -> None:
        self.assertIn("EMISSION REMINDER", EMISSION_REMINDER_SUFFIX)
        self.assertIn("ora-visual", EMISSION_REMINDER_SUFFIX)
        self.assertIn("REQUIRED", EMISSION_REMINDER_SUFFIX)
        # Must be prefixable to a user prompt without swallowing trailing
        # punctuation of the original prompt.
        self.assertTrue(EMISSION_REMINDER_SUFFIX.startswith("\n\n"))


class TestRunResultCascadeFields(unittest.TestCase):
    """Phase 6 additions to ``RunResult`` must round-trip through
    ``_aggregate`` without breaking the pre-Phase-6 JSON shape."""

    def test_default_analyst_stage_marker(self) -> None:
        r = RunResult(query="q", raw_response="", envelope=None)
        self.assertEqual(r.cascade_stage, "analyst")
        self.assertEqual(r.adversarial_block_detail, [])
        self.assertFalse(r.envelope_retry_used)

    def test_aggregate_preserves_adversarial_detail(self) -> None:
        r = RunResult(
            query="q", raw_response="", envelope={"schema_version": "0.2"},
            structural=[CriterionResult(id="S1", passed=True, detail="")],
            composite=[],
            adversarial_blocks=2,
            adversarial_block_detail=[
                {"rule": "T5", "severity": "Critical",
                 "message": "axis missing", "path": ""},
                {"rule": "T1", "severity": "Critical",
                 "message": "lie factor high", "path": ""},
            ],
        )
        agg = _aggregate([r])
        self.assertEqual(agg["runs"][0]["adversarial_blocks"], 2)
        self.assertEqual(len(agg["runs"][0]["adversarial_block_detail"]), 2)
        self.assertEqual(agg["runs"][0]["adversarial_block_detail"][0]["rule"],
                         "T5")
        # Pre-Phase-6 keys still present.
        self.assertIn("structural", agg["runs"][0])
        self.assertIn("composite", agg["runs"][0])
        self.assertIn("response_excerpt", agg["runs"][0])

    def test_aggregate_marks_cascade_revised_runs(self) -> None:
        r = RunResult(
            query="q", raw_response="", envelope={"schema_version": "0.2"},
            structural=[CriterionResult(id="S1", passed=True, detail="")],
            composite=[],
            cascade_stage="cascade-revised",
            cascade_analyst_response="analyst output",
            cascade_evaluator_response="evaluator output",
            cascade_revised_draft="revised draft",
            envelope_retry_used=True,
        )
        agg = _aggregate([r])
        row = agg["runs"][0]
        self.assertEqual(row["cascade_stage"], "cascade-revised")
        self.assertTrue(row["envelope_retry_used"])
        self.assertEqual(row["cascade_analyst_excerpt"], "analyst output")
        self.assertEqual(row["cascade_revised_draft_excerpt"], "revised draft")


class TestBuildSimulatedSystemPromptEmitLast(unittest.TestCase):
    """Phase 6 Track A5 — ``build_simulated_system_prompt(emit_last=True)``
    reorders the analyst prompt so EMISSION CONTRACT sits after
    GUARD RAILS (recency-bias hypothesis for S1 failures)."""

    def test_default_ordering_places_emission_after_content_contract(self) -> None:
        prompt = build_simulated_system_prompt("root-cause-analysis")
        # Anchor on newline-bracketed section headings; Phase 7 reviser
        # guidance mentions `## EMISSION CONTRACT` in prose, so bare
        # substring matches return the prose reference, not the heading.
        idx_cc = prompt.index("\n## CONTENT CONTRACT\n")
        idx_ec = prompt.index("\n## EMISSION CONTRACT\n")
        idx_gr = prompt.index("\n## GUARD RAILS\n")
        self.assertLess(idx_cc, idx_ec)
        self.assertLess(idx_ec, idx_gr)

    def test_emit_last_places_emission_after_guard_rails(self) -> None:
        prompt = build_simulated_system_prompt("root-cause-analysis",
                                                emit_last=True)
        idx_ec = prompt.index("\n## EMISSION CONTRACT\n")
        idx_gr = prompt.index("\n## GUARD RAILS\n")
        self.assertLess(idx_gr, idx_ec,
                        "emit_last must move EMISSION CONTRACT after "
                        "GUARD RAILS")

    def test_emit_last_preserves_section_bodies(self) -> None:
        default = build_simulated_system_prompt("root-cause-analysis")
        reordered = build_simulated_system_prompt("root-cause-analysis",
                                                    emit_last=True)
        # Both prompts contain the same distinctive section bodies.
        for marker in ('"type": "fishbone"',
                       "Solution Announcement Trigger",
                       "Chain 1:", "S12"):
            self.assertIn(marker, default)
            self.assertIn(marker, reordered)


class TestBuildCascadePromptStepDispatch(unittest.TestCase):
    """``_build_cascade_prompt`` must delegate to
    ``build_system_prompt_for_gear(step=...)`` and append the correct
    F-* scaffolding per step. No network required — only uses local
    files."""

    def test_analyst_step_omits_framework(self) -> None:
        prompt = _build_cascade_prompt("root-cause-analysis", step="analyst")
        self.assertIn("MODE INSTRUCTIONS", prompt)
        self.assertNotIn("F-* UNIVERSAL SCAFFOLDING", prompt,
                         "analyst step should not attach an F-* file")

    def test_evaluator_step_attaches_f_evaluate(self) -> None:
        prompt = _build_cascade_prompt("root-cause-analysis",
                                        step="evaluator")
        self.assertIn("F-* UNIVERSAL SCAFFOLDING — f-evaluate.md", prompt)
        self.assertIn("Focus for this mode", prompt)

    def test_reviser_step_attaches_f_revise(self) -> None:
        prompt = _build_cascade_prompt("root-cause-analysis",
                                        step="reviser")
        self.assertIn("F-* UNIVERSAL SCAFFOLDING — f-revise.md", prompt)
        self.assertIn("Reviser guidance per criterion", prompt)

    def test_verifier_step_attaches_f_verify(self) -> None:
        prompt = _build_cascade_prompt("root-cause-analysis",
                                        step="verifier")
        self.assertIn("F-* UNIVERSAL SCAFFOLDING — f-verify.md", prompt)
        self.assertIn("Verifier checks for this mode", prompt)

    def test_consolidator_step_attaches_f_consolidate(self) -> None:
        prompt = _build_cascade_prompt("systems-dynamics",
                                        step="consolidator")
        self.assertIn("F-* UNIVERSAL SCAFFOLDING — f-consolidate.md", prompt)
        self.assertIn("Consolidator guidance", prompt)


class TestPhase7TierCHelpers(unittest.TestCase):
    """Phase 7 Tier C — verdict classification + default-gear extraction
    helpers powering ``run_tier_c_pipeline``."""

    def test_classify_verdict_verified(self) -> None:
        self.assertEqual(_classify_verdict(
            "All checks passed. VERIFIED."), "VERIFIED")
        self.assertEqual(_classify_verdict(
            "VERIFIED — output clears V1-V8."), "VERIFIED")

    def test_classify_verdict_with_corrections(self) -> None:
        self.assertEqual(_classify_verdict(
            "Some drift detected; corrections applied. "
            "VERIFIED WITH CORRECTIONS."),
            "VERIFIED_WITH_CORRECTIONS")

    def test_classify_verdict_failed(self) -> None:
        self.assertEqual(_classify_verdict(
            "Multiple mandatory fixes unaddressed. "
            "VERIFICATION FAILED."),
            "VERIFICATION_FAILED")
        # Failure marker wins even if "VERIFIED" appears elsewhere.
        self.assertEqual(_classify_verdict(
            "Initially VERIFIED draft but review flagged: "
            "VERIFICATION FAILED."),
            "VERIFICATION_FAILED")

    def test_classify_verdict_unknown(self) -> None:
        self.assertEqual(_classify_verdict(""), "UNKNOWN")
        self.assertEqual(_classify_verdict("(no verdict present)"),
                         "UNKNOWN")

    def test_extract_default_gear_reads_mode_file(self) -> None:
        # Sample each distinct gear value from rebuilt mode files.
        rca_text = (MODES_DIR / "root-cause-analysis.md").read_text()
        self.assertEqual(_extract_default_gear(rca_text), 3)
        syn_text = (MODES_DIR / "synthesis.md").read_text()
        self.assertEqual(_extract_default_gear(syn_text), 4)
        pe_text = (MODES_DIR / "passion-exploration.md").read_text()
        self.assertEqual(_extract_default_gear(pe_text), 2)

    def test_extract_default_gear_fallback(self) -> None:
        self.assertEqual(_extract_default_gear(""), 3)
        # No DEFAULT GEAR heading — falls back to 3.
        self.assertEqual(_extract_default_gear(
            "## TRIGGER CONDITIONS\n\nsome body\n"), 3)


class TestPhase7AggregateTierCFields(unittest.TestCase):
    """``_aggregate`` must emit Tier C verdict distribution + per-run
    tier_c_* excerpts when runs carry a non-empty ``tier_c_verdict``,
    and must not emit those keys for pre-Phase-7 runs (backward
    compatibility)."""

    def test_runs_without_verdict_omit_tier_c_keys(self) -> None:
        r = RunResult(
            query="q", raw_response="", envelope={"schema_version": "0.2"},
            structural=[CriterionResult(id="S1", passed=True, detail="")],
            composite=[],
        )
        agg = _aggregate([r])
        self.assertNotIn("tier_c_verdict_distribution", agg)
        self.assertNotIn("tier_c_verified_rate", agg)
        self.assertNotIn("tier_c_verdict", agg["runs"][0])

    def test_runs_with_verdict_produce_distribution(self) -> None:
        runs = [
            RunResult(
                query="q1", raw_response="", envelope={"schema_version": "0.2"},
                structural=[CriterionResult(id="S1", passed=True, detail="")],
                composite=[],
                tier_c_verdict="VERIFIED",
                tier_c_verifier_response="VERIFIED.",
                tier_c_gear=3,
            ),
            RunResult(
                query="q2", raw_response="", envelope={"schema_version": "0.2"},
                structural=[CriterionResult(id="S1", passed=True, detail="")],
                composite=[],
                tier_c_verdict="VERIFIED_WITH_CORRECTIONS",
                tier_c_verifier_response="VERIFIED WITH CORRECTIONS.",
                tier_c_gear=3,
            ),
            RunResult(
                query="q3", raw_response="", envelope={"schema_version": "0.2"},
                structural=[CriterionResult(id="S1", passed=False,
                                            detail="missing")],
                composite=[],
                tier_c_verdict="VERIFICATION_FAILED",
                tier_c_verifier_response="VERIFICATION FAILED.",
                tier_c_gear=4,
            ),
        ]
        agg = _aggregate(runs)
        self.assertEqual(agg["tier_c_verdict_distribution"],
                         {"VERIFIED": 1, "VERIFIED_WITH_CORRECTIONS": 1,
                          "VERIFICATION_FAILED": 1})
        self.assertAlmostEqual(agg["tier_c_verified_rate"], 2 / 3)
        for row in agg["runs"]:
            self.assertIn("tier_c_verdict", row)
            self.assertIn("tier_c_gear", row)
            self.assertIn("tier_c_verifier_excerpt", row)


# ---------------------------------------------------------------------------
# Live Tier A (network) — skipped unless ORA_TIER_A_LIVE=1
# ---------------------------------------------------------------------------

@unittest.skipUnless(
    _get_gemini_key() and os.environ.get("ORA_TIER_A_LIVE") == "1",
    "Tier A live test requires gemini-api-key in keyring + "
    "ORA_TIER_A_LIVE=1.",
)
class TestTierALiveEmission(unittest.TestCase):
    def _run_mode(self, mode_name: str) -> None:
        runs = int(os.environ.get("ORA_TIER_A_RUNS", "3"))
        result = run_tier_a(
            mode_name,
            runs_per_query=runs,
            model=os.environ.get("ORA_TIER_A_MODEL", "gemini"),
        )
        self.assertGreaterEqual(
            result["overall_pass_rate"], 0.9,
            f"{mode_name} Tier A below 0.90: "
            f"{result['overall_pass_rate']:.2%} "
            f"({result['total_runs']} runs).",
        )

    def test_root_cause_analysis(self) -> None:
        self._run_mode("root-cause-analysis")

    def test_systems_dynamics(self) -> None:
        self._run_mode("systems-dynamics")

    def test_decision_under_uncertainty(self) -> None:
        self._run_mode("decision-under-uncertainty")

    def test_competing_hypotheses(self) -> None:
        self._run_mode("competing-hypotheses")


@unittest.skipUnless(
    _get_gemini_key() and os.environ.get("ORA_TIER_A_LIVE") == "1",
    "Cascade Tier A live test requires gemini-api-key + ORA_TIER_A_LIVE=1.",
)
class TestCascadeTierALiveEmission(unittest.TestCase):
    """Phase 6 — cascade-aware pass-rate assertion. The cascade is where
    Phase 5's investment pays off; this test measures the reviser's
    revised-draft pass rate against the same ≥ 0.9 threshold used for
    analyst-only."""

    def _run_mode(self, mode_name: str) -> None:
        runs = int(os.environ.get("ORA_TIER_A_RUNS", "3"))
        result = run_cascade_tier_a(
            mode_name,
            runs_per_query=runs,
            model=os.environ.get("ORA_TIER_A_MODEL", "gemini"),
        )
        self.assertGreaterEqual(
            result["overall_pass_rate"], 0.9,
            f"{mode_name} cascade Tier A below 0.90: "
            f"{result['overall_pass_rate']:.2%} "
            f"({result['total_runs']} runs).",
        )

    def test_root_cause_analysis(self) -> None:
        self._run_mode("root-cause-analysis")

    def test_systems_dynamics(self) -> None:
        self._run_mode("systems-dynamics")


# ---------------------------------------------------------------------------
# WP-5.5 — cascade structural tests (analyst → evaluator → reviser →
# verifier, plus consolidator for Gear 4 modes). These tests are STRUCTURAL
# — they confirm each step's output shape matches what the next step
# expects. They do NOT judge model quality; quality is Tier B/C's remit.
# Skipped unless ORA_TIER_A_LIVE=1 (same gate as TestTierALiveEmission).
# ---------------------------------------------------------------------------


def _cascade_has_all_headers(response: str, required: tuple[str, ...]) -> list[str]:
    """Return the list of required headers missing from the response."""
    missing = []
    for header in required:
        pattern = rf'##\s+{re.escape(header)}\s*\n'
        if not re.search(pattern, response):
            missing.append(header)
    return missing


# Representative canonical query per mode — kept concrete enough to
# exercise the cascade without triggering over-long runs. Each cascade
# test class picks one.
_CASCADE_QUERIES = {
    "root-cause-analysis": (
        "Deployments to production have been failing intermittently for "
        "the past two weeks. Some releases go through fine; others hang "
        "on health checks and auto-rollback. The on-call rotation has "
        "tried restarting the build cluster, bumping memory limits, and "
        "pinning a specific base image. Nothing has held. What are the "
        "root causes and what should we do about them?"
    ),
    "systems-dynamics": (
        "Our engineering velocity keeps oscillating — we ship faster for "
        "six weeks, then we hit a period where everything slows to a "
        "crawl, then we ship fast again. No one has changed the team or "
        "the process. Draw the feedback structure and identify the "
        "highest-leverage interventions."
    ),
}


@unittest.skipUnless(
    _get_gemini_key() and os.environ.get("ORA_TIER_A_LIVE") == "1",
    "Cascade structural tests require gemini-api-key + ORA_TIER_A_LIVE=1.",
)
class TestCascade_Evaluator(unittest.TestCase):
    """Analyst → Evaluator: the evaluator's output must match the universal
    seven-section contract (VERDICT / CONFIDENCE / MANDATORY FIXES /
    SUGGESTED IMPROVEMENTS / COVERAGE GAPS / UNCERTAINTIES /
    CROSS-FINDING CONFLICTS)."""

    MODE_NAME = "root-cause-analysis"

    def test_evaluator_output_matches_universal_contract(self) -> None:
        from mode_success_criteria import check_evaluator_output_shape
        query = _CASCADE_QUERIES[self.MODE_NAME]
        analyst_prompt = _build_cascade_prompt(self.MODE_NAME, step="analyst")
        analyst_response = _call_gemini(analyst_prompt, query)
        self.assertTrue(len(analyst_response) > 100,
                        f"analyst output truncated: {analyst_response[:200]!r}")

        evaluator_prompt = _build_cascade_prompt(self.MODE_NAME, step="evaluator")
        evaluator_user = (
            "The analyst produced the following output for the query above. "
            "Evaluate it per the universal seven-section contract.\n\n"
            "## ORIGINAL QUERY\n\n"
            f"{query}\n\n"
            "## ANALYST OUTPUT\n\n"
            f"{analyst_response}"
        )
        evaluator_response = _call_gemini(evaluator_prompt, evaluator_user)
        results = check_evaluator_output_shape(evaluator_response)
        failures = [(r.id, r.detail) for r in results if not r.passed]
        self.assertEqual(
            failures, [],
            f"evaluator output shape violations: {failures}\n\n"
            f"EVALUATOR OUTPUT (first 2000 chars):\n{evaluator_response[:2000]}"
        )


@unittest.skipUnless(
    _get_gemini_key() and os.environ.get("ORA_TIER_A_LIVE") == "1",
    "Cascade structural tests require gemini-api-key + ORA_TIER_A_LIVE=1.",
)
class TestCascade_Reviser(unittest.TestCase):
    """Analyst → Evaluator → Reviser: the reviser's output must contain the
    seven mirror-contract sections (ADDRESSED / NOT ADDRESSED / INCORPORATED
    / DECLINED / REMAINING UNCERTAINTIES / REVISED DRAFT / CHANGELOG)."""

    MODE_NAME = "root-cause-analysis"
    REQUIRED_HEADERS = (
        "ADDRESSED",
        "NOT ADDRESSED",
        "INCORPORATED",
        "DECLINED",
        "REMAINING UNCERTAINTIES",
        "REVISED DRAFT",
        "CHANGELOG",
    )

    def test_reviser_output_matches_mirror_contract(self) -> None:
        query = _CASCADE_QUERIES[self.MODE_NAME]
        analyst_prompt = _build_cascade_prompt(self.MODE_NAME, step="analyst")
        analyst_response = _call_gemini(analyst_prompt, query)

        evaluator_prompt = _build_cascade_prompt(self.MODE_NAME, step="evaluator")
        evaluator_response = _call_gemini(
            evaluator_prompt,
            f"## ORIGINAL QUERY\n\n{query}\n\n"
            f"## ANALYST OUTPUT\n\n{analyst_response}"
        )

        reviser_prompt = _build_cascade_prompt(self.MODE_NAME, step="reviser")
        reviser_response = _call_gemini(
            reviser_prompt,
            f"## ORIGINAL QUERY\n\n{query}\n\n"
            f"## YOUR ORIGINAL ANALYSIS\n\n{analyst_response}\n\n"
            f"## EVALUATOR'S CRITIQUE\n\n{evaluator_response}\n\n"
            "Revise your analysis per the universal reviser output contract."
        )
        missing = _cascade_has_all_headers(reviser_response, self.REQUIRED_HEADERS)
        self.assertEqual(
            missing, [],
            f"reviser output missing headers: {missing}\n\n"
            f"REVISER OUTPUT (first 2000 chars):\n{reviser_response[:2000]}"
        )


@unittest.skipUnless(
    _get_gemini_key() and os.environ.get("ORA_TIER_A_LIVE") == "1",
    "Cascade structural tests require gemini-api-key + ORA_TIER_A_LIVE=1.",
)
class TestCascade_Verifier(unittest.TestCase):
    """Analyst → Evaluator → Reviser → Verifier: the verifier's output must
    contain the universal V1-V8 pass/fail bullets plus a Verification
    Status line."""

    MODE_NAME = "root-cause-analysis"

    def test_verifier_output_contains_status_and_universal_checks(self) -> None:
        query = _CASCADE_QUERIES[self.MODE_NAME]
        # Run the full chain.
        analyst_prompt = _build_cascade_prompt(self.MODE_NAME, step="analyst")
        analyst_response = _call_gemini(analyst_prompt, query)

        evaluator_prompt = _build_cascade_prompt(self.MODE_NAME, step="evaluator")
        evaluator_response = _call_gemini(
            evaluator_prompt,
            f"## ORIGINAL QUERY\n\n{query}\n\n"
            f"## ANALYST OUTPUT\n\n{analyst_response}"
        )

        reviser_prompt = _build_cascade_prompt(self.MODE_NAME, step="reviser")
        reviser_response = _call_gemini(
            reviser_prompt,
            f"## ORIGINAL QUERY\n\n{query}\n\n"
            f"## YOUR ORIGINAL ANALYSIS\n\n{analyst_response}\n\n"
            f"## EVALUATOR'S CRITIQUE\n\n{evaluator_response}\n\n"
            "Revise your analysis per the universal reviser output contract."
        )

        verifier_prompt = _build_cascade_prompt(self.MODE_NAME, step="verifier")
        verifier_response = _call_gemini(
            verifier_prompt,
            f"## ORIGINAL QUERY\n\n{query}\n\n"
            f"## ORIGINAL ANALYSIS\n\n{analyst_response}\n\n"
            f"## EVALUATOR MANDATORY FIXES (subset of evaluator output)\n\n"
            f"{evaluator_response}\n\n"
            f"## REVISED ANALYSIS (reviser output)\n\n{reviser_response}\n\n"
            "Run the universal V1-V8 verifier checklist plus mode-specific "
            "verifier checks."
        )

        # At minimum the verifier output must contain:
        #   - one of VERIFIED / VERIFIED WITH CORRECTIONS / VERIFICATION FAILED
        #   - references to V1..V5 checks (V2/V3/V6 are Gear-4-only and N/A
        #     for the RCA (Gear 3) single-stream path).
        status_tokens = ("VERIFIED", "VERIFICATION FAILED")
        has_status = any(tok in verifier_response for tok in status_tokens)
        self.assertTrue(
            has_status,
            f"verifier output lacks status token; "
            f"first 800 chars:\n{verifier_response[:800]}"
        )
        # Spot-check that at least V1 and V5 universal checks appear.
        self.assertIn("V1", verifier_response)
        self.assertIn("V5", verifier_response)


@unittest.skipUnless(
    _get_gemini_key() and os.environ.get("ORA_TIER_A_LIVE") == "1",
    "Cascade structural tests require gemini-api-key + ORA_TIER_A_LIVE=1.",
)
class TestCascade_Consolidator(unittest.TestCase):
    """Gear 4 only — Depth + Breadth verified outputs → Consolidator
    reconciles → consolidated output preserves both streams' verdicts."""

    MODE_NAME = "systems-dynamics"  # Gear 4

    def test_consolidator_output_preserves_both_streams(self) -> None:
        query = _CASCADE_QUERIES[self.MODE_NAME]
        # Two independent analyst streams.
        depth_prompt = _build_cascade_prompt(self.MODE_NAME, step="analyst",
                                              slot="depth")
        breadth_prompt = _build_cascade_prompt(self.MODE_NAME, step="analyst",
                                                slot="breadth")
        depth_response = _call_gemini(depth_prompt, query)
        breadth_response = _call_gemini(breadth_prompt, query)

        consolidator_prompt = _build_cascade_prompt(
            self.MODE_NAME, step="consolidator"
        )
        consolidator_response = _call_gemini(
            consolidator_prompt,
            f"## ORIGINAL QUERY\n\n{query}\n\n"
            f"## DEPTH STREAM OUTPUT\n\n{depth_response}\n\n"
            f"## BREADTH STREAM OUTPUT\n\n{breadth_response}\n\n"
            "Reconcile per the mode's consolidator guidance and emit the "
            "consolidated output + Continuity Prompt."
        )

        # Consolidated output must contain both the synthesis structure and
        # attribution for divergent findings.
        required = (
            "CONSOLIDATED ANALYSIS",
            "Convergent Findings",
            "Divergent Findings",
            "Synthesis",
            "CONTINUITY PROMPT",
        )
        missing = []
        for header in required:
            if header not in consolidator_response:
                missing.append(header)
        self.assertEqual(
            missing, [],
            f"consolidator output missing: {missing}\n\n"
            f"CONSOLIDATOR OUTPUT (first 2000 chars):\n"
            f"{consolidator_response[:2000]}"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main_cli() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Tier A mode emission harness")
    p.add_argument("--mode", default="root-cause-analysis",
                   choices=sorted(MODE_SPECS.keys()))
    p.add_argument("--runs", type=int, default=3,
                   help="runs per canonical query (default: 3)")
    p.add_argument("--model", default="gemini", choices=["gemini", "claude"])
    p.add_argument("--output", default=None,
                   help="write full JSON results to PATH")
    p.add_argument("--threshold", type=float, default=0.9)
    p.add_argument("--timeout", type=float, default=None,
                   help="per-call timeout in seconds (default: "
                        "$ORA_TIER_A_TIMEOUT or 60)")
    p.add_argument("--verbose", action="store_true",
                   help="print per-call timing")
    p.add_argument("--cascade", action="store_true",
                   help="Phase 6: run cascade-aware harness "
                        "(analyst → evaluator → reviser; score the "
                        "revised draft)")
    p.add_argument("--tier-c", action="store_true",
                   help="Phase 7: run end-to-end Tier C harness "
                        "(analyst → evaluator → reviser → verifier, "
                        "plus consolidator + final verifier for Gear 4; "
                        "track VERIFIED / VERIFIED WITH CORRECTIONS / "
                        "VERIFICATION FAILED verdict distribution)")
    p.add_argument("--envelope-retry", action="store_true",
                   help="Phase 6: if analyst doesn't emit an "
                        "`ora-visual` fence, rerun once with an explicit "
                        "EMISSION REMINDER appended to the user prompt")
    args = p.parse_args()

    if args.tier_c and args.cascade:
        p.error("--tier-c and --cascade are mutually exclusive; "
                "Tier C is a superset of cascade-aware.")

    if args.tier_c:
        harness = run_tier_c_pipeline
        label = "Tier C"
    elif args.cascade:
        harness = run_cascade_tier_a
        label = "Cascade Tier A"
    else:
        harness = run_tier_a
        label = "Tier A"

    result = harness(
        args.mode,
        runs_per_query=args.runs,
        model=args.model,
        timeout_s=args.timeout,
        verbose=args.verbose,
        envelope_retry=args.envelope_retry,
    )
    print(f"\n=== {label} — {args.mode} ({args.model}) ===")
    print(f"  total runs:            {result['total_runs']}")
    print(f"  overall pass rate:     {result['overall_pass_rate']:.1%}")
    print(f"  structural pass rate:  {result['structural_pass_rate']:.1%}")
    if result["composite_pass_rate"] is not None:
        print(f"  composite pass rate:   "
              f"{result['composite_pass_rate']:.1%}")
    # Phase 7 — surface Tier C verdict distribution.
    if "tier_c_verdict_distribution" in result:
        print(f"  verifier-VERIFIED rate: "
              f"{result['tier_c_verified_rate']:.1%}")
        print("  verdict distribution:")
        for verdict, count in sorted(
                result["tier_c_verdict_distribution"].items()):
            print(f"    {verdict}: {count}")
    # Phase 6 — surface how many runs used the envelope-retry path.
    if args.envelope_retry:
        retries = sum(1 for r in result["runs"]
                      if r.get("envelope_retry_used"))
        print(f"  envelope-retry used:   {retries}/{result['total_runs']}")
    print("  per-criterion pass rates:")
    for k, v in result["per_criterion_pass_rate"].items():
        marker = " " if v >= 0.9 else "!"
        print(f"   {marker}{k}: {v:.1%}")

    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2))
        print(f"  wrote full results to {args.output}")

    return 0 if result["overall_pass_rate"] >= args.threshold else 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].startswith("--"):
        sys.exit(_main_cli())
    unittest.main()
