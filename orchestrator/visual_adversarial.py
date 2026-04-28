#!/usr/bin/env python3
"""
Ora Visual Adversarial Review — spec-level T-rule & LLM-prior-inversion checks.

WP-1.6 Phase 2 module. Runs **after** ``visual_validator.validate_envelope``
has confirmed the envelope is schema-valid and structurally coherent. This
module is the adversarial spec-level pass Protocol §7 calls for: Tufte
T-rules (T1–T15) plus §7.5 LLM-prior-inversion checks (template trap,
chart-type misselection, default-settings passthrough).

Severity taxonomy (Protocol §7.3):

* **Critical** → blocks emission. Client never sees the visual; prose is
  still delivered with warnings attached so the user knows the visual was
  suppressed and why.
* **Major**    → warning. Visual is emitted with a ``warnings`` array on
  the response so the client surface can flag the issue.
* **Minor**    → informational. Logged only.

Strictness per mode (``~/ora/config/mode-to-visual.json``):

* ``lax`` / ``relaxed`` → downgrades Major → Minor (informational).
* ``strict`` / ``critical`` → upgrades Major → Critical (blocking).
* ``standard`` → no re-classification.

Strictness never touches Critical findings — by the time a T-rule reports
Critical, the visual has a real honesty problem and must block regardless
of mode configuration.

Public API::

    review = review_envelope(envelope, mode)  # -> ReviewResult
    review.blocks   # list[Finding] — Critical; block emission
    review.warns    # list[Finding] — Major
    review.infos    # list[Finding] — Minor
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from visual_validator import CODES as V_CODES  # reuse shared code names


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    rule: str          # Tufte rule id ("T1", "T5") or LLM-inversion tag
    severity: str      # "Critical" | "Major" | "Minor"
    message: str
    path: str = ""
    suggestion: str = ""

    def as_dict(self) -> dict:
        d = {"rule": self.rule, "severity": self.severity, "message": self.message, "path": self.path}
        if self.suggestion:
            d["suggestion"] = self.suggestion
        return d


@dataclass
class ReviewResult:
    blocks: list[Finding] = field(default_factory=list)
    warns:  list[Finding] = field(default_factory=list)
    infos:  list[Finding] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "blocks": [f.as_dict() for f in self.blocks],
            "warns":  [f.as_dict() for f in self.warns],
            "infos":  [f.as_dict() for f in self.infos],
        }


# ---------------------------------------------------------------------------
# Mode strictness lookup
# ---------------------------------------------------------------------------

MODE_CONFIG_PATH = Path(os.path.expanduser("~/ora/config/mode-to-visual.json"))
_MODE_CONFIG: dict | None = None


def _load_mode_config() -> dict:
    global _MODE_CONFIG
    if _MODE_CONFIG is None:
        try:
            _MODE_CONFIG = json.loads(MODE_CONFIG_PATH.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            _MODE_CONFIG = {"modes": {}}
    return _MODE_CONFIG


def _strictness_for(mode: str) -> str:
    """Return the strictness label for ``mode`` — 'strict' | 'standard' |
    'lax'. Unknown modes default to 'standard'.
    """
    cfg = _load_mode_config()
    modes = cfg.get("modes", {})
    m = modes.get(mode) or modes.get(mode.replace("_", "-")) or {}
    raw = (m.get("adversarial_strictness") or "standard").lower()
    if raw in {"critical", "strict"}:
        return "strict"
    if raw in {"lax", "relaxed"}:
        return "lax"
    return "standard"


def _apply_strictness(severity: str, mode: str) -> str:
    """Escalate/demote Major per mode strictness. Critical is immovable."""
    if severity == "Critical":
        return "Critical"
    if severity == "Minor":
        return "Minor"
    # Major is the only re-classifiable tier.
    strictness = _strictness_for(mode)
    if strictness == "strict":
        return "Critical"
    if strictness == "lax":
        return "Minor"
    return "Major"


# ---------------------------------------------------------------------------
# Template-trap blacklist (§7.5)
# ---------------------------------------------------------------------------

TEMPLATE_TRAP_STRINGS = {
    "sample data",
    "untitled",
    "chart 1",
    "chart 2",
    "series 1",
    "series 2",
    "category 1",
    "category a",
    "lorem ipsum",
    "placeholder",
    "your text here",
    "my chart",
    "example title",
}


def _template_trap_hits(envelope: dict) -> list[tuple[str, str]]:
    """Walk the envelope and return ``(path, offending_value)`` pairs where
    a blacklist string appears in a label/title position."""
    hits: list[tuple[str, str]] = []

    def walk(v, path):
        if isinstance(v, dict):
            for k, child in v.items():
                walk(child, f"{path}.{k}" if path else k)
        elif isinstance(v, list):
            for i, child in enumerate(v):
                walk(child, f"{path}[{i}]")
        elif isinstance(v, str):
            low = v.lower().strip()
            if low in TEMPLATE_TRAP_STRINGS:
                hits.append((path, v))

    walk(envelope, "")
    return hits


# ---------------------------------------------------------------------------
# T-rule implementations (per-family)
# ---------------------------------------------------------------------------

QUANT_TYPES = {"comparison", "time_series", "distribution", "scatter", "heatmap", "tornado"}


def _t1_lie_factor(envelope: dict, vtype: str) -> list[Finding]:
    """T1: lie factor in [0.95, 1.05].

    Lie factor is the ratio of visual-magnitude-change to data-magnitude-change.
    For a bar/column/dot plot, the visual channel is length — so the lie
    factor evaluates to 1.0 exactly if the chart is honestly linear. We
    can't compute pixel geometry here (we only have the spec), but we can
    detect a common dishonest pattern: bar/area charts whose
    ``encoding.y.scale.domain`` does not include 0 when the data is
    quantitative (T2 overlaps here; T1 adds a numeric lie when the domain
    minimum is an arbitrary nonzero floor).
    """
    findings: list[Finding] = []
    if vtype not in {"comparison", "distribution", "time_series"}:
        return findings
    spec = envelope.get("spec") or {}
    data_vals = _numeric_series(spec)
    if not data_vals:
        return findings
    mark = spec.get("mark")
    # Only length-encoded marks are vulnerable to T1.
    if not _is_length_mark(mark):
        return findings
    encoding = spec.get("encoding") or {}
    yenc = encoding.get("y") or {}
    scale = yenc.get("scale") or {}
    domain = scale.get("domain")
    if not domain or not isinstance(domain, list) or len(domain) != 2:
        return findings
    try:
        dom_lo, dom_hi = float(domain[0]), float(domain[1])
    except (TypeError, ValueError):
        return findings
    dom_range = dom_hi - dom_lo
    data_range = max(data_vals) - min(data_vals)
    if dom_range <= 0 or data_range <= 0:
        return findings
    lie_factor = data_range / dom_range
    if lie_factor < 0.95 or lie_factor > 1.05:
        findings.append(Finding(
            rule="T1",
            severity="Critical",
            message=f"lie factor {lie_factor:.3f} outside [0.95, 1.05] (domain range {dom_range}, data range {data_range})",
            path="spec.encoding.y.scale.domain",
            suggestion="Expand scale.domain to match data range, or declare integrity_declarations.non_zero_baseline_justified.",
        ))
    return findings


def _t2_zero_baseline(envelope: dict, vtype: str) -> list[Finding]:
    """T2: zero baseline on bar/area/column unless justified."""
    findings: list[Finding] = []
    if vtype not in {"comparison", "distribution"}:
        return findings
    spec = envelope.get("spec") or {}
    mark = spec.get("mark")
    if not _is_bar_or_area(mark):
        return findings
    yenc = ((spec.get("encoding") or {}).get("y") or {})
    scale = yenc.get("scale") or {}
    # If explicit zero:false OR domain[0] != 0, this is a violation.
    explicit_zero = scale.get("zero")
    domain = scale.get("domain")
    justified = bool((envelope.get("integrity_declarations") or {}).get("non_zero_baseline_justified"))
    violation = False
    if explicit_zero is False:
        violation = True
    if isinstance(domain, list) and domain and isinstance(domain[0], (int, float)) and domain[0] != 0:
        violation = True
    if violation and not justified:
        findings.append(Finding(
            rule="T2",
            severity="Critical",
            message=f"bar/area chart has non-zero baseline without integrity_declarations.non_zero_baseline_justified (mark={mark})",
            path="spec.encoding.y.scale",
            suggestion="Set scale.zero=true, or populate integrity_declarations.non_zero_baseline_justified with the quantity type.",
        ))
    return findings


def _t3_dimensional_conformance(envelope: dict, vtype: str) -> list[Finding]:
    """T3: visual dimensions ≤ data dimensions.

    Counts the distinct encoded ``type`` values across x/y/color/size
    channels; compares to data-field count. 3D marks (mark string contains
    'bar3d' / 'pie3d' / 'cylinder') are a hard T3 fail because 3D adds a
    dimension no field backs.
    """
    findings: list[Finding] = []
    if vtype not in QUANT_TYPES:
        return findings
    spec = envelope.get("spec") or {}
    mark = spec.get("mark")
    mark_str = mark if isinstance(mark, str) else (mark or {}).get("type", "") if isinstance(mark, dict) else ""
    if any(tok in mark_str.lower() for tok in ("3d", "cylinder", "cone", "pyramid")):
        findings.append(Finding(
            rule="T3",
            severity="Critical",
            message=f"mark '{mark_str}' encodes a dimension without a data field backing it",
            path="spec.mark",
            suggestion="Use a flat 2D mark (bar, point, line).",
        ))
    encoding = spec.get("encoding") or {}
    encoded_channels = [c for c in ("x", "y", "color", "size", "shape") if c in encoding]
    # Peek at data field count.
    data_vals = (spec.get("data") or {}).get("values") or []
    if data_vals and isinstance(data_vals[0], dict):
        field_count = len(data_vals[0].keys())
        if len(encoded_channels) > field_count and field_count > 0:
            findings.append(Finding(
                rule="T3",
                severity="Major",
                message=f"{len(encoded_channels)} encoding channels but only {field_count} data fields — visual may overclaim structure",
                path="spec.encoding",
                suggestion="Drop unused channels or add data fields.",
            ))
    return findings


def _t5_chartjunk(envelope: dict, vtype: str) -> list[Finding]:
    """T5 hard blacklist: pie, arc, 3D marks, decorative marks."""
    findings: list[Finding] = []
    if vtype not in QUANT_TYPES:
        return findings
    spec = envelope.get("spec") or {}
    mark = spec.get("mark")
    mark_str = mark if isinstance(mark, str) else (mark or {}).get("type", "") if isinstance(mark, dict) else ""
    low = mark_str.lower()
    banned_tokens = ("pie", "arc", "3d", "cylinder", "cone", "pyramid", "doughnut")
    for tok in banned_tokens:
        if tok in low:
            memorability = bool(envelope.get("memorability_goal"))
            if memorability and tok not in ("3d", "pie", "doughnut"):
                # Memorability exception is bounded; pie/3D are never OK.
                continue
            findings.append(Finding(
                rule="T5",
                severity="Critical",
                message=f"chartjunk mark '{mark_str}' blacklisted (token '{tok}')",
                path="spec.mark",
                suggestion="Use bar, point, or dot-plot encodings — Cleveland-McGill ranks position higher than angle/area.",
            ))
            break
    return findings


def _t7_labelling(envelope: dict, vtype: str) -> list[Finding]:
    """T7: axis titles, units, n, source, period.

    Phase 7 — QUANT attribution (source / period / n) may be carried
    either as a non-empty top-level ``envelope.caption`` string (current
    path; the base envelope schema declares this field) or as a
    structured ``spec.caption`` object (legacy path; most current spec
    schemas forbid it under ``additionalProperties: false``). Resolution
    order:

    1. If ``envelope.caption`` is a non-empty string → attribution
       present; do not flag. The checker does not parse the string for
       the three sub-fields — non-empty authorial attribution is
       treated as evidence of intent and is the structurally correct
       location per the base envelope schema.
    2. Else if ``spec.caption`` is a dict → check for missing
       ``source`` / ``period`` / ``n`` fields and flag each.
    3. Else → flag the missing top-level ``envelope.caption`` with a
       single finding at path ``envelope.caption``.

    This closes the tornado / DUU schema-vs-checker mismatch diagnosed
    at Phase 6 (``specs/tornado.json`` has no ``spec.caption`` property
    and ``additionalProperties: false`` would reject one).
    """
    findings: list[Finding] = []
    if not (envelope.get("title") or "").strip():
        findings.append(Finding(rule="T7", severity="Major", message="missing envelope.title", path="title"))
    if vtype not in QUANT_TYPES:
        return findings
    env_caption = envelope.get("caption")
    if isinstance(env_caption, str) and env_caption.strip():
        return findings
    spec = envelope.get("spec") or {}
    spec_caption = spec.get("caption")
    if isinstance(spec_caption, dict):
        for k in ("source", "period", "n"):
            if not spec_caption.get(k):
                findings.append(Finding(
                    rule="T7",
                    severity="Major",
                    message=f"spec.caption.{k} absent (T7 labelling completeness)",
                    path=f"spec.caption.{k}",
                ))
    else:
        findings.append(Finding(
            rule="T7",
            severity="Major",
            message="envelope.caption absent (T7 labelling completeness — attribution missing)",
            path="envelope.caption",
            suggestion="Populate envelope.caption with source, period, and n (e.g., 'Source: FRED. Period: 2020-2024. n=48.').",
        ))
    return findings


def _t8_scale_disclosure(envelope: dict, vtype: str) -> list[Finding]:
    """T8: log/symlog/pow scales require base disclosure."""
    findings: list[Finding] = []
    if vtype not in QUANT_TYPES:
        return findings
    spec = envelope.get("spec") or {}
    encoding = spec.get("encoding") or {}
    for ch in ("x", "y"):
        scale = ((encoding.get(ch) or {}).get("scale") or {})
        stype = scale.get("type")
        if stype in ("log", "symlog", "pow"):
            base = scale.get("base")
            declared = (envelope.get("integrity_declarations") or {}).get("log_scale_base")
            if not base and not declared:
                findings.append(Finding(
                    rule="T8",
                    severity="Critical",
                    message=f"encoding.{ch}.scale.type='{stype}' without base disclosure",
                    path=f"spec.encoding.{ch}.scale.base",
                    suggestion="Set scale.base explicitly or declare integrity_declarations.log_scale_base.",
                ))
    return findings


def _t10_banking(envelope: dict, vtype: str) -> list[Finding]:
    """T10: banking to 45°. Warning-only per Protocol §7.3 (aspect-ratio
    deviations are Major). Requires inspecting data for a line mark; if we
    can compute a data range we estimate the banked aspect ratio and flag
    when user aspect deviates by > 2x (Cleveland rule).

    Reference baseline: ideal aspect ratio banks median absolute slope to
    45° — approximated here as ``dx/dy_median`` over sorted x values. This
    is a rough geometric estimate; deviations < 2x are ignored.
    """
    findings: list[Finding] = []
    if vtype != "time_series":
        return findings
    spec = envelope.get("spec") or {}
    mark = spec.get("mark")
    mark_str = mark if isinstance(mark, str) else (mark or {}).get("type", "") if isinstance(mark, dict) else ""
    if "line" not in mark_str.lower():
        return findings
    hints = envelope.get("render_hints") or {}
    ar = hints.get("aspect_ratio")
    if not isinstance(ar, (int, float)):
        return findings
    data = (spec.get("data") or {}).get("values") or []
    xs = [row.get("x") for row in data if isinstance(row, dict) and isinstance(row.get("x"), (int, float))]
    ys = [row.get("y") for row in data if isinstance(row, dict) and isinstance(row.get("y"), (int, float))]
    if len(xs) < 2 or len(ys) < 2:
        return findings
    dy = max(ys) - min(ys)
    dx = max(xs) - min(xs)
    if dy <= 0 or dx <= 0:
        return findings
    banked = dx / dy  # 45° target
    if banked <= 0:
        return findings
    if ar / banked > 2.0 or banked / ar > 2.0:
        findings.append(Finding(
            rule="T10",
            severity="Major",
            message=f"aspect_ratio={ar:.2f} deviates >2x from banked-to-45° estimate {banked:.2f}",
            path="render_hints.aspect_ratio",
            suggestion="Set aspect_ratio closer to the dx/dy banking optimum to preserve slope perception.",
        ))
    return findings


def _t15_caption_source_n(envelope: dict, vtype: str) -> list[Finding]:
    """T15 caption+source+n — validator already emits W_MISSING_CAPTION
    for QUANT types at warning severity. Here we elevate to Critical if
    the relation_to_prose is ``visually_native`` (Protocol §7.3: stricter
    on visually-native visuals).

    Phase 7 — attribution resolution mirrors ``_t7_labelling``: a
    non-empty top-level ``envelope.caption`` string satisfies the check.
    Falls back to the legacy ``spec.caption`` object when present (most
    current schemas forbid the object under ``additionalProperties:
    false``). If neither is populated, the finding's path reflects the
    preferred top-level location.
    """
    findings: list[Finding] = []
    if vtype not in QUANT_TYPES:
        return findings
    env_caption = envelope.get("caption")
    if isinstance(env_caption, str) and env_caption.strip():
        return findings
    rel = envelope.get("relation_to_prose", "")
    severity = "Critical" if rel == "visually_native" else "Major"
    spec = envelope.get("spec") or {}
    spec_caption = spec.get("caption")
    if isinstance(spec_caption, dict):
        missing = [k for k in ("source", "period", "n") if not spec_caption.get(k)]
        if not missing:
            return findings
        findings.append(Finding(
            rule="T15",
            severity=severity,
            message=f"caption missing {missing} (relation_to_prose={rel})",
            path="spec.caption",
            suggestion="Populate source, period, and n — required for honest attribution.",
        ))
    else:
        findings.append(Finding(
            rule="T15",
            severity=severity,
            message=f"envelope.caption absent (relation_to_prose={rel})",
            path="envelope.caption",
            suggestion="Populate envelope.caption with source, period, and n — required for honest attribution.",
        ))
    return findings


# ---------------------------------------------------------------------------
# LLM-prior-inversion (§7.5)
# ---------------------------------------------------------------------------

def _inv_template_trap(envelope: dict) -> list[Finding]:
    hits = _template_trap_hits(envelope)
    return [
        Finding(
            rule="inv.template_trap",
            severity="Major",
            message=f"boilerplate string '{val}' found at {path} — likely template regression",
            path=path,
            suggestion="Replace with authored, task-specific text.",
        )
        for path, val in hits
    ]


CAUSAL_FAMILY = {"causal_loop_diagram", "stock_and_flow", "causal_dag", "fishbone"}


def _inv_chart_type(envelope: dict, vtype: str) -> list[Finding]:
    findings: list[Finding] = []
    mode = envelope.get("mode_context", "")
    if "causal_analysis" in mode and vtype not in CAUSAL_FAMILY:
        findings.append(Finding(
            rule="inv.chart_type",
            severity="Major",
            message=f"mode_context='{mode}' suggests CAUSAL family; type='{vtype}' may be misselected",
            path="type",
            suggestion="Consider causal_loop_diagram, causal_dag, or stock_and_flow.",
        ))
    # time-over-time in comparison → prefer time_series
    if vtype == "comparison":
        spec = envelope.get("spec") or {}
        encoding = spec.get("encoding") or {}
        xenc = encoding.get("x") or {}
        if xenc.get("type") == "temporal" or (xenc.get("field", "") or "").lower() in {"date", "time", "year", "month", "week", "day"}:
            findings.append(Finding(
                rule="inv.chart_type",
                severity="Major",
                message="comparison chart with temporal x-axis detected — time_series is more accurate",
                path="type",
                suggestion="Switch type to 'time_series' (preserves banking + small-multiples semantics).",
            ))
    return findings


def _inv_default_settings(envelope: dict, vtype: str) -> list[Finding]:
    findings: list[Finding] = []
    if vtype not in QUANT_TYPES:
        return findings
    spec = envelope.get("spec") or {}
    # Distinguish "config field absent" (fine) from "config is the empty
    # default object" (a passthrough tell). Using dict-membership lets us
    # avoid the truthiness trap where {} == falsy.
    if "config" not in spec:
        return findings
    config = spec["config"]
    if isinstance(config, dict) and len(config) == 0:
        findings.append(Finding(
            rule="inv.default_settings",
            severity="Minor",
            message="spec.config == {} — Vega-Lite default-settings passthrough",
            path="spec.config",
            suggestion="Drop the empty config object or author explicit style choices.",
        ))
    return findings


# ---------------------------------------------------------------------------
# Per-family adversarial checks beyond T-rules
# ---------------------------------------------------------------------------

def _quadrant_axes_dependence(envelope: dict, vtype: str) -> list[Finding]:
    """Major warning when item scatter in a 2x2 shows |pearson r| > 0.7."""
    if vtype != "quadrant_matrix":
        return []
    spec = envelope.get("spec") or {}
    items = spec.get("items") or []
    pts = [(it.get("x"), it.get("y")) for it in items if isinstance(it.get("x"), (int, float)) and isinstance(it.get("y"), (int, float))]
    if len(pts) < 3:
        return []
    xs, ys = zip(*pts)
    r = _pearson(xs, ys)
    if r is None or abs(r) <= 0.7:
        return []
    return [Finding(
        rule="struct.axes_dependent",
        severity="Major",
        message=f"2x2 items show |pearson r|={abs(r):.2f} > 0.7 — axes likely dependent",
        path="spec.items",
        suggestion="Revise axis definitions or provide integrity_declarations.axes_independence_rationale.",
    )]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _numeric_series(spec: dict) -> list[float]:
    data = (spec.get("data") or {}).get("values") or []
    encoding = spec.get("encoding") or {}
    yfield = ((encoding.get("y") or {}).get("field"))
    if not yfield:
        return []
    out = []
    for row in data:
        v = row.get(yfield) if isinstance(row, dict) else None
        if isinstance(v, (int, float)):
            out.append(float(v))
    return out


def _is_length_mark(mark: Any) -> bool:
    if isinstance(mark, str):
        return mark in {"bar", "area", "column"}
    if isinstance(mark, dict):
        return mark.get("type") in {"bar", "area", "column"}
    return False


def _is_bar_or_area(mark: Any) -> bool:
    return _is_length_mark(mark)


def _pearson(xs, ys) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------

def review_envelope(envelope: dict, mode: str | None = None) -> ReviewResult:
    """Adversarial review of an envelope. ``mode`` is the Ora mode
    (e.g. 'systems-dynamics'); if omitted, defaults to
    ``envelope['mode_context']`` or 'standard'.
    """
    if not isinstance(envelope, dict):
        return ReviewResult(blocks=[Finding(rule="envelope", severity="Critical", message="envelope not an object")])

    # Strip _note like the validator does so the adversarial layer is safe
    # against test fixtures.
    if "_note" in envelope:
        envelope = {k: v for k, v in envelope.items() if k != "_note"}

    vtype = envelope.get("type", "")
    effective_mode = mode or envelope.get("mode_context", "") or "standard"

    findings: list[Finding] = []
    findings.extend(_t1_lie_factor(envelope, vtype))
    findings.extend(_t2_zero_baseline(envelope, vtype))
    findings.extend(_t3_dimensional_conformance(envelope, vtype))
    findings.extend(_t5_chartjunk(envelope, vtype))
    findings.extend(_t7_labelling(envelope, vtype))
    findings.extend(_t8_scale_disclosure(envelope, vtype))
    findings.extend(_t10_banking(envelope, vtype))
    findings.extend(_t15_caption_source_n(envelope, vtype))
    findings.extend(_inv_template_trap(envelope))
    findings.extend(_inv_chart_type(envelope, vtype))
    findings.extend(_inv_default_settings(envelope, vtype))
    findings.extend(_quadrant_axes_dependence(envelope, vtype))

    # WP-4.2 — Per-mode structural success criteria.
    # Each rebuilt mode declares structural checks in its SUCCESS
    # CRITERIA section (machine-readable YAML). Implementations live in
    # ``mode_success_criteria`` and return a ``CriterionResult`` list.
    # We convert failed criteria into Major findings (severity is later
    # escalated/demoted per mode strictness in the usual way).
    #
    # S2 (schema validity) is checked by the validator upstream; we skip
    # emitting a finding for it here to avoid double-reporting.
    try:
        from mode_success_criteria import check_structural
        structural_results = check_structural(effective_mode, envelope)
    except Exception as exc:  # defensive — never let the reviewer crash
        structural_results = []
        findings.append(Finding(
            rule="mode_structural_dispatch",
            severity="Minor",
            message=f"per-mode structural check raised: {exc}",
        ))
    for cr in structural_results:
        if cr.passed or cr.id == "S2":
            continue
        findings.append(Finding(
            rule=f"mode_success_criterion_{cr.id}",
            severity="Major",
            message=f"{effective_mode}/{cr.id} failed: {cr.detail or '(no detail)'}",
            path=f"mode/{effective_mode}/success_criteria/structural/{cr.id}",
            suggestion=(
                "See the mode file's SUCCESS CRITERIA section for the "
                "structural requirement this envelope violates."
            ),
        ))

    # Apply per-mode strictness escalation, then bucket.
    result = ReviewResult()
    for f in findings:
        f = Finding(
            rule=f.rule,
            severity=_apply_strictness(f.severity, effective_mode),
            message=f.message,
            path=f.path,
            suggestion=f.suggestion,
        )
        if f.severity == "Critical":
            result.blocks.append(f)
        elif f.severity == "Major":
            result.warns.append(f)
        else:
            result.infos.append(f)
    return result


# ---------------------------------------------------------------------------
# Composition helpers for boot.py
# ---------------------------------------------------------------------------

def process_response(response: str, mode: str | None = None) -> tuple[str, dict]:
    """Pipeline integration helper.

    Finds ``ora-visual`` fenced JSON blocks in ``response``, runs validator
    + adversarial review on each, and returns ``(modified_response,
    diagnostics)``. When a block has a Critical finding, it is **removed**
    from the output (prose remains) and a fallback marker is inserted so
    the client can surface a "figure unavailable" notice per Protocol §8.5.

    ``diagnostics`` is a list of per-block dicts, in response-order, each
    containing ``id``, ``type``, ``blocked``, ``validator`` and
    ``adversarial`` payloads. The ``boot.py`` call site wraps this into
    the response envelope delivered to the client.

    If the response has no ora-visual blocks, this is a no-op and
    ``diagnostics['visuals']`` is an empty list.
    """
    import re

    diagnostics: dict[str, list] = {"visuals": []}

    # Match fenced ora-visual blocks. Greedy until next ``` on its own line.
    pattern = re.compile(r"```ora-visual\s*\n(.*?)\n```", re.DOTALL)

    def replace(match: re.Match) -> str:
        raw = match.group(1)
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError as exc:
            diagnostics["visuals"].append({
                "id": None,
                "type": None,
                "blocked": True,
                "validator": {"valid": False, "errors": [{"code": V_CODES["E_SCHEMA_INVALID"], "message": f"JSON parse failed: {exc}"}]},
                "adversarial": None,
            })
            return "[visual suppressed: parse error]"

        # Lazy import so unit tests don't need schemas available when only
        # exercising adversarial paths.
        from visual_validator import validate_envelope
        vresult = validate_envelope(envelope)
        if not vresult.valid:
            diagnostics["visuals"].append({
                "id": envelope.get("id"),
                "type": envelope.get("type"),
                "blocked": True,
                "validator": vresult.as_dict(),
                "adversarial": None,
            })
            return f"[visual {envelope.get('id','?')} suppressed: schema/structural errors]"

        review = review_envelope(envelope, mode or envelope.get("mode_context"))
        if review.blocks:
            diagnostics["visuals"].append({
                "id": envelope.get("id"),
                "type": envelope.get("type"),
                "blocked": True,
                "validator": vresult.as_dict(),
                "adversarial": review.as_dict(),
            })
            return f"[visual {envelope.get('id','?')} suppressed: adversarial Critical findings]"

        diagnostics["visuals"].append({
            "id": envelope.get("id"),
            "type": envelope.get("type"),
            "blocked": False,
            "validator": vresult.as_dict(),
            "adversarial": review.as_dict(),
        })
        # Emit the block unchanged.
        return match.group(0)

    new_text = pattern.sub(replace, response)
    return new_text, diagnostics


__all__ = [
    "Finding",
    "ReviewResult",
    "review_envelope",
    "process_response",
    "TEMPLATE_TRAP_STRINGS",
]
