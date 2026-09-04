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
import re
from dataclasses import dataclass, field
from typing import Any

from visual_validator import CODES as V_CODES  # reuse shared code names

try:
    import runtime_paths as _rp
except ImportError:  # package import
    from orchestrator import runtime_paths as _rp


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

MODE_CONFIG_PATH = _rp.CONFIG_DIR / "mode-to-visual.json"
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

# Group only complete three-digit runs with one consistent separator. Do not
# join comma-separated lists, line breaks, or a prefix/suffix of malformed groups.
_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_])[-+]?"
    r"(?:(?:(?=\d{1,3}(?P<group>[, \u00a0\u2009\u202f'’]))"
    r"(?<!\d(?P=group))\d{1,3}(?P=group)\d{3}"
    r"(?:(?P=group)\d{3})*(?!\d|(?P=group)\d)|\d+)(?:\.\d+)?|\.\d+)"
    r"(?:[eE][-+]?\d+)?(?:\s*%)?"
)
_NUMBER_TRANSLATION = str.maketrans("", "", ", \t\r\n\u00a0\u2009\u202f'’%")


def _t1_lie_factor(envelope: dict, vtype: str) -> list[Finding]:
    """T1: Tufte's lie factor within [0.95, 1.05].

    The lie factor is the size of the effect SHOWN divided by the size of the
    effect IN THE DATA. On a length-encoded mark a value ``v`` is drawn from
    the axis floor, so it reads as length ``v - lo``. Two values therefore
    *appear* to stand in the ratio ``(v_max - lo) / (v_min - lo)`` while their
    true ratio is ``v_max / v_min``, and::

        lie_factor = ((v_max - lo) / (v_min - lo)) / (v_max / v_min)

    With a zero floor this is exactly 1.0 however the axis is padded. As the
    floor climbs toward the smallest value the ratio inflates without bound —
    which is the truncated-axis deception the rule exists to catch.

    This previously computed ``data_range / domain_range``, which is a
    *fill ratio* — how much of the axis the data happens to span — and is not
    a lie factor at all. It scored the two cases that matter backwards: an
    honest zero-baseline chart with any headroom fell below 0.95 and was
    blocked Critical (data 10–100 on a [0, 100] axis scored 0.900), while the
    textbook truncated axis, fitted snugly to its data, scored exactly 1.000
    and sailed through (data 90–100 on a [90, 100] axis). The escape hatch its
    own suggestion advertised was never read.

    Only exaggeration is reported. A floor below zero understates differences
    rather than overstating them, and zero-baseline policy is T2's job.
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
    if dom_hi <= dom_lo:
        return findings
    # The honest declaration T2 already recognizes covers T1's single cause:
    # a deliberately non-zero floor. The old suggestion text pointed at this
    # field without anything ever reading it.
    if bool((envelope.get("integrity_declarations") or {}).get("non_zero_baseline_justified")):
        return findings
    v_min, v_max = min(data_vals), max(data_vals)
    # Ratio reasoning needs positive magnitudes; diverging/negative series are
    # a different encoding question and are left to T2 and T9.
    if v_min <= 0:
        return findings
    if dom_lo <= 0:
        return findings  # zero (or lower) floor — lie factor is 1.0 by construction
    if v_min <= dom_lo:
        findings.append(Finding(
            rule="T1",
            severity="Critical",
            message=(f"axis floor {dom_lo:g} is at or above the smallest value "
                     f"{v_min:g} — that mark is drawn with no length at all, so "
                     f"the comparison it appears to support cannot be read"),
            path="spec.encoding.y.scale.domain",
            suggestion="Set scale.domain to start at 0, or declare integrity_declarations.non_zero_baseline_justified.",
        ))
        return findings
    shown_ratio = (v_max - dom_lo) / (v_min - dom_lo)
    true_ratio = v_max / v_min
    if true_ratio <= 0:
        return findings
    lie_factor = shown_ratio / true_ratio
    if lie_factor > 1.05:
        findings.append(Finding(
            rule="T1",
            severity="Critical",
            message=(f"lie factor {lie_factor:.3f} exceeds 1.05 — an axis floor of "
                     f"{dom_lo:g} makes {v_max:g} look {shown_ratio:.1f}x "
                     f"{v_min:g} when it is {true_ratio:.1f}x"),
            path="spec.encoding.y.scale.domain",
            suggestion="Set scale.domain to start at 0, or declare integrity_declarations.non_zero_baseline_justified.",
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


def _numeric_grounding(envelope: dict, vtype: str,
                       prose: str | None) -> list[Finding]:
    """Require envelope numbers to be traceable to the accepted prose.

    The envelope is not an independent source of facts: when the terminal
    review has the final prose, every numeric value in a quantitative mark or
    parsed/structural relationship must occur there (with a small
    percent/decimal equivalence for ordinary reporting). Direct callers that
    do not provide prose retain the historical structural-only review.
    """
    if not prose or not vtype or vtype == "annotated_image":
        return []
    values: list[tuple[str, bool]] = []
    structural_keys = {
        "id", "node_id", "edge_id", "source", "target", "from", "to",
        "source_id", "target_id", "parent_id", "semantic_element_id",
        "assistant_visual_id", "generation_revision", "hierarchy_level",
    }

    def collect(value: Any, key: str | None = None) -> None:
        if isinstance(value, bool) or value is None:
            return
        # hierarchy_level is a derived layout field, not a source claim. The
        # concept-map builder computes it from graph depth, so requiring every
        # level integer in the prose would reject grounded native maps.
        if key and key.lower().replace("-", "_") in structural_keys:
            return
        if isinstance(value, (int, float)):
            if isinstance(value, int) or math.isfinite(value):
                values.append((str(value), False))
            return
        if isinstance(value, str):
            # Structural references such as ``node-1`` and ``edge:2`` are
            # identifiers, not numeric claims. Their digits must not make a
            # valid parsed DAG/C4/Mermaid relationship fail grounding.
            if re.fullmatch(r"[A-Za-z_]+[-_:][A-Za-z0-9_.:-]+", value.strip()):
                return
            for match in _NUMBER_RE.finditer(value):
                token = match.group()
                values.append((token.translate(_NUMBER_TRANSLATION),
                               token.rstrip().endswith("%")))
            return
        if isinstance(value, dict):
            for child_key, child in value.items():
                collect(child, str(child_key))
            return
        if isinstance(value, (list, tuple)):
            for child in value:
                collect(child)

    spec = envelope.get("spec") or {}
    if vtype in QUANT_TYPES:
        # Do not treat caption.n or explicit canvas dimensions as plotted
        # facts. Ground the values carried by the data rows, plus the numeric
        # scenario values in a tornado spec.
        if vtype == "tornado":
            collect({
                "base_case_value": spec.get("base_case_value"),
                "parameters": spec.get("parameters") or [],
            })
        else:
            collect((spec.get("data") or {}).get("values") or [])
        # Preserve the original plotted value even when its field name would
        # otherwise be treated as a structural reference. Do not round to float.
        yfield = ((spec.get("encoding") or {}).get("y") or {}).get("field")
        for row in (spec.get("data") or {}).get("values") or []:
            if yfield and isinstance(row, dict):
                collect(row.get(yfield))
    else:
        collect(spec)
    if not values:
        return []

    def norm(value: str, shift: int = 0) -> tuple[int, int, str]:
        # Keep sign, decimal-point position, and significant digits separate.
        # Neither exact comparison nor percent conversion expands the exponent.
        coefficient, _, power = value.lower().partition("e")
        whole, _, fraction = coefficient.lstrip("+-").partition(".")
        digits = "".join(str(int(digit)) for digit in whole + fraction).lstrip("0")
        if not digits:
            return (0, 0, "")
        exponent = 0
        for digit in power.lstrip("+-"):
            exponent = exponent * 10 + int(digit)
        if power.startswith("-"):
            exponent = -exponent
        return (-1 if coefficient.startswith("-") else 1,
                exponent + len(digits) - len(fraction) + shift,
                digits.rstrip("0"))

    prose_numbers = set()
    prose_unmarked_numbers = set()
    prose_percent_numbers = set()
    for match in _NUMBER_RE.finditer(prose):
        token = match.group()
        try:
            value = token.translate(_NUMBER_TRANSLATION)
            number = norm(value)
            prose_numbers.add(number)
            if token.rstrip().endswith("%"):
                prose_percent_numbers.add(number)
                prose_numbers.add(norm(value, -2))
            else:
                prose_unmarked_numbers.add(number)
                if number[0] and number[1] <= 0:
                    prose_numbers.add(norm(value, 2))
        except ValueError:
            continue

    # Explicit percentages must match the original unit: a converted 1250
    # from prose 125000% cannot ground a label claiming 1250%.
    missing = set()
    for value, is_percent in values:
        number = norm(value)
        if is_percent:
            grounded = (number in prose_percent_numbers
                        or norm(value, -2) in prose_unmarked_numbers)
        else:
            grounded = number in prose_numbers
        if not grounded:
            missing.add(value)
    # The compact magnitude order reverses for negatives; zero sorts between
    # the negative and positive values without padding significant digits.
    missing = (sorted((v for v in missing if norm(v)[0] < 0), key=norm, reverse=True)
               + sorted((v for v in missing if norm(v)[0] >= 0), key=norm))
    if not missing:
        return []
    return [Finding(
        rule="grounding.numeric",
        severity="Critical",
        message=("quantitative values " + ", ".join(missing)
                 + " are not present in the accepted prose"),
        path="spec.data.values",
        suggestion="Ground every plotted value in the final prose or omit the unsupported mark.",
    )]


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
# T-rules completed in Phase 2 (T4, T6, T9, T11, T12, T13, T14)
# ---------------------------------------------------------------------------

def _mark_type(spec: dict) -> str:
    mark = spec.get("mark")
    if isinstance(mark, str):
        return mark
    if isinstance(mark, dict):
        return mark.get("type") or ""
    return ""


def _t4_data_ink(envelope: dict, vtype: str) -> list[Finding]:
    """T4: data-ink ratio — decorative non-data ink (drop shadow, gradient fill
    on a data mark). Minor / informational; relaxed under memorability_goal.
    3D extrusion / chartjunk is the harder T5 (Critical)."""
    if vtype not in QUANT_TYPES or envelope.get("memorability_goal"):
        return []
    spec = envelope.get("spec") or {}
    mark = spec.get("mark")
    decorations: list[str] = []
    if isinstance(mark, dict):
        for deco in ("shadow", "dropShadow", "drop_shadow"):
            if mark.get(deco):
                decorations.append(deco)
        for ch in ("fill", "color"):
            val = mark.get(ch)
            if isinstance(val, dict) and "gradient" in val:
                decorations.append(f"mark.{ch}.gradient")
    if not decorations:
        return []
    return [Finding(
        rule="T4", severity="Minor",
        message=f"decorative non-data ink present ({', '.join(decorations)}) — lowers data-ink ratio",
        path="spec.mark",
        suggestion="Drop shadows/gradients on data marks, or set memorability_goal if the embellishment is intentional.",
    )]


def _t6_show_the_data(envelope: dict, vtype: str) -> list[Finding]:
    """T6: show the data. A y-axis aggregate (mean/median/sum) over >20 points
    with no distributional layer hides the spread (Weissgerber). Major."""
    if vtype != "comparison":
        return []
    spec = envelope.get("spec") or {}
    yagg = ((( spec.get("encoding") or {}).get("y") or {}).get("aggregate") or "").lower()
    if yagg not in ("mean", "average", "median", "sum"):
        return []
    data = (spec.get("data") or {}).get("values") or []
    if len(data) <= 20:
        return []
    return [Finding(
        rule="T6", severity="Major",
        message=f"y aggregated by '{yagg}' over {len(data)} points with no distributional layer — hides spread",
        path="spec.encoding.y.aggregate",
        suggestion="Add a box/strip/violin distributional layer, or justify the aggregation.",
    )]


def _t9_axis_orientation(envelope: dict, vtype: str) -> list[Finding]:
    """T9: inverted y-scale on a conventional quantity without an explicit
    integrity declaration. Critical (§7.3)."""
    if vtype not in QUANT_TYPES:
        return []
    spec = envelope.get("spec") or {}
    yscale = (((spec.get("encoding") or {}).get("y") or {}).get("scale") or {})
    inverted = yscale.get("reverse") is True
    dom = yscale.get("domain")
    if (isinstance(dom, list) and len(dom) == 2
            and all(isinstance(x, (int, float)) for x in dom) and dom[0] > dom[1]):
        inverted = True
    if not inverted:
        return []
    if (envelope.get("integrity_declarations") or {}).get("inverted_axis_justified"):
        return []
    return [Finding(
        rule="T9", severity="Critical",
        message="inverted y-axis on a conventional quantity without justification",
        path="spec.encoding.y.scale.reverse",
        suggestion="Remove the inversion or set integrity_declarations.inverted_axis_justified.",
    )]


def _t11_small_multiples(envelope: dict, vtype: str) -> list[Finding]:
    """T11: >=7 categorical colors on a single panel — suggest small multiples
    (facet). Minor / suggestion."""
    if vtype not in QUANT_TYPES:
        return []
    spec = envelope.get("spec") or {}
    enc = spec.get("encoding") or {}
    field = (enc.get("color") or {}).get("field")
    data = (spec.get("data") or {}).get("values") or []
    if not field or not data or enc.get("facet") or "facet" in spec:
        return []
    cats = {row[field] for row in data if isinstance(row, dict) and field in row}
    if len(cats) < 7:
        return []
    return [Finding(
        rule="T11", severity="Minor",
        message=f"{len(cats)} categorical colors on one panel — consider small multiples (facet)",
        path="spec.encoding.color",
        suggestion="Facet into small multiples; >6 colors strain preattentive discrimination.",
    )]


def _t12_currency(envelope: dict, vtype: str) -> list[Finding]:
    """T12: nominal currency on a time series should be real/deflated over
    multi-year spans. Heuristic Minor (fires only when a currency unit is
    declared and no real/deflated note is present)."""
    if vtype != "time_series":
        return []
    spec = envelope.get("spec") or {}
    cap = spec.get("caption") or {}
    units = (cap.get("units") or "") if isinstance(cap, dict) else ""
    blob = " ".join([units, envelope.get("caption") or "", envelope.get("title") or ""]).lower()
    if not any(sym in blob for sym in ("$", "usd", "eur", "gbp", "dollar", "euro", "currency")):
        return []
    if any(w in blob for w in ("real", "deflated", "inflation-adjusted", "constant", "chained")):
        return []
    return [Finding(
        rule="T12", severity="Minor",
        message="nominal currency on a time series — prefer real/deflated values over multi-year spans",
        path="caption.units",
        suggestion="Use inflation-adjusted (real) values or state explicitly that figures are nominal.",
    )]


def _t13_event_labelling(envelope: dict, vtype: str) -> list[Finding]:
    """T13: a long time series with no event annotations. Conservative Minor."""
    if vtype != "time_series":
        return []
    spec = envelope.get("spec") or {}
    data = (spec.get("data") or {}).get("values") or []
    if len(data) < 60:
        return []
    if envelope.get("annotations") or "layer" in spec or "rule" in str(spec.get("mark")):
        return []
    return [Finding(
        rule="T13", severity="Minor",
        message=f"long time series ({len(data)} points) with no event annotations",
        path="spec",
        suggestion="Label major events (rule layers / annotations) so readers can anchor inflections.",
    )]


def _t14_tick_consistency(envelope: dict, vtype: str) -> list[Finding]:
    """T14: non-uniform explicit tick spacing on a linear quantitative axis.
    Minor (log axes excluded — their ticks aren't uniform by design; T8)."""
    if vtype not in QUANT_TYPES:
        return []
    enc = (envelope.get("spec") or {}).get("encoding") or {}
    findings: list[Finding] = []
    for ch in ("x", "y"):
        cdef = enc.get(ch) or {}
        if (cdef.get("scale") or {}).get("type") in ("log", "symlog", "pow"):
            continue
        vals = (cdef.get("axis") or {}).get("values")
        if isinstance(vals, list) and len(vals) >= 3 and all(isinstance(v, (int, float)) for v in vals):
            diffs = {round(vals[i + 1] - vals[i], 9) for i in range(len(vals) - 1)}
            if len(diffs) > 1:
                findings.append(Finding(
                    rule="T14", severity="Minor",
                    message=f"non-uniform tick spacing on {ch}-axis ({vals})",
                    path=f"spec.encoding.{ch}.axis.values",
                    suggestion="Use a constant tick step on linear quantitative axes.",
                ))
    return findings


# ---------------------------------------------------------------------------
# Clarity gates (Phase 2) — catch unclear/empty/redundant emissions that the
# Tufte honesty rules don't cover.
# ---------------------------------------------------------------------------

_PLACEHOLDER_SD = {"", "n/a", "na", "none", "todo", "...", "tbd", "see above", "placeholder"}


def _clarity_semantic_quality(envelope: dict, vtype: str) -> list[Finding]:
    """The four-level semantic_description must be substantive, not placeholder
    or copy-pasted across levels; short_alt follows the Cesal <=150 form."""
    sd = envelope.get("semantic_description")
    if not isinstance(sd, dict):
        return []  # absence is a schema error caught upstream
    findings: list[Finding] = []
    short_alt = (sd.get("short_alt") or "").strip()
    if not short_alt:
        findings.append(Finding(
            rule="clarity.semantic", severity="Major",
            message="semantic_description.short_alt is empty (accessibility)",
            path="semantic_description.short_alt",
            suggestion="Write the Cesal one-liner: '<chart type> of <data>, where <key takeaway>.'",
        ))
    elif len(short_alt) > 150:
        findings.append(Finding(
            rule="clarity.semantic", severity="Minor",
            message=f"short_alt is {len(short_alt)} chars (>150; Cesal one-liner)",
            path="semantic_description.short_alt",
            suggestion="Trim short_alt to <=150 characters.",
        ))
    levels = [(sd.get(k) or "").strip().lower() for k in
              ("level_1_elemental", "level_2_statistical", "level_3_perceptual")]
    if any(lv in _PLACEHOLDER_SD for lv in levels):
        findings.append(Finding(
            rule="clarity.semantic", severity="Minor",
            message="a semantic_description level is placeholder/empty",
            path="semantic_description",
            suggestion="Populate level_1/2/3 with real elemental / statistical / perceptual descriptions.",
        ))
    # Identical non-redundant-guard levels indicate copy-paste.
    redundancy_guard = {"see surrounding prose.", "see surrounding prose"}
    nonempty = [lv for lv in levels if lv and lv not in redundancy_guard]
    if len(nonempty) >= 2 and len(set(nonempty)) == 1:
        findings.append(Finding(
            rule="clarity.semantic", severity="Minor",
            message="semantic_description levels are identical (copy-pasted)",
            path="semantic_description",
            suggestion="Each level serves a distinct purpose — differentiate elemental / statistical / perceptual.",
        ))
    return findings


def _clarity_redundant(envelope: dict, vtype: str) -> list[Finding]:
    """Name a redundant visual as a non-blocking improvement candidate.

    The terminal authority gets one chance to improve it. If that attempt is
    unavailable or still redundant, the already-reviewed visual is accepted;
    strict mode must not turn this clarity preference into a release block.
    """
    if envelope.get("relation_to_prose") == "redundant":
        return [Finding(
            rule="clarity.redundant", severity="Major",
            message="relation_to_prose='redundant' — one improvement attempt is permitted before accepting the visual",
            path="relation_to_prose",
            suggestion="If possible, make the visual carry structure the prose does not; otherwise accept it after one attempt.",
        )]
    return []


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

def review_envelope(envelope: dict, mode: str | None = None,
                    prose: str | None = None) -> ReviewResult:
    """Adversarial review of an envelope. ``mode`` is the Ora mode
    (e.g. 'systems-dynamics'); if omitted, defaults to
    ``envelope['mode_context']`` or 'standard'. ``prose`` is the final
    accepted prose that accompanies the envelope. It is carried through the
    review boundary so grounding checks can compare the envelope with the
    actual deliverable rather than with an intermediate pipeline response.
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
    findings.extend(_numeric_grounding(envelope, vtype, prose))
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
    # Phase 2 — remaining Tufte rules + clarity gates.
    findings.extend(_t4_data_ink(envelope, vtype))
    findings.extend(_t6_show_the_data(envelope, vtype))
    findings.extend(_t9_axis_orientation(envelope, vtype))
    findings.extend(_t11_small_multiples(envelope, vtype))
    findings.extend(_t12_currency(envelope, vtype))
    findings.extend(_t13_event_labelling(envelope, vtype))
    findings.extend(_t14_tick_consistency(envelope, vtype))
    findings.extend(_clarity_semantic_quality(envelope, vtype))
    findings.extend(_clarity_redundant(envelope, vtype))

    # The per-mode structural-criteria hook (mode_success_criteria) was
    # retired 2026-05-10 along with the cascade architecture: the locked
    # 2026-05-01 mode template no longer carries machine-readable SUCCESS
    # CRITERIA YAML. Structural checks are now distributed across the
    # generic T-rules + validator above. If a new per-mode structural-
    # check mechanism is introduced under the new template, it lands here.

    # Apply per-mode strictness escalation, then bucket.
    result = ReviewResult()
    for f in findings:
        # Redundancy is a named, non-blocking exemption. Do not re-escalate it
        # when a strict mode upgrades other Major findings.
        severity = (
            f.severity if f.rule == "clarity.redundant"
            else _apply_strictness(f.severity, effective_mode)
        )
        f = Finding(
            rule=f.rule,
            severity=severity,
            message=f.message,
            path=f.path,
            suggestion=f.suggestion,
        )
        if f.rule == "clarity.redundant":
            result.warns.append(f)
        elif f.severity == "Critical":
            result.blocks.append(f)
        elif f.severity == "Major":
            result.warns.append(f)
        else:
            result.infos.append(f)
    return result


# ---------------------------------------------------------------------------
# Composition helpers for boot.py
# ---------------------------------------------------------------------------

def _try_repair_envelope(envelope: dict, mode: str | None,
                         prose: str | None = None) -> dict | None:
    """Deterministically repair a schema-invalid model envelope: fill the
    mechanical fields, drop schema-forbidden extras, and apply per-type fixes
    (quadrant axes/bounds, QUANT caption, …). Returns the repaired envelope
    (caller re-validates) or ``None`` if it can't be attempted. Fail-open."""
    try:
        vtype = envelope.get("type")
        if not isinstance(vtype, str) or not vtype:
            return None
        from visual_synthesis import autofill
        from visual_recovery import repair_spec
        env = autofill(dict(envelope),
                       mode or envelope.get("mode_context") or "unknown", vtype)
        if not (env.get("title") or "").strip():
            env["title"] = vtype.replace("_", " ").title()
        return repair_spec(env, vtype)
    except Exception:
        return None


def process_response(response: str, mode: str | None = None,
                     prose: str | None = None) -> tuple[str, dict]:
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

    from visual_recovery import ORA_VISUAL_FENCE_RE

    diagnostics: dict[str, list] = {"visuals": []}

    # Canonical fence pattern — see visual_recovery.ORA_VISUAL_FENCE_RE. It
    # refuses to match an unterminated fence, which is what stops this
    # substitution from deleting the prose between a broken block and the
    # next unrelated code fence.
    pattern = ORA_VISUAL_FENCE_RE

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
            # Premium malformed-envelope path: before dropping a schema-invalid
            # block, try a deterministic repair (fill mechanical fields, drop
            # schema-forbidden extras, fix common per-type mistakes). If the
            # repaired envelope passes BOTH schema and adversarial review, emit
            # it instead of suppressing. Only fires on schema failures (never
            # overrides an honesty/adversarial block); fully fail-open.
            repaired = _try_repair_envelope(envelope, mode, prose=prose)
            if repaired is not None:
                rres = validate_envelope(repaired)
                rreview = review_envelope(
                    repaired, mode or repaired.get("mode_context"), prose=prose,
                )
                if rres.valid and not rreview.blocks:
                    diagnostics["visuals"].append({
                        "id": repaired.get("id"),
                        "type": repaired.get("type"),
                        "blocked": False,
                        "repaired": True,
                        "validator": rres.as_dict(),
                        "adversarial": rreview.as_dict(),
                    })
                    return "```ora-visual\n" + json.dumps(repaired, indent=2, ensure_ascii=False) + "\n```"
            diagnostics["visuals"].append({
                "id": envelope.get("id"),
                "type": envelope.get("type"),
                "blocked": True,
                "validator": vresult.as_dict(),
                "adversarial": None,
            })
            return f"[visual {envelope.get('id','?')} suppressed: schema/structural errors]"

        review = review_envelope(
            envelope,
            mode or envelope.get("mode_context"),
            prose=prose,
        )
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


def inspect_response(response: str, mode: str | None = None) -> dict:
    """Observe-only twin of :func:`process_response`.

    Runs the same parse → validator → adversarial evaluation over every
    ``ora-visual`` block and returns the SAME ``diagnostics`` shape, but
    **never mutates the text and never suppresses anything**. Each per-visual
    entry additionally carries ``parse_ok`` (False only when the fenced body
    failed ``json.loads``).

    Used by the Phase-0 emission-telemetry sweep so intermediate pipeline
    steps can be measured without altering analytical output. Kept as a
    parallel implementation (rather than refactoring ``process_response``) so
    the live suppression path stays byte-for-byte unchanged.
    """
    from visual_recovery import ORA_VISUAL_FENCE_RE

    diagnostics: dict[str, list] = {"visuals": []}
    if not response or "ora-visual" not in response:
        return diagnostics

    pattern = ORA_VISUAL_FENCE_RE
    for match in pattern.finditer(response):
        raw = match.group(1)
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError as exc:
            diagnostics["visuals"].append({
                "id": None,
                "type": None,
                "parse_ok": False,
                "blocked": True,
                "validator": {"valid": False, "errors": [{"code": V_CODES["E_SCHEMA_INVALID"], "message": f"JSON parse failed: {exc}"}]},
                "adversarial": None,
            })
            continue

        from visual_validator import validate_envelope
        vresult = validate_envelope(envelope)
        if not vresult.valid:
            diagnostics["visuals"].append({
                "id": envelope.get("id"),
                "type": envelope.get("type"),
                "parse_ok": True,
                "blocked": True,
                "validator": vresult.as_dict(),
                "adversarial": None,
            })
            continue

        review = review_envelope(envelope, mode or envelope.get("mode_context"))
        diagnostics["visuals"].append({
            "id": envelope.get("id"),
            "type": envelope.get("type"),
            "parse_ok": True,
            "blocked": bool(review.blocks),
            "validator": vresult.as_dict(),
            "adversarial": review.as_dict(),
        })
    return diagnostics


__all__ = [
    "Finding",
    "ReviewResult",
    "review_envelope",
    "process_response",
    "inspect_response",
    "TEMPLATE_TRAP_STRINGS",
]
