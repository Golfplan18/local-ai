#!/usr/bin/env python3
"""
Per-mode structural success criteria — WP-4.2.

Lifts the structural checkers authored for the Tier A harness into a
shared module that the adversarial reviewer (`visual_adversarial`) and
the test harness (`tests/test_mode_emission`) both consume. No
duplication.

Scope: **structural** criteria only (the machine-verifiable ones — schema
validity, envelope-type allowlists, field presence, numeric bounds,
canonical-name checks, etc.). Semantic criteria (M-series, requiring
prose + LLM judgement) and composite criteria (C-series, requiring both
prose and envelope) remain in the harness for now; see Phase 5.

Public surface
--------------

.. code:: python

    from mode_success_criteria import check_structural, CriterionResult

    results = check_structural("root-cause-analysis", envelope)
    # -> list[CriterionResult]   (id, passed, detail)

``check_structural`` returns an empty list for modes without a
structural checker registered (project-mode, structured-output, and any
yet-unregistered mode). Callers treat "no checker" as silent pass.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from visual_validator import validate_envelope


# ---------------------------------------------------------------------------
# CriterionResult — shared dataclass
# ---------------------------------------------------------------------------

@dataclass
class CriterionResult:
    id: str
    passed: bool
    detail: str = ""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _first_error_detail(validation) -> str:
    if not validation.errors:
        return ""
    err = validation.errors[0].as_dict()
    return f"{err['code']} @ {err['path']}: {err['message'][:120]}"


def _short_alt_len(envelope: dict) -> int:
    sd = envelope.get("semantic_description") or {}
    return len(sd.get("short_alt") or "")


def _semantic_description_complete(envelope: dict) -> bool:
    sd = envelope.get("semantic_description") or {}
    required = ("level_1_elemental", "level_2_statistical",
                "level_3_perceptual", "short_alt")
    return (
        all((sd.get(k) or "").strip() for k in required)
        and len(sd.get("short_alt") or "") <= 150
    )


def _preamble_checks(envelope: dict, mode_name: str,
                     allowed_types: set[str],
                     relation_expected: str,
                     add, validation) -> None:
    """Shared S2-S6 preamble — schema-valid / type / mode_context /
    canvas_action / relation_to_prose. S1 (envelope presence) is the
    caller's concern."""
    add("S2", validation.valid, _first_error_detail(validation))
    vtype = envelope.get("type")
    add("S3", vtype in allowed_types, f"type={vtype}")
    add("S4", envelope.get("mode_context") == mode_name,
        f"mode_context={envelope.get('mode_context')!r}")
    add("S5", envelope.get("canvas_action") == "replace",
        f"canvas_action={envelope.get('canvas_action')!r}")
    add("S6", envelope.get("relation_to_prose") == relation_expected,
        f"relation={envelope.get('relation_to_prose')!r}")


def _concept_map_shape_ok(spec: dict, min_concepts: int = 4,
                          min_phrases: int = 2, min_props: int = 3,
                          require_cross_link: bool = True) -> tuple[bool, str]:
    concepts = spec.get("concepts") or []
    phrases = spec.get("linking_phrases") or []
    props = spec.get("propositions") or []
    concept_ids = {c.get("id") for c in concepts if c.get("id")}
    phrase_ids = {p.get("id") for p in phrases if p.get("id")}
    resolved = all(
        p.get("from_concept") in concept_ids
        and p.get("to_concept") in concept_ids
        and p.get("via_phrase") in phrase_ids
        for p in props
    )
    has_cross = any(p.get("is_cross_link") for p in props)
    ok = (
        len(concepts) >= min_concepts
        and len(phrases) >= min_phrases
        and len(props) >= min_props
        and resolved
        and (has_cross if require_cross_link else True)
    )
    return ok, (
        f"concepts={len(concepts)} phrases={len(phrases)} "
        f"props={len(props)} resolved={resolved} cross={has_cross}"
    )


def _pro_con_shape_ok(spec: dict, min_pros: int = 2,
                      min_cons: int = 2) -> tuple[bool, str]:
    claim = (spec.get("claim") or "").strip()
    pros = spec.get("pros") or []
    cons = spec.get("cons") or []
    pros_ok = len(pros) >= min_pros and all(
        (p.get("text") or "").strip() for p in pros
    )
    cons_ok = len(cons) >= min_cons and all(
        (c.get("text") or "").strip() for c in cons
    )
    ok = bool(claim) and pros_ok and cons_ok
    return ok, f"claim={bool(claim)} pros={len(pros)} cons={len(cons)}"


def _mermaid_dsl_ok(spec: dict, dialect: str) -> tuple[bool, str]:
    dsl = (spec.get("dsl") or "").strip()
    if dialect == "flowchart":
        first = dsl.splitlines()[0].strip().lower() if dsl else ""
        return (
            bool(dsl)
            and spec.get("dialect") == "flowchart"
            and (first.startswith("flowchart") or first.startswith("graph")),
            f"dialect={spec.get('dialect')!r} first={first[:30]!r}",
        )
    return bool(dsl), f"dsl_len={len(dsl)}"


# ---------------------------------------------------------------------------
# RCA-specific helpers & constants
# ---------------------------------------------------------------------------

RCA_CANONICAL: dict[str, set[str]] = {
    "6M": {"Man", "Machine", "Method", "Material", "Measurement",
           "Milieu", "Mother Nature", "Environment"},
    "4P": {"People", "Process", "Policy", "Plant"},
    "4S": {"Surroundings", "Suppliers", "Systems", "Skills"},
    "8P": {"Product", "Price", "Place", "Promotion", "People",
           "Process", "Physical Evidence", "Productivity"},
}
BANNED_EFFECT_PREFIXES = (
    "increase ", "reduce ", "implement ", "adopt ", "deploy ", "improve ",
)

_LOOP_ID_RE = re.compile(r"^[RB][0-9]+$")
ACH_VOCAB = {"CC", "C", "N", "I", "II", "NA"}


def _fishbone_max_depth(causes, d: int = 1) -> int:
    m = d
    for c in causes or []:
        sub = c.get("sub_causes")
        if sub:
            m = max(m, _fishbone_max_depth(sub, d + 1))
    return m


# ---------------------------------------------------------------------------
# Per-mode structural checkers
# ---------------------------------------------------------------------------

def check_rca_structural(envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []

    def add(id_: str, passed: bool, detail: str = "") -> None:
        results.append(CriterionResult(id=id_, passed=passed, detail=detail))

    validation = validate_envelope(envelope)
    add("S2", validation.valid, _first_error_detail(validation))

    vtype = envelope.get("type")
    add("S3", vtype in {"fishbone", "causal_loop_diagram"}, f"type={vtype}")
    add("S4", envelope.get("mode_context") == "root-cause-analysis",
        f"mode_context={envelope.get('mode_context')!r}")
    add("S5", envelope.get("canvas_action") == "replace",
        f"canvas_action={envelope.get('canvas_action')!r}")

    spec = envelope.get("spec") or {}
    if vtype == "fishbone":
        effect = (spec.get("effect") or "").strip()
        effect_ok = bool(effect) and not any(
            effect.lower().startswith(p) for p in BANNED_EFFECT_PREFIXES
        )
        add("S6", effect_ok, f"effect={effect[:60]!r}")

        framework = spec.get("framework")
        add("S7", framework in {"6M", "4P", "4S", "8P", "custom"},
            f"framework={framework!r}")

        cats = spec.get("categories") or []
        add("S8", len(cats) >= 3, f"category_count={len(cats)}")

        non_empty = all(
            isinstance(c.get("causes"), list) and len(c["causes"]) >= 1
            and all((cause.get("text") or "").strip()
                    for cause in c["causes"])
            for c in cats
        )
        add("S9", non_empty, "")

        max_d = max(
            (_fishbone_max_depth(c.get("causes")) for c in cats),
            default=0,
        )
        add("S10", max_d >= 2, f"max_depth={max_d}")

        if framework and framework != "custom":
            allowed = RCA_CANONICAL.get(framework, set())
            names = [c.get("name") for c in cats]
            bad = [n for n in names if n not in allowed]
            add("S11", len(bad) == 0, f"non_canonical={bad}")
        else:
            add("S11", True, "framework=custom")

    elif vtype == "causal_loop_diagram":
        loops = spec.get("loops") or []
        add("S6", True, "cld: effect-phrasing n/a")
        add("S7", True, "cld: framework n/a")
        add("S8", True, "cld: category-count n/a")
        add("S9", True, "cld: checked by S2")
        add("S10",
            any(len(lp.get("members", [])) >= 2 for lp in loops),
            f"loop_count={len(loops)}")
        add("S11", True, "cld: canonical-names n/a")
    else:
        for sid in ("S6", "S7", "S8", "S9", "S10", "S11"):
            add(sid, False, f"unknown_type={vtype}")

    add("S12", _semantic_description_complete(envelope),
        f"short_alt_len={_short_alt_len(envelope)}")
    return results


def check_sd_structural(envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []

    def add(id_: str, passed: bool, detail: str = "") -> None:
        results.append(CriterionResult(id=id_, passed=passed, detail=detail))

    validation = validate_envelope(envelope)
    add("S2", validation.valid, _first_error_detail(validation))

    vtype = envelope.get("type")
    add("S3", vtype in {"causal_loop_diagram", "stock_and_flow"},
        f"type={vtype}")
    add("S4", envelope.get("mode_context") == "systems-dynamics",
        f"mode_context={envelope.get('mode_context')!r}")
    add("S5", envelope.get("canvas_action") == "replace",
        f"canvas_action={envelope.get('canvas_action')!r}")
    add("S6", envelope.get("relation_to_prose") == "visually_native",
        f"relation={envelope.get('relation_to_prose')!r}")

    spec = envelope.get("spec") or {}
    if vtype == "causal_loop_diagram":
        variables = spec.get("variables") or []
        add("S7", len(variables) >= 4, f"var_count={len(variables)}")

        links = spec.get("links") or []
        polarity_ok = all(l.get("polarity") in {"+", "-"} for l in links)
        add("S8", len(links) >= 3 and polarity_ok,
            f"links={len(links)} polarity_ok={polarity_ok}")

        loops = spec.get("loops") or []
        loop_shape_ok = (
            len(loops) >= 1
            and all(_LOOP_ID_RE.match(lp.get("id", "")) for lp in loops)
            and all(len(lp.get("members") or []) >= 2 for lp in loops)
            and all((lp.get("label") or "").strip() for lp in loops)
        )
        add("S9", loop_shape_ok, f"loop_count={len(loops)}")

        graph_cycle_err = any(
            "E_GRAPH_CYCLE" in (e.code or "") for e in validation.errors
        ) if not validation.valid else False
        add("S10", not graph_cycle_err,
            "parity-parity inferred from schema validity")

        add("S11", True, "cld: S&F-shape n/a")

    elif vtype == "stock_and_flow":
        stocks = spec.get("stocks") or []
        flows = spec.get("flows") or []
        add("S7", True, "s&f: var-count n/a")
        add("S8", True, "s&f: link-polarity n/a")
        add("S9", True, "s&f: loops n/a")
        add("S10", True, "s&f: polarity n/a")
        stock_ok = (
            len(stocks) >= 1
            and all("initial" in s and (s.get("unit") or "") for s in stocks)
        )
        flow_ok = (
            len(flows) >= 1
            and all((f.get("unit") or "") for f in flows)
        )
        add("S11", stock_ok and flow_ok,
            f"stocks_ok={stock_ok} flows_ok={flow_ok}")
    else:
        for sid in ("S7", "S8", "S9", "S10", "S11"):
            add(sid, False, f"unknown_type={vtype}")

    add("S12", _semantic_description_complete(envelope),
        f"short_alt_len={_short_alt_len(envelope)}")
    return results


def check_duu_structural(envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []

    def add(id_: str, passed: bool, detail: str = "") -> None:
        results.append(CriterionResult(id=id_, passed=passed, detail=detail))

    validation = validate_envelope(envelope)
    add("S2", validation.valid, _first_error_detail(validation))

    vtype = envelope.get("type")
    add("S3", vtype in {"decision_tree", "influence_diagram", "tornado"},
        f"type={vtype}")
    add("S4", envelope.get("mode_context") == "decision-under-uncertainty",
        f"mode_context={envelope.get('mode_context')!r}")
    add("S5", envelope.get("canvas_action") == "replace",
        f"canvas_action={envelope.get('canvas_action')!r}")
    add("S6", envelope.get("relation_to_prose") == "integrated",
        f"relation={envelope.get('relation_to_prose')!r}")

    spec = envelope.get("spec") or {}
    if vtype == "decision_tree":
        mode = spec.get("mode")
        root = spec.get("root") or {}
        s7_ok = (
            mode in {"decision", "probability"}
            and root.get("kind") in {"decision", "chance"}
            and (mode != "decision" or (spec.get("utility_units") or ""))
        )
        add("S7", s7_ok,
            f"mode={mode} root.kind={root.get('kind')} "
            f"units={spec.get('utility_units')!r}")
        prob_err = any(
            "E_PROB_SUM" in (e.code or "") for e in validation.errors
        ) if not validation.valid else False
        add("S8", not prob_err, "probabilities inferred from validator")
        add("S9", True, "dt: influence_diagram n/a")
        add("S10", True, "dt: tornado n/a")
        add("S11", True, "dt: functional-arc DAG n/a")

    elif vtype == "influence_diagram":
        nodes = spec.get("nodes") or []
        value_count = sum(1 for n in nodes if n.get("kind") == "value")
        kinds = {n.get("kind") for n in nodes}
        arcs = spec.get("arcs") or []
        arcs_valid = all(
            a.get("type") in {"informational", "functional", "relevance"}
            for a in arcs
        )
        add("S7", True, "id: decision_tree n/a")
        add("S8", True, "id: probability-sum n/a")
        add("S9",
            value_count == 1
            and "decision" in kinds and "chance" in kinds
            and arcs_valid,
            f"value_count={value_count} kinds={kinds} arcs_valid={arcs_valid}")
        add("S10", True, "id: tornado n/a")
        cycle_err = any(
            "E_GRAPH_CYCLE" in (e.code or "") for e in validation.errors
        ) if not validation.valid else False
        add("S11", not cycle_err, "DAG inferred from validator")

    elif vtype == "tornado":
        params = spec.get("parameters") or []
        sort_by = spec.get("sort_by")
        fields_ok = all(
            isinstance(p.get("label"), str) and p["label"]
            and all(isinstance(p.get(k), (int, float))
                    for k in ("low_value", "high_value",
                              "outcome_at_low", "outcome_at_high"))
            for p in params
        )
        sort_err = any(
            "sorted by |swing|" in (e.message or "") for e in validation.errors
        ) if not validation.valid else False
        add("S7", True, "tornado: decision_tree n/a")
        add("S8", True, "tornado: prob-sum n/a")
        add("S9", True, "tornado: influence_diagram n/a")
        add("S10",
            len(params) >= 2 and fields_ok
            and sort_by in {"swing", "high_impact", "custom"}
            and not sort_err,
            f"params={len(params)} fields_ok={fields_ok} "
            f"sort={sort_by} sort_err={sort_err}")
        add("S11", True, "tornado: functional-arc DAG n/a")
    else:
        for sid in ("S7", "S8", "S9", "S10", "S11"):
            add(sid, False, f"unknown_type={vtype}")

    add("S12", _semantic_description_complete(envelope),
        f"short_alt_len={_short_alt_len(envelope)}")
    return results


def check_ch_structural(envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []

    def add(id_: str, passed: bool, detail: str = "") -> None:
        results.append(CriterionResult(id=id_, passed=passed, detail=detail))

    validation = validate_envelope(envelope)
    add("S2", validation.valid, _first_error_detail(validation))

    vtype = envelope.get("type")
    add("S3", vtype == "ach_matrix", f"type={vtype}")
    add("S4", envelope.get("mode_context") == "competing-hypotheses",
        f"mode_context={envelope.get('mode_context')!r}")
    add("S5", envelope.get("canvas_action") == "replace",
        f"canvas_action={envelope.get('canvas_action')!r}")
    add("S6", envelope.get("relation_to_prose") == "visually_native",
        f"relation={envelope.get('relation_to_prose')!r}")

    spec = envelope.get("spec") or {}
    hypotheses = spec.get("hypotheses") or []
    evidence = spec.get("evidence") or []
    cells = spec.get("cells") or {}
    add("S7", len(hypotheses) >= 3, f"hyp_count={len(hypotheses)}")
    add("S8", len(evidence) >= 3, f"ev_count={len(evidence)}")

    hyp_ids = [h.get("id") for h in hypotheses]
    cell_complete = all(
        e.get("id") in cells
        and all(h in cells[e["id"]] for h in hyp_ids)
        for e in evidence
    )
    add("S9", cell_complete, "cell completeness")

    vocab_ok = all(
        all(v in ACH_VOCAB
            for v in (cells.get(e.get("id"), {}) or {}).values())
        for e in evidence
    )
    add("S10", vocab_ok, "vocab compliance")

    sm = spec.get("scoring_method")
    add("S11", sm in {"heuer_tally", "bayesian", "weighted"},
        f"scoring_method={sm!r}")

    diagnostic_rows = 0
    for e in evidence:
        row = cells.get(e.get("id"), {})
        vals = {row.get(h) for h in hyp_ids if h in row}
        if len(vals) > 1:
            diagnostic_rows += 1
    add("S12", diagnostic_rows >= 1,
        f"diagnostic_rows={diagnostic_rows}/{len(evidence)}")

    add("S13", _semantic_description_complete(envelope),
        f"short_alt_len={_short_alt_len(envelope)}")
    return results


def check_tm_structural(envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    validation = validate_envelope(envelope)
    _preamble_checks(envelope, "terrain-mapping",
                     {"concept_map"}, "integrated", add, validation)
    spec = envelope.get("spec") or {}
    ok, detail = _concept_map_shape_ok(spec, 4, 2, 3, True)
    add("S7", len(spec.get("concepts") or []) >= 4,
        f"concepts={len(spec.get('concepts') or [])}")
    add("S8", len(spec.get("linking_phrases") or []) >= 2,
        f"phrases={len(spec.get('linking_phrases') or [])}")
    add("S9", ok and len(spec.get("propositions") or []) >= 3, detail)
    add("S10", any(p.get("is_cross_link") for p in (spec.get("propositions") or [])),
        "cross_link")
    add("S11", bool((spec.get("focus_question") or "").strip()),
        "focus_question")
    add("S12", _semantic_description_complete(envelope),
        f"short_alt_len={_short_alt_len(envelope)}")
    return results


def check_synthesis_structural(envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    validation = validate_envelope(envelope)
    _preamble_checks(envelope, "synthesis", {"concept_map"},
                     "integrated", add, validation)
    spec = envelope.get("spec") or {}
    concepts = spec.get("concepts") or []
    roots = [c for c in concepts if c.get("hierarchy_level") == 0]
    add("S7", len(concepts) >= 4 and len(roots) >= 2,
        f"concepts={len(concepts)} roots_level0={len(roots)}")
    add("S8", len(spec.get("linking_phrases") or []) >= 2, "")
    ok, detail = _concept_map_shape_ok(spec, 4, 2, 4, True)
    add("S9", ok, detail)
    add("S10", any(p.get("is_cross_link") for p in (spec.get("propositions") or [])),
        "")
    add("S11", bool((spec.get("focus_question") or "").strip()),
        "")
    add("S12", _semantic_description_complete(envelope), "")
    return results


def check_pe_structural(envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    validation = validate_envelope(envelope)
    _preamble_checks(envelope, "passion-exploration", {"concept_map"},
                     "integrated", add, validation)
    spec = envelope.get("spec") or {}
    add("S7", len(spec.get("concepts") or []) >= 3,
        f"concepts={len(spec.get('concepts') or [])}")
    add("S8", len(spec.get("linking_phrases") or []) >= 1, "")
    add("S9", len(spec.get("propositions") or []) >= 2, "")
    add("S10", _semantic_description_complete(envelope), "")
    for sid in ("S11", "S12"):
        add(sid, True, "passion: reduced criteria")
    return results


def check_rm_structural(envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    validation = validate_envelope(envelope)
    _preamble_checks(envelope, "relationship-mapping",
                     {"concept_map", "causal_dag"}, "integrated", add, validation)
    spec = envelope.get("spec") or {}
    vtype = envelope.get("type")
    if vtype == "concept_map":
        ok, detail = _concept_map_shape_ok(spec, 4, 2, 3, True)
        add("S7", ok, detail)
        add("S8", True, "cm: dag n/a")
    elif vtype == "causal_dag":
        dsl = (spec.get("dsl") or "").strip()
        exposure = spec.get("focal_exposure") or ""
        outcome = spec.get("focal_outcome") or ""
        cycle_err = any("E_GRAPH_CYCLE" in (e.code or "")
                        for e in validation.errors) if not validation.valid else False
        add("S7", True, "dag: cm n/a")
        add("S8",
            bool(dsl) and exposure in dsl and outcome in dsl and not cycle_err,
            f"dsl_len={len(dsl)} exposure_in_dsl={exposure in dsl} "
            f"outcome_in_dsl={outcome in dsl} cycle={cycle_err}")
    else:
        add("S7", False, f"unknown {vtype}")
        add("S8", False, f"unknown {vtype}")
    add("S9", True, "reserved")
    add("S10", _semantic_description_complete(envelope), "")
    for sid in ("S11", "S12"):
        add(sid, True, "reserved")
    return results


def check_sp_structural(envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    validation = validate_envelope(envelope)
    _preamble_checks(envelope, "scenario-planning",
                     {"quadrant_matrix"}, "integrated", add, validation)
    spec = envelope.get("spec") or {}
    add("S7", spec.get("subtype") == "scenario_planning",
        f"subtype={spec.get('subtype')!r}")
    quadrants = spec.get("quadrants") or {}
    four_ok = all(
        quadrants.get(k) and (quadrants[k].get("name") or "").strip()
        and (quadrants[k].get("narrative") or "").strip()
        for k in ("TL", "TR", "BL", "BR")
    )
    add("S8", four_ok, "four_quadrants_with_narrative")
    indicators_ok = all(
        isinstance(quadrants.get(k, {}).get("indicators"), list)
        and len(quadrants[k]["indicators"]) >= 1
        for k in ("TL", "TR", "BL", "BR")
    )
    add("S9", indicators_ok, "each_quadrant_has_indicators")
    rationale = (spec.get("axes_independence_rationale") or "").strip()
    add("S10", len(rationale) >= 40, f"rationale_len={len(rationale)}")
    x_axis = spec.get("x_axis") or {}
    y_axis = spec.get("y_axis") or {}
    axes_ok = all(
        (ax.get("label") or "").strip()
        and (ax.get("low_label") or "").strip()
        and (ax.get("high_label") or "").strip()
        for ax in (x_axis, y_axis)
    )
    add("S11", axes_ok, "axes_complete")
    add("S12", _semantic_description_complete(envelope), "")
    return results


def check_cm_structural(envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    validation = validate_envelope(envelope)
    _preamble_checks(envelope, "constraint-mapping",
                     {"quadrant_matrix", "pro_con"}, "integrated", add, validation)
    spec = envelope.get("spec") or {}
    vtype = envelope.get("type")
    if vtype == "quadrant_matrix":
        add("S7", spec.get("subtype") == "strategic_2x2",
            f"subtype={spec.get('subtype')!r}")
        items = spec.get("items") or []
        items_ok = (
            len(items) >= 3
            and all(isinstance(it.get("label"), str) and it["label"]
                    and isinstance(it.get("x"), (int, float))
                    and isinstance(it.get("y"), (int, float))
                    and 0 <= it["x"] <= 1 and 0 <= it["y"] <= 1
                    for it in items)
        )
        add("S8", items_ok, f"items={len(items)}")
        add("S9", bool((spec.get("axes_independence_rationale") or "").strip()),
            "")
        add("S10", True, "qm: pro_con n/a")
    elif vtype == "pro_con":
        ok, detail = _pro_con_shape_ok(spec, 2, 2)
        for sid in ("S7", "S8", "S9"):
            add(sid, True, "pc: qm n/a")
        add("S10", ok, detail)
    add("S11", _semantic_description_complete(envelope), "")
    add("S12", True, "reserved")
    return results


def check_ba_structural(envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    validation = validate_envelope(envelope)
    _preamble_checks(envelope, "benefits-analysis",
                     {"pro_con", "tornado"}, "integrated", add, validation)
    spec = envelope.get("spec") or {}
    vtype = envelope.get("type")
    if vtype == "pro_con":
        ok, detail = _pro_con_shape_ok(spec, 2, 2)
        add("S7", ok, detail)
        for sid in ("S8", "S9", "S10"):
            add(sid, True, "pc: tornado n/a")
    elif vtype == "tornado":
        params = spec.get("parameters") or []
        sort_by = spec.get("sort_by")
        fields_ok = all(
            isinstance(p.get("label"), str) and p["label"]
            and all(isinstance(p.get(k), (int, float))
                    for k in ("low_value", "high_value",
                              "outcome_at_low", "outcome_at_high"))
            for p in params
        )
        sort_err = any("sorted by |swing|" in (e.message or "")
                       for e in validation.errors) if not validation.valid else False
        for sid in ("S7",):
            add(sid, True, "tornado: pc n/a")
        add("S8", len(params) >= 2 and fields_ok,
            f"params={len(params)} fields_ok={fields_ok}")
        add("S9",
            sort_by in {"swing", "high_impact", "custom"} and not sort_err,
            f"sort={sort_by} sort_err={sort_err}")
        add("S10", True, "tornado: reserved")
    add("S11", _semantic_description_complete(envelope), "")
    add("S12", True, "reserved")
    return results


def check_da_structural(envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    validation = validate_envelope(envelope)
    _preamble_checks(envelope, "dialectical-analysis",
                     {"ibis"}, "integrated", add, validation)
    spec = envelope.get("spec") or {}
    nodes = spec.get("nodes") or []
    kinds = [n.get("type") for n in nodes]
    add("S7", "question" in kinds, f"has_question={'question' in kinds}")
    idea_count = sum(1 for k in kinds if k == "idea")
    add("S8", idea_count >= 2, f"idea_nodes={idea_count}")
    add("S9", validation.valid, "ibis grammar via validator")
    add("S10", "con" in kinds, f"has_con={'con' in kinds}")
    add("S11", _semantic_description_complete(envelope), "")
    add("S12", True, "reserved")
    return results


def check_cb_structural(envelope: dict) -> list[CriterionResult]:
    import json as _json
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    validation = validate_envelope(envelope)
    _preamble_checks(envelope, "cui-bono",
                     {"flowchart", "concept_map"}, "integrated", add, validation)
    spec = envelope.get("spec") or {}
    vtype = envelope.get("type")
    if vtype == "flowchart":
        ok, detail = _mermaid_dsl_ok(spec, "flowchart")
        add("S7", ok, detail)
        for sid in ("S8", "S9"):
            add(sid, True, "fc: cm n/a")
    elif vtype == "concept_map":
        ok, detail = _concept_map_shape_ok(spec, 4, 2, 3, False)
        add("S7", True, "cm: fc n/a")
        add("S8", ok, detail)
        add("S9", True, "reserved")
    env_text = _json.dumps(envelope).lower()
    has_author = any(w in env_text for w in ("author", "authors", "standard-setting", "regulator"))
    has_benef = any(w in env_text for w in ("benefici", "exempt", "bears cost", "constituenc"))
    add("S10", has_author and has_benef,
        f"has_author={has_author} has_benef={has_benef}")
    add("S11", _semantic_description_complete(envelope), "")
    add("S12", True, "reserved")
    return results


def check_cs_structural(envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    validation = validate_envelope(envelope)
    _preamble_checks(envelope, "consequences-and-sequel",
                     {"causal_dag", "flowchart"}, "integrated", add, validation)
    spec = envelope.get("spec") or {}
    vtype = envelope.get("type")
    if vtype == "causal_dag":
        dsl = spec.get("dsl") or ""
        exposure = spec.get("focal_exposure") or ""
        outcome = spec.get("focal_outcome") or ""
        nodes = set(re.findall(r"[a-zA-Z_][a-zA-Z_0-9]*", dsl)) - {"dag"}
        cycle_err = any("E_GRAPH_CYCLE" in (e.code or "")
                        for e in validation.errors) if not validation.valid else False
        add("S7", True, "cs: flowchart n/a")
        add("S8", bool(dsl) and exposure in dsl and outcome in dsl and not cycle_err,
            f"exposure_ok={exposure in dsl} outcome_ok={outcome in dsl} cycle={cycle_err}")
        add("S9", len(nodes) >= 5, f"nodes={len(nodes)}")
    elif vtype == "flowchart":
        ok, detail = _mermaid_dsl_ok(spec, "flowchart")
        add("S7", ok, detail)
        for sid in ("S8", "S9"):
            add(sid, True, "fc: dag n/a")
    add("S10", True, "longest-path check reserved for LLM-reviewer")
    add("S11", _semantic_description_complete(envelope), "")
    add("S12", True, "reserved")
    return results


def check_si_structural(envelope: dict) -> list[CriterionResult]:
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    validation = validate_envelope(envelope)
    _preamble_checks(envelope, "strategic-interaction",
                     {"decision_tree", "influence_diagram"}, "integrated", add, validation)
    spec = envelope.get("spec") or {}
    vtype = envelope.get("type")
    if vtype == "decision_tree":
        mode = spec.get("mode")
        root = spec.get("root") or {}
        add("S7", mode in {"decision", "probability"}
            and root.get("kind") in {"decision", "chance"}
            and (mode != "decision" or spec.get("utility_units")),
            f"mode={mode}")
        prob_err = any("E_PROB_SUM" in (e.code or "")
                       for e in validation.errors) if not validation.valid else False
        add("S8", not prob_err, "probs ok")
        for sid in ("S9", "S10"):
            add(sid, True, "dt: id n/a")
    elif vtype == "influence_diagram":
        nodes = spec.get("nodes") or []
        value_count = sum(1 for n in nodes if n.get("kind") == "value")
        cycle_err = any("E_GRAPH_CYCLE" in (e.code or "")
                        for e in validation.errors) if not validation.valid else False
        for sid in ("S7", "S8"):
            add(sid, True, "id: dt n/a")
        add("S9", value_count == 1, f"value_count={value_count}")
        add("S10", not cycle_err, "functional DAG ok")
    add("S11", _semantic_description_complete(envelope), "")
    add("S12", True, "reserved")
    return results


def check_dc_structural(envelope: dict) -> list[CriterionResult]:
    """deep-clarification: envelope is OPTIONAL. Callers should branch on
    envelope presence BEFORE invoking this. When present, the envelope
    must be a valid flowchart."""
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    validation = validate_envelope(envelope)
    _preamble_checks(envelope, "deep-clarification",
                     {"flowchart"}, "integrated", add, validation)
    spec = envelope.get("spec") or {}
    ok, detail = _mermaid_dsl_ok(spec, "flowchart")
    add("S7", ok, detail)
    for sid in ("S8", "S9", "S10"):
        add(sid, True, "dc: reserved")
    add("S11", _semantic_description_complete(envelope), "")
    add("S12", True, "reserved")
    return results


def check_rt_structural(envelope: dict) -> list[CriterionResult]:
    """red-team: envelope is OPTIONAL — emitted only when the user's
    input contained a diagram to be attacked. When present, the envelope
    overlays severity-coded annotations on the user's spatial structure
    using whichever schema-valid type matches the input (concept_map,
    flowchart, or causal_loop_diagram — same convention as
    spatial-reasoning). Callers should branch on envelope presence
    BEFORE invoking this."""
    results: list[CriterionResult] = []
    add = lambda id_, p, d="": results.append(CriterionResult(id=id_, passed=p, detail=d))
    validation = validate_envelope(envelope)
    # Inline preamble — canvas_action expectation is "annotate" for
    # red-team (overlaid on user's diagram), not "replace".
    allowed_types = {"concept_map", "flowchart", "causal_loop_diagram"}
    add("S2", validation.valid, _first_error_detail(validation))
    vtype = envelope.get("type")
    add("S3", vtype in allowed_types, f"type={vtype}")
    add("S4", envelope.get("mode_context") == "red-team",
        f"mode_context={envelope.get('mode_context')!r}")
    add("S5", envelope.get("canvas_action") == "annotate",
        f"canvas_action={envelope.get('canvas_action')!r}")
    add("S6", envelope.get("relation_to_prose") == "visually_native",
        f"relation={envelope.get('relation_to_prose')!r}")
    annotations = envelope.get("annotations") or []
    add("S7", len(annotations) >= 1, f"annotations={len(annotations)}")
    # S8 — annotation kind in allowlist (callout/highlight)
    allowed_kinds = {"callout", "highlight"}
    bad_kinds = [a.get("kind") for a in annotations
                 if a.get("kind") not in allowed_kinds]
    add("S8", not bad_kinds, f"bad_kinds={bad_kinds}")
    # S9 — callout text length (<=60)
    long_callouts = [a for a in annotations
                     if a.get("kind") == "callout"
                     and len(a.get("text") or "") > 60]
    add("S9", not long_callouts, f"over_60={len(long_callouts)}")
    # S10 — severity dual encoding: each callout text must start with one of
    # the severity prefixes (Showstopper / Major / Caveat) followed by the
    # surface tag in brackets ([I] or [E]).
    severity_pattern = re.compile(
        r"^(Showstopper|Major|Caveat)\s*\[(I|E)\]:", re.IGNORECASE)
    callouts = [a for a in annotations if a.get("kind") == "callout"]
    bad_severity = [a for a in callouts
                    if not severity_pattern.match(a.get("text") or "")]
    add("S10", not bad_severity and len(callouts) >= 1,
        f"unprefixed_callouts={len(bad_severity)}")
    add("S11", _semantic_description_complete(envelope), "")
    add("S12", True, "reserved")
    return results


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

# Modes for which envelope ABSENCE is the pass condition. Callers should
# detect envelope absence before dispatching and treat it as silent pass;
# if an envelope IS emitted, that is itself a failure (the mode rejected
# visual suppression).
NO_VISUAL_MODES = frozenset({
    "steelman-construction",
    "paradigm-suspension",
    "simple",
    "standard",
    "adversarial",
})

# Modes where an envelope is OPTIONAL — emitting one is fine; emitting
# none is also fine. Structural checks only apply when an envelope is
# present.
OPTIONAL_ENVELOPE_MODES = frozenset({"deep-clarification", "passion-exploration", "red-team"})


_CHECKERS: dict[str, Callable[[dict], list[CriterionResult]]] = {
    "root-cause-analysis":        check_rca_structural,
    "systems-dynamics":           check_sd_structural,
    "decision-under-uncertainty": check_duu_structural,
    "competing-hypotheses":       check_ch_structural,
    "terrain-mapping":            check_tm_structural,
    "synthesis":                  check_synthesis_structural,
    "passion-exploration":        check_pe_structural,
    "relationship-mapping":       check_rm_structural,
    "scenario-planning":          check_sp_structural,
    "constraint-mapping":         check_cm_structural,
    "benefits-analysis":          check_ba_structural,
    "dialectical-analysis":       check_da_structural,
    "cui-bono":                   check_cb_structural,
    "consequences-and-sequel":    check_cs_structural,
    "strategic-interaction":      check_si_structural,
    "deep-clarification":         check_dc_structural,
    "red-team":                   check_rt_structural,
}


def check_structural(mode_name: str, envelope: dict) -> list[CriterionResult]:
    """Dispatch to the mode-specific structural checker.

    Returns an empty list for:
    - unknown modes (project-mode, structured-output, or any mode without
      a registered checker)
    - no-visual modes when envelope is ``None`` (expected pass)
    - optional-envelope modes when envelope is ``None`` (expected pass)

    Callers that need the "envelope emitted but mode is no-visual" signal
    should check membership in ``NO_VISUAL_MODES`` explicitly; that is a
    semantic-level judgement (the mode asked for suppression, the model
    emitted anyway) and lives outside the dispatch.
    """
    if envelope is None:
        if mode_name in NO_VISUAL_MODES or mode_name in OPTIONAL_ENVELOPE_MODES:
            return []
        # Other modes: caller should have set S1 false upstream.
        return []
    checker = _CHECKERS.get(mode_name)
    if checker is None:
        return []
    return checker(envelope)


# ---------------------------------------------------------------------------
# Universal evaluator output contract — WP-5.4
#
# Every evaluator output (Breadth-evaluates-Depth or Depth-evaluates-Breadth)
# must produce seven sections in this order as Markdown headers. The reviser
# parses this contract with regex, so structural validation here guards the
# handoff — not the quality of the critique, just that the critique has the
# shape the reviser can ingest.
#
# Matches the contract specified in:
#   - frameworks/book/f-evaluate.md  (universal contract body)
#   - vault/Working — Framework — Pipeline Cascade Integration Plan.md §5
# ---------------------------------------------------------------------------

# Seven canonical section headers in order.
EVALUATOR_CONTRACT_SECTIONS: tuple[str, ...] = (
    "VERDICT",
    "CONFIDENCE",
    "MANDATORY FIXES",
    "SUGGESTED IMPROVEMENTS",
    "COVERAGE GAPS",
    "UNCERTAINTIES",
    "CROSS-FINDING CONFLICTS",
)

_VERDICT_VALUES = frozenset({"pass", "partial", "fail"})
_CONFIDENCE_VALUES = frozenset({"high", "moderate", "low"})

# Required field keys per MANDATORY FIXES finding and per SUGGESTED
# IMPROVEMENT. The evaluator emits these as bullet sub-list keys
# (``- citation:``, ``- violated_criterion_id:`` etc.); the shape checker
# confirms each finding carries all the keys expected for its section.
_MANDATORY_FIX_FIELDS = (
    "citation",
    "violated_criterion_id",
    "what's_wrong",
    "what's_required",
)
_SUGGESTION_FIELDS = (
    "citation",
    "current_state",
    "suggested_change",
    "reasoning",
    "expected_benefit",
    "criterion_it_would_move",
)


def _extract_evaluator_section(text: str, heading: str) -> str | None:
    """Return the body between ``## heading`` and the next ``## `` / end, or
    ``None`` if the heading is absent."""
    pattern = rf'##\s+{re.escape(heading)}\s*\n(.*?)(?=\n##\s+|\Z)'
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1).strip() if m else None


def _section_has_findings(body: str) -> bool:
    """True iff a section body declares findings (vs. the literal ``None.``
    allowed when the section is empty)."""
    stripped = body.strip()
    if not stripped:
        return False
    if stripped.lower() == "none." or stripped.lower() == "none":
        return False
    # Look for bullet findings — the contract uses ``- **Finding N ... **``
    # but we accept any hyphen-list as a finding declaration.
    return bool(re.search(r'^\s*-\s', body, re.MULTILINE))


def _split_into_findings(body: str) -> list[str]:
    """Split a section body into one block per top-level bullet. Each
    block covers the bullet line plus any indented continuation lines."""
    lines = body.splitlines()
    blocks: list[str] = []
    current: list[str] = []
    for line in lines:
        if re.match(r'^\s*-\s', line) and not line.startswith("  -"):
            # New top-level bullet; flush previous
            if current:
                blocks.append("\n".join(current))
                current = []
            current.append(line)
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return [b for b in blocks if b.strip()]


def _finding_has_all_fields(block: str, required_fields: tuple[str, ...]) -> tuple[bool, list[str]]:
    """Return (all_present, missing_list) for a finding block. A field is
    declared by any occurrence of ``<field>:`` in the block — the contract
    uses ``- citation: ...`` / ``- violated_criterion_id: ...`` etc."""
    missing = []
    for field in required_fields:
        pattern = rf'(?:^|\n)\s*-?\s*{re.escape(field)}\s*:'
        if not re.search(pattern, block):
            missing.append(field)
    return (not missing, missing)


def check_evaluator_output_shape(response: str) -> list[CriterionResult]:
    """WP-5.4 — validate that evaluator output matches the universal
    seven-section contract.

    Returns a list of ``CriterionResult`` with ids ``E1`` .. ``E7``. The
    validator is structural only — it confirms the sections are present in
    the correct order and that any findings inside MANDATORY FIXES /
    SUGGESTED IMPROVEMENTS carry the required fields. Quality of the
    findings themselves is for downstream consumers (reviser, verifier,
    Tier B/C harnesses).

    Args:
        response: the evaluator's full system output (Markdown text).

    Returns:
        list of CriterionResult — each id names the check (E1..E7), passed
        is True when the check holds, detail carries the diagnostic string.
    """
    results: list[CriterionResult] = []

    def add(id_: str, passed: bool, detail: str = "") -> None:
        results.append(CriterionResult(id=id_, passed=passed, detail=detail))

    # E1 — all seven section headers present
    section_bodies: dict[str, str | None] = {
        h: _extract_evaluator_section(response, h) for h in EVALUATOR_CONTRACT_SECTIONS
    }
    missing_headers = [h for h, b in section_bodies.items() if b is None]
    add(
        "E1",
        not missing_headers,
        f"missing_headers={missing_headers}" if missing_headers
        else "all seven universal contract headers present",
    )

    # E2 — sections in canonical order
    # Find the character position of each section's header; they must be
    # strictly increasing in the order EVALUATOR_CONTRACT_SECTIONS.
    positions = []
    for h in EVALUATOR_CONTRACT_SECTIONS:
        m = re.search(rf'##\s+{re.escape(h)}\s*\n', response)
        positions.append(m.start() if m else None)
    present_positions = [p for p in positions if p is not None]
    in_order = present_positions == sorted(present_positions)
    add(
        "E2",
        in_order,
        "sections in canonical order" if in_order
        else f"out-of-order positions: {positions}",
    )

    # E3 — VERDICT body starts with one of pass|partial|fail, followed
    # by a rationale sentence.
    verdict_body = section_bodies.get("VERDICT")
    if verdict_body is None:
        add("E3", False, "VERDICT section absent")
    else:
        first_token = verdict_body.strip().split(None, 1)[0].rstrip(",.:;").lower() if verdict_body.strip() else ""
        has_rationale = len(verdict_body.split()) >= 2
        ok = first_token in _VERDICT_VALUES and has_rationale
        add(
            "E3",
            ok,
            f"verdict_token={first_token!r} has_rationale={has_rationale}",
        )

    # E4 — CONFIDENCE body is one of high|moderate|low.
    confidence_body = section_bodies.get("CONFIDENCE")
    if confidence_body is None:
        add("E4", False, "CONFIDENCE section absent")
    else:
        token = confidence_body.strip().split(None, 1)[0].rstrip(",.:;").lower() if confidence_body.strip() else ""
        ok = token in _CONFIDENCE_VALUES
        add("E4", ok, f"confidence_token={token!r}")

    # E5 — MANDATORY FIXES: empty (``None.``) or each finding has all
    # four required fields.
    mfix_body = section_bodies.get("MANDATORY FIXES")
    if mfix_body is None:
        add("E5", False, "MANDATORY FIXES section absent")
    elif not _section_has_findings(mfix_body):
        add("E5", True, "no findings (declared None)")
    else:
        findings = _split_into_findings(mfix_body)
        bad = []
        for i, f in enumerate(findings, 1):
            ok, missing = _finding_has_all_fields(f, _MANDATORY_FIX_FIELDS)
            if not ok:
                bad.append(f"#{i}: missing={missing}")
        add(
            "E5",
            not bad,
            f"findings={len(findings)} " + (f"bad={bad}" if bad else "all_fields_present"),
        )

    # E6 — SUGGESTED IMPROVEMENTS: empty or each has all six required fields.
    sug_body = section_bodies.get("SUGGESTED IMPROVEMENTS")
    if sug_body is None:
        add("E6", False, "SUGGESTED IMPROVEMENTS section absent")
    elif not _section_has_findings(sug_body):
        add("E6", True, "no findings (declared None)")
    else:
        findings = _split_into_findings(sug_body)
        bad = []
        for i, f in enumerate(findings, 1):
            ok, missing = _finding_has_all_fields(f, _SUGGESTION_FIELDS)
            if not ok:
                bad.append(f"#{i}: missing={missing}")
        add(
            "E6",
            not bad,
            f"findings={len(findings)} " + (f"bad={bad}" if bad else "all_fields_present"),
        )

    # E7 — COVERAGE GAPS / UNCERTAINTIES / CROSS-FINDING CONFLICTS are
    # present (empty 'None.' acceptable). The reviser relies on all three
    # being emitted even when empty.
    tail_sections = ("COVERAGE GAPS", "UNCERTAINTIES", "CROSS-FINDING CONFLICTS")
    absent_tail = [s for s in tail_sections if section_bodies.get(s) is None]
    add(
        "E7",
        not absent_tail,
        f"absent_tail_sections={absent_tail}" if absent_tail
        else "all tail sections present (possibly 'None.')",
    )

    return results


__all__ = [
    "CriterionResult",
    "check_structural",
    "check_evaluator_output_shape",
    "EVALUATOR_CONTRACT_SECTIONS",
    "NO_VISUAL_MODES",
    "OPTIONAL_ENVELOPE_MODES",
    "check_rca_structural",
    "check_sd_structural",
    "check_duu_structural",
    "check_ch_structural",
    "check_tm_structural",
    "check_synthesis_structural",
    "check_pe_structural",
    "check_rm_structural",
    "check_sp_structural",
    "check_cm_structural",
    "check_ba_structural",
    "check_da_structural",
    "check_cb_structural",
    "check_cs_structural",
    "check_si_structural",
    "check_dc_structural",
    "check_rt_structural",
    "RCA_CANONICAL",
    "BANNED_EFFECT_PREFIXES",
    "ACH_VOCAB",
]
