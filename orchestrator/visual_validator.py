#!/usr/bin/env python3
"""
Ora Visual Validator — server-side schema + structural-invariant checker.

WP-1.6 Phase 1 module. Validates ``ora-visual`` envelopes emitted by
analytical models before they reach the client-side renderer. Two layers:

1. **JSON Schema** — loads the 23 files under ``~/ora/config/visual-schemas/``
   and validates every envelope against the discriminated-union ``envelope.json``
   schema using ``jsonschema`` + ``referencing`` (the recipe documented in
   ``visual-schemas/README.md``). Schemas are loaded once at import time
   and cached in module globals.

2. **Structural invariants** — per-type semantic checks that JSON Schema
   cannot express (graph acyclicity, probability-sum, IBIS grammar,
   reference resolution, etc.). Catalogued in the schema README's
   "Constraints JSON Schema cannot express" table. Each type gets a
   ``_check_<type>(spec)`` function; ``validate_envelope`` dispatches on
   ``envelope['type']`` after the schema pass.

Public API::

    result = validate_envelope(envelope)   # -> ValidationResult
    result.valid         # bool
    result.errors        # list[Error] (severity='error'; blocking)
    result.warnings      # list[Error] (severity='warning'; informational)

Error codes mirror ``~/ora/server/static/ora-visual-compiler/errors.js``
(E_SCHEMA_INVALID, E_GRAPH_CYCLE, E_PROB_SUM, E_IBIS_GRAMMAR,
E_UNRESOLVED_REF, E_DSL_PARSE, plus W_* warning codes). See the
``CODES`` constant below — it is the single Python mirror of the JS set.

Composes with ``visual_adversarial`` (the T-rule / LLM-prior-inversion
layer). Pipeline order is validator first; if it returns ``valid=False``
with blocking errors, adversarial review is skipped (nothing to adversarially
review). The ``boot.py`` integration helper in ``_visual_hook`` runs both.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# External deps (present in the ora runtime per WP-0.2 test harness).
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012


# ---------------------------------------------------------------------------
# Error code registry — mirror of errors.js CODES
# ---------------------------------------------------------------------------

# Prefix E_ = blocking; W_ = informational. Kept in one-for-one correspondence
# with ``server/static/ora-visual-compiler/errors.js``. If you add a code here,
# add the JS twin (or vice versa) — drift between the two sides will produce
# a client that can't recognize a server finding or vice versa.
CODES = {
    # Envelope-level
    "E_MISSING_FIELD":        "E_MISSING_FIELD",
    "E_UNKNOWN_TYPE":         "E_UNKNOWN_TYPE",
    "E_SCHEMA_VERSION":       "E_SCHEMA_VERSION",
    "E_SCHEMA_INVALID":       "E_SCHEMA_INVALID",
    "E_NO_SPEC":              "E_NO_SPEC",
    # Per-type structural
    "E_GRAPH_CYCLE":          "E_GRAPH_CYCLE",
    "E_PROB_SUM":             "E_PROB_SUM",
    "E_IBIS_GRAMMAR":         "E_IBIS_GRAMMAR",
    "E_DSL_PARSE":            "E_DSL_PARSE",
    "E_UNRESOLVED_REF":       "E_UNRESOLVED_REF",
    # Warnings
    "W_UNKNOWN_MAJOR":        "W_UNKNOWN_MAJOR",
    "W_NOTE_FIELD_STRIPPED":  "W_NOTE_FIELD_STRIPPED",
    "W_MISSING_TITLE":        "W_MISSING_TITLE",
    "W_MISSING_CAPTION":      "W_MISSING_CAPTION",
    "W_STOCK_ISOLATED":       "W_STOCK_ISOLATED",
    "W_UNITS_MISMATCH":       "W_UNITS_MISMATCH",
    "W_ACH_NONDIAGNOSTIC":    "W_ACH_NONDIAGNOSTIC",
    "W_ORPHAN_NODE":          "W_ORPHAN_NODE",
    "W_EFFECT_SOLUTION_PHRASED": "W_EFFECT_SOLUTION_PHRASED",
    "W_NO_CROSS_LINKS":       "W_NO_CROSS_LINKS",
    "W_AXES_DEPENDENT":       "W_AXES_DEPENDENT",
}


@dataclass
class Error:
    """A single validation finding.

    ``code`` is one of the ``CODES`` values; ``severity`` is 'error' (E_*) or
    'warning' (W_*), derived from the prefix but stored explicitly so
    adversarial re-classification can override it (strict mode upgrading
    Major warnings to Critical, for example).
    """

    code: str
    message: str
    path: str = ""
    severity: str = "error"

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "path": self.path, "severity": self.severity}


@dataclass
class ValidationResult:
    valid: bool
    errors: list[Error] = field(default_factory=list)
    warnings: list[Error] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": [e.as_dict() for e in self.errors],
            "warnings": [w.as_dict() for w in self.warnings],
        }


def _err(code: str, message: str, path: str = "") -> Error:
    return Error(code=code, message=message, path=path, severity="error")


def _warn(code: str, message: str, path: str = "") -> Error:
    return Error(code=code, message=message, path=path, severity="warning")


# ---------------------------------------------------------------------------
# Schema loading — once at import time, cached in module globals
# ---------------------------------------------------------------------------

SCHEMAS_ROOT = Path(os.path.expanduser("~/ora/config/visual-schemas"))
KNOWN_MAJOR = 0  # schema_version major we understand; 0.x is current

_ENVELOPE_VALIDATOR: Draft202012Validator | None = None


def _build_validator() -> Draft202012Validator:
    """Load every schema under ``visual-schemas/`` into a referencing registry
    and return a ``Draft202012Validator`` bound to ``envelope.json``.

    Schemas are registered twice — once under their declared ``$id`` and
    once under their relative path — because the envelope's ``oneOf`` branches
    use path-style ``$ref``s ("specs/comparison.json") while inter-schema
    references inside individual specs sometimes use the absolute ``$id``.
    Binding both styles is the recipe the README documents.
    """
    if not SCHEMAS_ROOT.exists():
        raise RuntimeError(f"visual-schemas directory not found: {SCHEMAS_ROOT}")

    def _load(p: Path) -> dict:
        return json.loads(p.read_text())

    resources: list[tuple[str, Resource]] = []
    paths = [
        SCHEMAS_ROOT / "envelope.json",
        SCHEMAS_ROOT / "semantic_description.json",
        SCHEMAS_ROOT / "spatial_representation.json",
        *sorted((SCHEMAS_ROOT / "specs").glob("*.json")),
    ]
    for p in paths:
        schema = _load(p)
        rel = p.relative_to(SCHEMAS_ROOT).as_posix()
        res = Resource(contents=schema, specification=DRAFT202012)
        if "$id" in schema:
            resources.append((schema["$id"], res))
        resources.append((rel, res))

    registry = Registry().with_resources(resources)
    envelope = _load(SCHEMAS_ROOT / "envelope.json")
    return Draft202012Validator(envelope, registry=registry)


def _get_validator() -> Draft202012Validator:
    """Lazy accessor — imports of this module succeed even if schemas are
    briefly unavailable; the first ``validate_envelope`` call raises."""
    global _ENVELOPE_VALIDATOR
    if _ENVELOPE_VALIDATOR is None:
        _ENVELOPE_VALIDATOR = _build_validator()
    return _ENVELOPE_VALIDATOR


# ---------------------------------------------------------------------------
# Envelope-level checks (things jsonschema does, plus the version gate)
# ---------------------------------------------------------------------------

def _strip_note(envelope: dict) -> tuple[dict, bool]:
    """Pop the ``_note`` field if present. The WP-0.2 invalid example files
    carry ``_note`` documenting the violation; with ``additionalProperties:false``
    the envelope schema would reject it for the wrong reason. Strip once before
    running the validator. Returns ``(stripped, was_present)``."""
    if isinstance(envelope, dict) and "_note" in envelope:
        stripped = {k: v for k, v in envelope.items() if k != "_note"}
        return stripped, True
    return envelope, False


def _version_check(envelope: dict) -> list[Error]:
    """Semver gate: unknown major version is a warning (forward compat)."""
    out: list[Error] = []
    v = envelope.get("schema_version", "")
    if not isinstance(v, str) or "." not in v:
        return out  # structural schema will catch it
    try:
        major = int(v.split(".")[0])
    except ValueError:
        return out
    if major > KNOWN_MAJOR:
        out.append(_warn(
            CODES["W_UNKNOWN_MAJOR"],
            f"schema_version major={major} unknown; current parser targets {KNOWN_MAJOR}.x",
            "schema_version",
        ))
    return out


def _format_path(path) -> str:
    # jsonschema's absolute_path is a deque of segments; render as a/b[0]/c.
    out = []
    for seg in path:
        if isinstance(seg, int):
            out.append(f"[{seg}]")
        else:
            out.append("/" + str(seg) if out else str(seg))
    return "".join(out)


def _schema_errors(envelope: dict) -> list[Error]:
    """Run jsonschema and return a flat list of Error objects."""
    validator = _get_validator()
    raw = list(validator.iter_errors(envelope))
    return [
        _err(
            CODES["E_SCHEMA_INVALID"],
            err.message,
            _format_path(err.absolute_path),
        )
        for err in raw
    ]


# ---------------------------------------------------------------------------
# Per-type structural invariants
# ---------------------------------------------------------------------------

def _check_causal_loop_diagram(spec: dict) -> list[Error]:
    """CLD invariants (schema README row 1-2):

    * ``variables[].id`` unique; every ``links[].from/to`` resolves.
    * Declared loops are genuine cycles in the graph.
    * Loop ``type`` (R/B) matches the parity of '-' polarities on its edges
      (even → R, odd → B).
    * Orphan nodes (no incident edges) flagged unless ``allow_isolated: true``.
    """
    out: list[Error] = []
    variables = spec.get("variables") or []
    links = spec.get("links") or []
    loops = spec.get("loops") or []

    ids: set[str] = set()
    for i, v in enumerate(variables):
        vid = v.get("id")
        if vid in ids:
            out.append(_err(CODES["E_UNRESOLVED_REF"], f"duplicate variable id '{vid}'", f"spec.variables[{i}].id"))
        if isinstance(vid, str):
            ids.add(vid)

    # Build adjacency and edge polarity map for loop-parity check.
    adj: dict[str, list[tuple[str, str]]] = {v: [] for v in ids}
    connected: set[str] = set()
    for i, lk in enumerate(links):
        f, t = lk.get("from"), lk.get("to")
        if f not in ids:
            out.append(_err(CODES["E_UNRESOLVED_REF"], f"links[{i}].from='{f}' not in variables", f"spec.links[{i}].from"))
        if t not in ids:
            out.append(_err(CODES["E_UNRESOLVED_REF"], f"links[{i}].to='{t}' not in variables", f"spec.links[{i}].to"))
        if f in ids and t in ids:
            adj.setdefault(f, []).append((t, lk.get("polarity", "+")))
            connected.add(f)
            connected.add(t)

    allow_isolated = bool(spec.get("allow_isolated"))
    if not allow_isolated:
        for v in sorted(ids - connected):
            out.append(_warn(CODES["W_ORPHAN_NODE"], f"variable '{v}' has no incident edges", "spec.variables"))

    # Loop checks.
    for i, loop in enumerate(loops):
        members = loop.get("members") or []
        declared_type = loop.get("type", "")
        if not members:
            continue
        # Verify cycle: each consecutive pair + last-to-first must be in adjacency.
        ok = True
        minus = 0
        n = len(members)
        for j in range(n):
            src, dst = members[j], members[(j + 1) % n]
            edges = [p for (to_, p) in adj.get(src, []) if to_ == dst]
            if not edges:
                ok = False
                out.append(_err(
                    CODES["E_UNRESOLVED_REF"],
                    f"loop {loop.get('id')} asserts edge {src}->{dst} that does not exist",
                    f"spec.loops[{i}].members",
                ))
                break
            if "-" in edges[0]:
                minus += 1
        if ok:
            expected = "B" if (minus % 2 == 1) else "R"
            if declared_type and declared_type != expected:
                out.append(_err(
                    CODES["E_GRAPH_CYCLE"],
                    f"loop {loop.get('id')} declared type={declared_type} but polarity-parity implies {expected} ({minus} negative edges)",
                    f"spec.loops[{i}].type",
                ))
    return out


def _check_stock_and_flow(spec: dict) -> list[Error]:
    """Stock-and-flow invariants:
    * flow endpoints resolve to stock or cloud ids
    * each stock has >=1 attached flow (else W_STOCK_ISOLATED)
    * info_links over auxiliaries form a DAG
    * (unit dimensional consistency is a heuristic — emit W_UNITS_MISMATCH
      only if we can detect a clear mismatch; fall silent otherwise).
    """
    out: list[Error] = []
    stocks = spec.get("stocks") or []
    flows = spec.get("flows") or []
    clouds = spec.get("clouds") or []
    auxiliaries = spec.get("auxiliaries") or []
    info_links = spec.get("info_links") or []

    stock_ids = {s.get("id") for s in stocks if s.get("id")}
    cloud_ids = {c.get("id") for c in clouds if c.get("id")}
    aux_ids = {a.get("id") for a in auxiliaries if a.get("id")}
    flow_ids = {f.get("id") for f in flows if f.get("id")}
    stock_or_cloud = stock_ids | cloud_ids

    stocks_with_flow: set[str] = set()
    for i, fl in enumerate(flows):
        f, t = fl.get("from"), fl.get("to")
        if f not in stock_or_cloud:
            out.append(_err(CODES["E_UNRESOLVED_REF"], f"flow[{i}].from='{f}' not a stock or cloud", f"spec.flows[{i}].from"))
        else:
            if f in stock_ids:
                stocks_with_flow.add(f)
        if t not in stock_or_cloud:
            out.append(_err(CODES["E_UNRESOLVED_REF"], f"flow[{i}].to='{t}' not a stock or cloud", f"spec.flows[{i}].to"))
        else:
            if t in stock_ids:
                stocks_with_flow.add(t)

    for s in stocks:
        sid = s.get("id")
        if sid not in stocks_with_flow:
            out.append(_warn(CODES["W_STOCK_ISOLATED"], f"stock '{sid}' has no attached flows", "spec.stocks"))

    # info_links: from stock|aux -> flow|aux. Check DAG over aux nodes only.
    all_ids = stock_ids | aux_ids | flow_ids
    aux_adj: dict[str, list[str]] = {a: [] for a in aux_ids}
    for i, lk in enumerate(info_links):
        f, t = lk.get("from"), lk.get("to")
        if f not in all_ids:
            out.append(_err(CODES["E_UNRESOLVED_REF"], f"info_links[{i}].from='{f}' unresolved", f"spec.info_links[{i}].from"))
        if t not in all_ids:
            out.append(_err(CODES["E_UNRESOLVED_REF"], f"info_links[{i}].to='{t}' unresolved", f"spec.info_links[{i}].to"))
        if f in aux_ids and t in aux_ids:
            aux_adj.setdefault(f, []).append(t)

    if _has_cycle(aux_adj):
        out.append(_err(CODES["E_GRAPH_CYCLE"], "info_links form a cycle over auxiliaries (must be a DAG)", "spec.info_links"))
    return out


def _check_causal_dag(spec: dict) -> list[Error]:
    """DAGitty DSL: minimal parser (enough to enforce acyclicity and the
    exposure/outcome presence check). Real rendering uses the vendor parser;
    we duplicate only the structural pieces.

    The DSL format in WP-0.2 is: ``dag { x [exposure]; y [outcome]; u [latent]; x -> y; u -> x }``.
    """
    out: list[Error] = []
    dsl = spec.get("dsl", "")
    focal_in = spec.get("focal_exposure", "")
    focal_out = spec.get("focal_outcome", "")
    if not isinstance(dsl, str) or not dsl.strip():
        out.append(_err(CODES["E_DSL_PARSE"], "causal_dag.spec.dsl is empty", "spec.dsl"))
        return out
    try:
        nodes, edges = _parse_dagitty(dsl)
    except ValueError as exc:
        out.append(_err(CODES["E_DSL_PARSE"], f"DAGitty parse failed: {exc}", "spec.dsl"))
        return out

    if focal_in and focal_in not in nodes:
        out.append(_err(CODES["E_UNRESOLVED_REF"], f"focal_exposure '{focal_in}' not declared in dsl", "spec.focal_exposure"))
    if focal_out and focal_out not in nodes:
        out.append(_err(CODES["E_UNRESOLVED_REF"], f"focal_outcome '{focal_out}' not declared in dsl", "spec.focal_outcome"))

    adj: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
    if _has_cycle(adj):
        out.append(_err(CODES["E_GRAPH_CYCLE"], "DAGitty dsl has a cycle (DAG required)", "spec.dsl"))
    return out


def _parse_dagitty(dsl: str) -> tuple[set[str], list[tuple[str, str]]]:
    # Trim outer "dag { ... }" if present.
    src = dsl.strip()
    if src.lower().startswith("dag"):
        brace = src.find("{")
        close = src.rfind("}")
        if brace < 0 or close < 0 or close < brace:
            raise ValueError("missing braces")
        src = src[brace + 1:close]
    nodes: set[str] = set()
    edges: list[tuple[str, str]] = []
    for stmt in src.split(";"):
        stmt = stmt.strip()
        if not stmt:
            continue
        if "->" in stmt:
            left, right = stmt.split("->", 1)
            a = left.strip().split()[0]
            b = right.strip().split()[0]
            edges.append((a, b))
            nodes.add(a)
            nodes.add(b)
        else:
            # node declaration like 'x [exposure]' or 'x'
            tok = stmt.split()[0]
            nodes.add(tok)
    return nodes, edges


def _check_fishbone(spec: dict) -> list[Error]:
    """Depth <= 3; framework category names constrained when framework != custom;
    effect phrased as a problem (soft lint)."""
    out: list[Error] = []
    framework = spec.get("framework", "")
    canonical = {
        "6M": {"Man", "Machine", "Method", "Material", "Measurement", "Milieu", "Mother Nature", "Environment"},
        "4P": {"People", "Process", "Policy", "Plant"},
        "4S": {"Surroundings", "Suppliers", "Systems", "Skills"},
        "8P": {"Product", "Price", "Place", "Promotion", "People", "Process", "Physical Evidence", "Productivity"},
    }
    cats = spec.get("categories") or []
    allowed = canonical.get(framework)
    for i, cat in enumerate(cats):
        if allowed and cat.get("name") not in allowed:
            out.append(_err(
                CODES["E_UNRESOLVED_REF"],
                f"fishbone category '{cat.get('name')}' not in {framework} canonical set",
                f"spec.categories[{i}].name",
            ))

    def _depth(causes, d=1):
        m = d
        for c in causes or []:
            sub = c.get("sub_causes")
            if sub:
                m = max(m, _depth(sub, d + 1))
        return m

    for i, cat in enumerate(cats):
        d = _depth(cat.get("causes"))
        if d > 3:
            out.append(_err(
                CODES["E_UNRESOLVED_REF"],
                f"fishbone category '{cat.get('name')}' exceeds depth 3 (got {d})",
                f"spec.categories[{i}]",
            ))

    effect = spec.get("effect", "") or ""
    if effect:
        low = effect.lower()
        # Soft lint: effect stated as solution ("increase X", "reduce Y", "implement Z")
        for verb in ("increase ", "reduce ", "implement ", "adopt ", "deploy ", "improve "):
            if low.startswith(verb):
                out.append(_warn(
                    CODES["W_EFFECT_SOLUTION_PHRASED"],
                    f"effect appears phrased as a solution ('{effect[:60]}'); fishbone effects should name problems",
                    "spec.effect",
                ))
                break
    return out


def _check_decision_tree(spec: dict) -> list[Error]:
    """Recursive invariants:
    * chance-node children probabilities sum to 1 ± 1e-6 (in [0,1])
    * decision-node edges carry no probability
    * terminals carry payoff when mode=decision
    * decision nodes have >= 1 child
    """
    out: list[Error] = []
    mode = spec.get("mode", "")
    root = spec.get("root")
    if not isinstance(root, dict):
        return out

    def walk(node: dict, path: str) -> None:
        kind = node.get("kind")
        children = node.get("children") or []
        if kind == "decision":
            if not children:
                out.append(_err(
                    CODES["E_UNRESOLVED_REF"],
                    "decision node has no children",
                    path,
                ))
            for i, child in enumerate(children):
                if "probability" in child:
                    out.append(_err(
                        CODES["E_PROB_SUM"],
                        "probability present on decision-node edge (not allowed)",
                        f"{path}/children[{i}].probability",
                    ))
                sub = child.get("node")
                if isinstance(sub, dict):
                    walk(sub, f"{path}/children[{i}].node")
        elif kind == "chance":
            total = 0.0
            for i, child in enumerate(children):
                p = child.get("probability")
                if not isinstance(p, (int, float)):
                    out.append(_err(
                        CODES["E_PROB_SUM"],
                        "chance-node edge missing probability",
                        f"{path}/children[{i}].probability",
                    ))
                    continue
                if p < 0 or p > 1:
                    out.append(_err(
                        CODES["E_PROB_SUM"],
                        f"probability {p} outside [0,1]",
                        f"{path}/children[{i}].probability",
                    ))
                total += float(p)
                sub = child.get("node")
                if isinstance(sub, dict):
                    walk(sub, f"{path}/children[{i}].node")
            if children and abs(total - 1.0) > 1e-6:
                out.append(_err(
                    CODES["E_PROB_SUM"],
                    f"chance-node probabilities sum to {total:.6f} (expected 1.0)",
                    f"{path}/children",
                ))
        elif kind == "terminal":
            if mode == "decision" and "payoff" not in node:
                out.append(_err(
                    CODES["E_UNRESOLVED_REF"],
                    "terminal node missing payoff (required in mode=decision)",
                    f"{path}.payoff",
                ))

    walk(root, "spec.root")
    return out


def _check_influence_diagram(spec: dict) -> list[Error]:
    """Exactly one value node. Functional-arc subgraph into value is acyclic.
    Temporal consistency when temporal_order given: no arcs into a decision
    from a later-decided node.
    """
    out: list[Error] = []
    nodes = spec.get("nodes") or []
    arcs = spec.get("arcs") or []
    temporal = spec.get("temporal_order") or []

    kinds: dict[str, str] = {}
    for n in nodes:
        nid = n.get("id")
        if nid:
            kinds[nid] = n.get("kind", "")

    value_nodes = [nid for nid, k in kinds.items() if k == "value"]
    if len(value_nodes) != 1:
        out.append(_err(
            CODES["E_UNRESOLVED_REF"],
            f"influence_diagram must have exactly one value node (got {len(value_nodes)})",
            "spec.nodes",
        ))

    # Functional subgraph acyclic
    func_adj: dict[str, list[str]] = {nid: [] for nid in kinds}
    for a in arcs:
        if a.get("type") == "functional":
            f, t = a.get("from"), a.get("to")
            if f in kinds and t in kinds:
                func_adj.setdefault(f, []).append(t)
    if _has_cycle(func_adj):
        out.append(_err(CODES["E_GRAPH_CYCLE"], "functional-arc subgraph has a cycle", "spec.arcs"))

    # Temporal consistency
    if temporal:
        order = {nid: i for i, nid in enumerate(temporal)}
        for i, a in enumerate(arcs):
            f, t = a.get("from"), a.get("to")
            if kinds.get(t) == "decision" and f in order and t in order:
                if order[f] > order[t]:
                    out.append(_err(
                        CODES["E_UNRESOLVED_REF"],
                        f"arc from '{f}' (later) to decision '{t}' (earlier) violates temporal_order",
                        f"spec.arcs[{i}]",
                    ))
    return out


def _check_ach_matrix(spec: dict) -> list[Error]:
    """Every (evidence × hypothesis) cell populated. Non-diagnostic rows
    (all cells equal) get W_ACH_NONDIAGNOSTIC."""
    out: list[Error] = []
    hypotheses = spec.get("hypotheses") or []
    evidence = spec.get("evidence") or []
    cells = spec.get("cells") or {}
    hyp_ids = [h.get("id") for h in hypotheses if h.get("id")]
    for ev in evidence:
        eid = ev.get("id")
        row = cells.get(eid)
        if not isinstance(row, dict):
            out.append(_err(
                CODES["E_UNRESOLVED_REF"],
                f"ach_matrix missing cells row for evidence '{eid}'",
                "spec.cells",
            ))
            continue
        for hid in hyp_ids:
            if hid not in row:
                out.append(_err(
                    CODES["E_UNRESOLVED_REF"],
                    f"ach_matrix cell ({eid},{hid}) missing",
                    f"spec.cells.{eid}.{hid}",
                ))
        vals = [row.get(hid) for hid in hyp_ids if hid in row]
        if vals and len(set(vals)) == 1:
            out.append(_warn(
                CODES["W_ACH_NONDIAGNOSTIC"],
                f"evidence '{eid}' non-diagnostic: all cells equal '{vals[0]}'",
                f"spec.cells.{eid}",
            ))
    return out


def _check_quadrant_matrix(spec: dict) -> list[Error]:
    """scenario_planning requires narrative in each quadrant.
    axes_independence_rationale non-empty (schema enforces existence; we
    enforce non-empty here and flag correlated items).
    """
    out: list[Error] = []
    subtype = spec.get("subtype", "")
    quadrants = spec.get("quadrants") or {}
    if subtype == "scenario_planning":
        for k in ("TL", "TR", "BL", "BR"):
            q = quadrants.get(k) or {}
            if not (q.get("narrative") or "").strip():
                out.append(_err(
                    CODES["E_UNRESOLVED_REF"],
                    f"quadrant {k} missing non-empty narrative (required for scenario_planning)",
                    f"spec.quadrants.{k}.narrative",
                ))
    rationale = (spec.get("axes_independence_rationale") or "").strip()
    if not rationale:
        out.append(_err(
            CODES["E_UNRESOLVED_REF"],
            "axes_independence_rationale must be non-empty",
            "spec.axes_independence_rationale",
        ))
    # Items bounds are schema-enforced [0,1]. Pearson correlation handled in
    # adversarial review (W_AXES_DEPENDENT) so it can use the strictness
    # escalation ladder.
    return out


def _check_bow_tie(spec: dict) -> list[Error]:
    """At least one threat, one consequence (schema enforces via minItems).
    Preventive control type enum: eliminate|reduce|detect.
    Mitigative control type enum: reduce|recover|contain.
    Schema encodes these enums; we double-check here so any ad-hoc spec passing
    JSON Schema still hits the structural layer.
    """
    out: list[Error] = []
    pc_enum = {"eliminate", "reduce", "detect"}
    mc_enum = {"reduce", "recover", "contain"}
    for i, th in enumerate(spec.get("threats") or []):
        for j, pc in enumerate(th.get("preventive_controls") or []):
            if pc.get("type") not in pc_enum:
                out.append(_err(
                    CODES["E_UNRESOLVED_REF"],
                    f"preventive control type '{pc.get('type')}' not in {pc_enum}",
                    f"spec.threats[{i}].preventive_controls[{j}].type",
                ))
    for i, cs in enumerate(spec.get("consequences") or []):
        for j, mc in enumerate(cs.get("mitigative_controls") or []):
            if mc.get("type") not in mc_enum:
                out.append(_err(
                    CODES["E_UNRESOLVED_REF"],
                    f"mitigative control type '{mc.get('type')}' not in {mc_enum}",
                    f"spec.consequences[{i}].mitigative_controls[{j}].type",
                ))
    return out


def _check_ibis(spec: dict) -> list[Error]:
    """IBIS grammar enforcement — blocking per Protocol §3.12.

    Legal triples (source kind, edge type, target kind):
    * (idea, responds_to, question)
    * (pro,  supports,    idea)
    * (con,  objects_to,  idea)
    * (question, questions, *)  — any target kind
    """
    out: list[Error] = []
    nodes = spec.get("nodes") or []
    edges = spec.get("edges") or []
    kinds = {n.get("id"): n.get("type") for n in nodes if n.get("id")}

    legal = {
        "responds_to": {("idea", "question")},
        "supports":    {("pro",  "idea")},
        "objects_to":  {("con",  "idea")},
    }

    for i, e in enumerate(edges):
        f, t, etype = e.get("from"), e.get("to"), e.get("type")
        sk, tk = kinds.get(f), kinds.get(t)
        if f not in kinds:
            out.append(_err(CODES["E_UNRESOLVED_REF"], f"edge.from='{f}' unresolved", f"spec.edges[{i}].from"))
        if t not in kinds:
            out.append(_err(CODES["E_UNRESOLVED_REF"], f"edge.to='{t}' unresolved", f"spec.edges[{i}].to"))
        if etype == "questions":
            if sk != "question":
                out.append(_err(
                    CODES["E_IBIS_GRAMMAR"],
                    f"'questions' edge must originate from a question node (got {sk})",
                    f"spec.edges[{i}]",
                ))
            continue
        if etype in legal:
            if (sk, tk) not in legal[etype]:
                out.append(_err(
                    CODES["E_IBIS_GRAMMAR"],
                    f"edge ({sk},{etype},{tk}) violates IBIS grammar; legal: {legal[etype]}",
                    f"spec.edges[{i}]",
                ))
    return out


def _check_concept_map(spec: dict) -> list[Error]:
    """Every proposition triple resolves; soft warning if no cross-links."""
    out: list[Error] = []
    concepts = {c.get("id") for c in (spec.get("concepts") or []) if c.get("id")}
    phrases = {p.get("id") for p in (spec.get("linking_phrases") or []) if p.get("id")}
    props = spec.get("propositions") or []
    saw_cross = False
    for i, p in enumerate(props):
        f = p.get("from_concept")
        via = p.get("via_phrase")
        to = p.get("to_concept")
        if f not in concepts:
            out.append(_err(CODES["E_UNRESOLVED_REF"], f"proposition.from_concept '{f}' unresolved", f"spec.propositions[{i}].from_concept"))
        if via not in phrases:
            out.append(_err(CODES["E_UNRESOLVED_REF"], f"proposition.via_phrase '{via}' unresolved", f"spec.propositions[{i}].via_phrase"))
        if to not in concepts:
            out.append(_err(CODES["E_UNRESOLVED_REF"], f"proposition.to_concept '{to}' unresolved", f"spec.propositions[{i}].to_concept"))
        if p.get("is_cross_link"):
            saw_cross = True
    if props and not saw_cross:
        out.append(_warn(
            CODES["W_NO_CROSS_LINKS"],
            "concept_map has no cross-links (Novak marker of integrative understanding)",
            "spec.propositions",
        ))
    return out


def _check_pro_con(spec: dict) -> list[Error]:
    out: list[Error] = []
    if not (spec.get("claim") or "").strip():
        out.append(_err(CODES["E_UNRESOLVED_REF"], "pro_con requires non-empty claim", "spec.claim"))
    # Shape is already covered by schema (pros, cons are arrays).
    return out


def _check_quant_spec_fields(spec: dict) -> list[Error]:
    """QUANT-family shared check: caption.source/period/n present (T15
    caption-source-n) is surfaced here as a warning so adversarial review
    can elevate it. Schema requires the caption object already."""
    out: list[Error] = []
    caption = spec.get("caption") or {}
    for k in ("source", "period", "n"):
        if k not in caption or caption.get(k) in (None, ""):
            out.append(_warn(
                CODES["W_MISSING_CAPTION"],
                f"QUANT spec missing caption.{k} (Tufte T15)",
                f"spec.caption.{k}",
            ))
    return out


def _check_tornado(spec: dict) -> list[Error]:
    """Invariants: parameters sorted by |swing| descending when sort_by='swing'."""
    out: list[Error] = []
    sort_by = spec.get("sort_by", "swing")
    params = spec.get("parameters") or []
    if sort_by == "swing" and len(params) >= 2:
        swings = [abs((p.get("outcome_at_high") or 0) - (p.get("outcome_at_low") or 0)) for p in params]
        if swings != sorted(swings, reverse=True):
            out.append(_err(
                CODES["E_UNRESOLVED_REF"],
                "tornado parameters must be sorted by |swing| descending when sort_by='swing'",
                "spec.parameters",
            ))
    return out


def _check_c4(spec: dict) -> list[Error]:
    out: list[Error] = []
    dsl = spec.get("dsl") or ""
    level = spec.get("level", "")
    if not isinstance(dsl, str) or "workspace" not in dsl:
        out.append(_err(CODES["E_DSL_PARSE"], "Structurizr DSL missing 'workspace' keyword", "spec.dsl"))
    # Level mixing check: scan for container/container-level keyword on context diagrams.
    if level == "context" and "container " in dsl:
        out.append(_err(
            CODES["E_DSL_PARSE"],
            "C4 level='context' DSL uses 'container' — level mixing not allowed",
            "spec.dsl",
        ))
    return out


def _check_mermaid_dsl(dialect: str):
    def _check(spec: dict) -> list[Error]:
        out: list[Error] = []
        dsl = spec.get("dsl") or ""
        if not isinstance(dsl, str) or not dsl.strip():
            out.append(_err(CODES["E_DSL_PARSE"], f"{dialect} dsl is empty", "spec.dsl"))
            return out
        first = dsl.lstrip().splitlines()[0].strip().lower()
        expected = {
            "flowchart": ("flowchart", "graph"),
            "sequence": ("sequencediagram",),
            "state": ("statediagram", "statediagram-v2"),
        }.get(dialect, ())
        if expected and not any(first.startswith(p) for p in expected):
            out.append(_err(
                CODES["E_DSL_PARSE"],
                f"{dialect} dsl does not begin with one of {expected}",
                "spec.dsl",
            ))
        return out
    return _check


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_cycle(adj: dict[str, list[str]]) -> bool:
    """Iterative DFS cycle detection."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in adj}
    for start in list(adj.keys()):
        if color[start] != WHITE:
            continue
        stack: list[tuple[str, int]] = [(start, 0)]
        color[start] = GRAY
        while stack:
            node, idx = stack[-1]
            neigh = adj.get(node) or []
            if idx >= len(neigh):
                color[node] = BLACK
                stack.pop()
                continue
            stack[-1] = (node, idx + 1)
            nxt = neigh[idx]
            if nxt not in color:
                color[nxt] = WHITE
            if color[nxt] == GRAY:
                return True
            if color[nxt] == WHITE:
                color[nxt] = GRAY
                stack.append((nxt, 0))
    return False


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_STRUCTURAL: dict[str, Callable[[dict], list[Error]]] = {
    "causal_loop_diagram": _check_causal_loop_diagram,
    "stock_and_flow":      _check_stock_and_flow,
    "causal_dag":          _check_causal_dag,
    "fishbone":            _check_fishbone,
    "decision_tree":       _check_decision_tree,
    "influence_diagram":   _check_influence_diagram,
    "ach_matrix":          _check_ach_matrix,
    "quadrant_matrix":     _check_quadrant_matrix,
    "bow_tie":             _check_bow_tie,
    "ibis":                _check_ibis,
    "pro_con":             _check_pro_con,
    "concept_map":         _check_concept_map,
    "tornado":             _check_tornado,
    "c4":                  _check_c4,
    "flowchart":           _check_mermaid_dsl("flowchart"),
    "sequence":            _check_mermaid_dsl("sequence"),
    "state":               _check_mermaid_dsl("state"),
    # QUANT shared checks — lightweight caption-presence warning. The T-rule
    # engine in visual_adversarial does the heavier T1/T2/T3/T10 work.
    "comparison":          _check_quant_spec_fields,
    "time_series":         _check_quant_spec_fields,
    "distribution":        _check_quant_spec_fields,
    "scatter":             _check_quant_spec_fields,
    "heatmap":             _check_quant_spec_fields,
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def validate_envelope(envelope: dict) -> ValidationResult:
    """Validate an ora-visual envelope and return a ``ValidationResult``.

    Flow:
      1. Strip the ``_note`` field if present (test-fixture convenience).
      2. Run JSON Schema validation (Draft 2020-12, referencing registry).
         Every schema failure becomes an E_SCHEMA_INVALID error.
      3. If the schema pass produced errors, return immediately — structural
         checks below assume the envelope shape is trusted.
      4. Version gate (W_UNKNOWN_MAJOR warning on unknown major).
      5. Dispatch on ``envelope['type']`` to a structural-invariant checker.

    ``valid`` is ``True`` iff there are zero errors (warnings don't block).
    """
    if not isinstance(envelope, dict):
        return ValidationResult(valid=False, errors=[_err(CODES["E_MISSING_FIELD"], "envelope must be an object")])

    envelope, had_note = _strip_note(envelope)
    warnings: list[Error] = []
    if had_note:
        warnings.append(_warn(CODES["W_NOTE_FIELD_STRIPPED"], "_note field stripped before validation", "_note"))

    errors: list[Error] = _schema_errors(envelope)
    warnings.extend(_version_check(envelope))
    if errors:
        return ValidationResult(valid=False, errors=errors, warnings=warnings)

    vtype = envelope.get("type", "")
    spec = envelope.get("spec") or {}
    if not spec:
        errors.append(_err(CODES["E_NO_SPEC"], "envelope.spec is empty", "spec"))
        return ValidationResult(valid=False, errors=errors, warnings=warnings)

    checker = _STRUCTURAL.get(vtype)
    if checker is None:
        # schema pass already rejected unknown types, so this would mean a
        # known-type enum entry without a registered checker. Treat as
        # internal error (not blocking).
        warnings.append(_warn(
            CODES["W_MISSING_TITLE"],
            f"no structural checker registered for type '{vtype}' — passing through",
            "type",
        ))
    else:
        findings = checker(spec)
        for f in findings:
            if f.severity == "error":
                errors.append(f)
            else:
                warnings.append(f)

    # Envelope-level soft checks
    if not (envelope.get("title") or "").strip():
        warnings.append(_warn(CODES["W_MISSING_TITLE"], "title missing (accessibility degraded)", "title"))

    return ValidationResult(valid=(len(errors) == 0), errors=errors, warnings=warnings)


# ---------------------------------------------------------------------------
# Spatial representation validator (WP-3.3)
# ---------------------------------------------------------------------------

_SPATIAL_VALIDATOR: Draft202012Validator | None = None


def _get_spatial_validator() -> Draft202012Validator:
    """Lazy accessor for a standalone spatial_representation validator.

    Reuses the same referencing registry as the envelope validator (so
    ``$ref``s into peer schemas resolve), but binds to ``spatial_representation.json``
    as the entry point. This keeps the WP-3.3 merged-input path fast and
    independent of the full envelope tree.
    """
    global _SPATIAL_VALIDATOR
    if _SPATIAL_VALIDATOR is None:
        if not SCHEMAS_ROOT.exists():
            raise RuntimeError(f"visual-schemas directory not found: {SCHEMAS_ROOT}")

        def _load(p: Path) -> dict:
            return json.loads(p.read_text())

        # Register the same resources the envelope validator does so any
        # cross-schema refs keep resolving.
        resources: list[tuple[str, Resource]] = []
        paths = [
            SCHEMAS_ROOT / "envelope.json",
            SCHEMAS_ROOT / "semantic_description.json",
            SCHEMAS_ROOT / "spatial_representation.json",
            *sorted((SCHEMAS_ROOT / "specs").glob("*.json")),
        ]
        for p in paths:
            schema = _load(p)
            rel = p.relative_to(SCHEMAS_ROOT).as_posix()
            res = Resource(contents=schema, specification=DRAFT202012)
            if "$id" in schema:
                resources.append((schema["$id"], res))
            resources.append((rel, res))

        registry = Registry().with_resources(resources)
        spatial_schema = _load(SCHEMAS_ROOT / "spatial_representation.json")
        _SPATIAL_VALIDATOR = Draft202012Validator(spatial_schema, registry=registry)
    return _SPATIAL_VALIDATOR


def validate_spatial_representation(spatial_rep: dict) -> ValidationResult:
    """Validate a ``spatial_representation`` object against its authoritative
    schema (``config/visual-schemas/spatial_representation.json``) plus light
    structural cross-checks.

    WP-3.3 hook — called by the server's ``/chat/multipart`` endpoint when
    the client-side canvas serializer uploads a spatial_representation JSON
    string alongside text input. Returns a ``ValidationResult`` with errors
    populated on failure so callers can reject with 400 + details.

    Cross-checks beyond JSON Schema:
    * Relationship ``source`` / ``target`` ids must resolve to declared
      entity ids (schema can't express this).
    * Cluster ``members`` must resolve to declared entity ids.
    * Hierarchy ``parent`` and ``children`` ids must resolve to declared
      entity ids.

    All cross-check failures are surfaced as ``E_UNRESOLVED_REF`` errors
    to match the taxonomy used by the envelope validator.
    """
    if not isinstance(spatial_rep, dict):
        return ValidationResult(
            valid=False,
            errors=[_err(CODES["E_MISSING_FIELD"], "spatial_representation must be an object")],
        )

    errors: list[Error] = []
    warnings: list[Error] = []

    # 1) JSON Schema pass.
    validator = _get_spatial_validator()
    for err in validator.iter_errors(spatial_rep):
        errors.append(_err(
            CODES["E_SCHEMA_INVALID"],
            err.message,
            _format_path(err.absolute_path),
        ))
    if errors:
        return ValidationResult(valid=False, errors=errors, warnings=warnings)

    # 2) Structural cross-checks (id resolution).
    entity_ids: set[str] = set()
    for i, ent in enumerate(spatial_rep.get("entities") or []):
        eid = ent.get("id")
        if isinstance(eid, str):
            if eid in entity_ids:
                errors.append(_err(
                    CODES["E_UNRESOLVED_REF"],
                    f"duplicate entity id '{eid}'",
                    f"entities[{i}].id",
                ))
            entity_ids.add(eid)

    for r, rel in enumerate(spatial_rep.get("relationships") or []):
        src, tgt = rel.get("source"), rel.get("target")
        if src not in entity_ids:
            errors.append(_err(
                CODES["E_UNRESOLVED_REF"],
                f"relationships[{r}].source='{src}' not in entities",
                f"relationships[{r}].source",
            ))
        if tgt not in entity_ids:
            errors.append(_err(
                CODES["E_UNRESOLVED_REF"],
                f"relationships[{r}].target='{tgt}' not in entities",
                f"relationships[{r}].target",
            ))

    for c, cluster in enumerate(spatial_rep.get("clusters") or []):
        for m, mid in enumerate(cluster.get("members") or []):
            if mid not in entity_ids:
                errors.append(_err(
                    CODES["E_UNRESOLVED_REF"],
                    f"clusters[{c}].members[{m}]='{mid}' not in entities",
                    f"clusters[{c}].members[{m}]",
                ))

    for h, node in enumerate(spatial_rep.get("hierarchy") or []):
        parent = node.get("parent")
        if parent not in entity_ids:
            errors.append(_err(
                CODES["E_UNRESOLVED_REF"],
                f"hierarchy[{h}].parent='{parent}' not in entities",
                f"hierarchy[{h}].parent",
            ))
        for k, cid in enumerate(node.get("children") or []):
            if cid not in entity_ids:
                errors.append(_err(
                    CODES["E_UNRESOLVED_REF"],
                    f"hierarchy[{h}].children[{k}]='{cid}' not in entities",
                    f"hierarchy[{h}].children[{k}]",
                ))

    return ValidationResult(valid=(len(errors) == 0), errors=errors, warnings=warnings)


def serialize_spatial_representation_to_text(spatial_rep: dict) -> str:
    """Render a spatial_representation JSON object as a terse machine-parseable
    text block for text-only models.

    Format (one line per item):
      <id> at [x, y]: <label>                 — entities
      <source> --(<type>)--> <target>          — relationships
      cluster "<label>": <id1>, <id2>, ...     — clusters
      hierarchy "<parent>" (<type>): <children> — hierarchy nodes

    Output is wrapped in delimited ``=== USER SPATIAL INPUT ===`` /
    ``=== END SPATIAL INPUT ===`` fences so boot.py prompt assembly can
    inject it cleanly. Empty or non-dict inputs return ``""``.
    """
    if not isinstance(spatial_rep, dict):
        return ""

    entities = spatial_rep.get("entities") or []
    if not entities:
        return ""

    lines: list[str] = ["=== USER SPATIAL INPUT ==="]
    for ent in entities:
        eid = ent.get("id", "?")
        pos = ent.get("position") or [0, 0]
        label = ent.get("label", "")
        try:
            x, y = float(pos[0]), float(pos[1])
            pos_str = f"[{x:.3f}, {y:.3f}]"
        except Exception:
            pos_str = str(pos)
        lines.append(f"{eid} at {pos_str}: {label}")

    for rel in spatial_rep.get("relationships") or []:
        src = rel.get("source", "?")
        tgt = rel.get("target", "?")
        rtype = rel.get("type", "?")
        lines.append(f"{src} --({rtype})--> {tgt}")

    for cluster in spatial_rep.get("clusters") or []:
        clabel = cluster.get("label", "")
        members = ", ".join(cluster.get("members") or [])
        lines.append(f'cluster "{clabel}": {members}')

    for node in spatial_rep.get("hierarchy") or []:
        parent = node.get("parent", "?")
        htype = node.get("type", "?")
        children = ", ".join(node.get("children") or [])
        lines.append(f'hierarchy "{parent}" ({htype}): {children}')

    lines.append("=== END SPATIAL INPUT ===")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# WP-5.2 — annotation instruction validation
# ---------------------------------------------------------------------------

# The annotation instruction schema is small and mutable while we tune
# Phase 5, so we inline a Python validator here rather than adding a
# dedicated JSON Schema file under ``config/visual-schemas/``. If the shape
# stabilizes we'll promote it to a schema file (parallel to
# ``spatial_representation.json``); for now, keeping the rules co-located
# with the pipeline code avoids schema-graph registration overhead.
#
# Shape (mirror of ``server/static/annotation-parser.js``):
#
#     {
#       "annotations": [
#         {
#           "annotation_id": "ua-callout-3",
#           "kind": "callout" | "highlight" | "strikethrough" | "sticky" | "pen",
#           "action": "expand" | "add_relationship" | "remove" | "add_element"
#                   | "modify_cluster" | "suggest_cluster" | "note",
#           "target_id": "<svg id>" | null,
#           "text": "<str>",
#           "position": [x, y] | null,
#           "points":   [[x, y], ...] | null,
#           "warning":  "<str, optional>"
#         }
#       ]
#     }

ANNOTATION_KINDS = frozenset({"callout", "highlight", "strikethrough", "sticky", "pen"})
ANNOTATION_ACTIONS = frozenset({
    "expand", "add_relationship", "remove", "add_element",
    "modify_cluster", "suggest_cluster", "note",
})


def _check_position(pos, path: str, errors: list[Error]) -> None:
    """Position is [x, y] of numbers, or None. Anything else is an error."""
    if pos is None:
        return
    if not isinstance(pos, list) or len(pos) != 2:
        errors.append(_err(
            CODES["E_SCHEMA_INVALID"],
            "position must be [x, y] list of two numbers or null",
            path,
        ))
        return
    for i, v in enumerate(pos):
        if not isinstance(v, (int, float)):
            errors.append(_err(
                CODES["E_SCHEMA_INVALID"],
                f"position[{i}] must be a number",
                f"{path}[{i}]",
            ))


def _check_points(points, path: str, errors: list[Error]) -> None:
    """Points is [[x, y], ...] or None. Each inner item must be [number, number]."""
    if points is None:
        return
    if not isinstance(points, list):
        errors.append(_err(
            CODES["E_SCHEMA_INVALID"],
            "points must be a list of [x, y] pairs or null",
            path,
        ))
        return
    for i, pt in enumerate(points):
        if not isinstance(pt, list) or len(pt) != 2:
            errors.append(_err(
                CODES["E_SCHEMA_INVALID"],
                f"points[{i}] must be [x, y]",
                f"{path}[{i}]",
            ))
            continue
        for j, v in enumerate(pt):
            if not isinstance(v, (int, float)):
                errors.append(_err(
                    CODES["E_SCHEMA_INVALID"],
                    f"points[{i}][{j}] must be a number",
                    f"{path}[{i}][{j}]",
                ))


def validate_annotations(annotations: Any) -> ValidationResult:
    """Validate an annotation-instruction payload (WP-5.2).

    Accepts either:
      * the top-level ``{"annotations": [...]}`` object, OR
      * the bare ``[...]`` list (server normalizes before calling).

    Returns a :class:`ValidationResult` with ``valid=True`` and no errors
    when the payload conforms. Empty list is valid (no annotations).

    Validation rules:
      * Top-level must be dict with ``annotations`` list, or bare list.
      * Each annotation must be a dict with:
          - ``annotation_id``: non-empty string
          - ``kind``: one of ANNOTATION_KINDS
          - ``action``: one of ANNOTATION_ACTIONS
          - ``target_id``: string or None
          - ``text``: string (may be empty)
          - ``position``: [x, y] of numbers or None
          - ``points``: [[x, y], ...] of numbers or None
      * Missing or wrong-type fields produce ``E_MISSING_FIELD`` /
        ``E_SCHEMA_INVALID`` with a path pointing at the offending spot.

    This validator is inline (no JSON Schema) because the structure is small
    and we want iteration speed while Phase 5 stabilizes.
    """
    errors: list[Error] = []
    warnings: list[Error] = []

    # Accept both shapes.
    if isinstance(annotations, dict):
        items = annotations.get("annotations")
        if not isinstance(items, list):
            errors.append(_err(
                CODES["E_MISSING_FIELD"],
                "top-level must be {'annotations': [...]} or a bare list",
                "annotations",
            ))
            return ValidationResult(valid=False, errors=errors, warnings=warnings)
    elif isinstance(annotations, list):
        items = annotations
    else:
        errors.append(_err(
            CODES["E_SCHEMA_INVALID"],
            "annotations payload must be a dict or list",
            "",
        ))
        return ValidationResult(valid=False, errors=errors, warnings=warnings)

    for i, entry in enumerate(items):
        path_prefix = f"annotations[{i}]"
        if not isinstance(entry, dict):
            errors.append(_err(
                CODES["E_SCHEMA_INVALID"],
                "annotation entry must be an object",
                path_prefix,
            ))
            continue

        # Required: annotation_id (non-empty string)
        aid = entry.get("annotation_id")
        if not isinstance(aid, str) or not aid:
            errors.append(_err(
                CODES["E_MISSING_FIELD"],
                "annotation_id missing or not a non-empty string",
                f"{path_prefix}.annotation_id",
            ))

        # Required: kind (enum)
        kind = entry.get("kind")
        if not isinstance(kind, str):
            errors.append(_err(
                CODES["E_MISSING_FIELD"],
                "kind missing or not a string",
                f"{path_prefix}.kind",
            ))
        elif kind not in ANNOTATION_KINDS:
            errors.append(_err(
                CODES["E_SCHEMA_INVALID"],
                f"unknown kind '{kind}'; must be one of "
                f"{sorted(ANNOTATION_KINDS)}",
                f"{path_prefix}.kind",
            ))

        # Required: action (enum)
        action = entry.get("action")
        if not isinstance(action, str):
            errors.append(_err(
                CODES["E_MISSING_FIELD"],
                "action missing or not a string",
                f"{path_prefix}.action",
            ))
        elif action not in ANNOTATION_ACTIONS:
            errors.append(_err(
                CODES["E_SCHEMA_INVALID"],
                f"unknown action '{action}'; must be one of "
                f"{sorted(ANNOTATION_ACTIONS)}",
                f"{path_prefix}.action",
            ))

        # target_id: string or None
        if "target_id" in entry:
            t = entry["target_id"]
            if t is not None and not isinstance(t, str):
                errors.append(_err(
                    CODES["E_SCHEMA_INVALID"],
                    "target_id must be a string or null",
                    f"{path_prefix}.target_id",
                ))

        # text: string (may be empty)
        if "text" in entry:
            t = entry["text"]
            if t is not None and not isinstance(t, str):
                errors.append(_err(
                    CODES["E_SCHEMA_INVALID"],
                    "text must be a string",
                    f"{path_prefix}.text",
                ))

        # position / points
        if "position" in entry:
            _check_position(entry["position"], f"{path_prefix}.position", errors)
        if "points" in entry:
            _check_points(entry["points"], f"{path_prefix}.points", errors)

        # warning is optional and free-form; only require a string shape.
        if "warning" in entry:
            w = entry["warning"]
            if w is not None and not isinstance(w, str):
                warnings.append(_warn(
                    CODES["W_UNKNOWN_MAJOR"],
                    "warning field present but not a string",
                    f"{path_prefix}.warning",
                ))

    return ValidationResult(
        valid=(len(errors) == 0),
        errors=errors,
        warnings=warnings,
    )


def serialize_annotations_to_text(annotations: Any) -> str:
    """Render an annotation-instruction payload as a compact fenced block
    suitable for injection into the system prompt (WP-5.2).

    Format (one line per annotation):

        [<kind>→<action>] <target_or_position>: <text>

    Wrapped in delimited ``=== USER ANNOTATIONS ===`` /
    ``=== END USER ANNOTATIONS ===`` fences so ``build_system_prompt_for_gear``
    can inject it cleanly.

    Accepts both the wrapper ``{"annotations": [...]}`` dict and a bare list.
    Empty / malformed input returns ``""`` (no fence) so callers can bolt
    this onto the prompt assembly without pre-checking.
    """
    # Normalize
    if isinstance(annotations, dict):
        items = annotations.get("annotations") or []
    elif isinstance(annotations, list):
        items = annotations
    else:
        return ""

    if not items:
        return ""

    lines: list[str] = ["=== USER ANNOTATIONS ==="]
    for entry in items:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind", "?")
        action = entry.get("action", "note")
        target = entry.get("target_id")
        position = entry.get("position")
        text = entry.get("text") or ""
        warning = entry.get("warning") or ""

        if target:
            locus = f"on {target}"
        elif isinstance(position, list) and len(position) == 2:
            try:
                locus = f"free-position ({float(position[0]):.0f}, {float(position[1]):.0f})"
            except Exception:
                locus = "free-position"
        else:
            locus = "free-position"

        # Quote non-empty text so the model can tell content from frame.
        # Strikethrough + empty text carries parenthetical semantics.
        if text.strip():
            body = f'"{text}"'
        else:
            if kind == "strikethrough" and action == "remove":
                body = "(flagged for removal)"
            elif kind == "pen":
                body = "(freehand stroke — grouping hint)"
            elif kind == "highlight":
                body = "(emphasis only)"
            else:
                body = ""

        line = f"[{kind}\u2192{action}] {locus}:"
        if body:
            line += " " + body
        if warning:
            line += f"  // note: {warning}"
        lines.append(line)

    lines.append("=== END USER ANNOTATIONS ===")
    return "\n".join(lines)


__all__ = [
    "CODES",
    "Error",
    "ValidationResult",
    "validate_envelope",
    "validate_spatial_representation",
    "serialize_spatial_representation_to_text",
    "validate_annotations",
    "serialize_annotations_to_text",
    "ANNOTATION_KINDS",
    "ANNOTATION_ACTIONS",
    "SCHEMAS_ROOT",
]
