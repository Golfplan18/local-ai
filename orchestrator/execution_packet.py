"""orchestrator/execution_packet.py — Execution Review Phase 4.

The polymorphic ``ExecutionPacket`` output type + the packet-to-review renderer
(spec §12) + the evaluation-lane router (§5), as ONE consolidated module.

This is **"same downstream machinery, richer output — NOT a second pipeline."**
The packet is a richer *form* of the terminal deliverable, built at the single
run_pipeline / pipeline-stream terminal (``boot.py`` + ``server.py``) — which every
non-hold gear (1/2/3/4 + the bare-model path) flows through — from the already-
folded route signals (``risk_gate.fold_route_observed``) plus the in-gear text-
review verdict threaded on ``context_pkg['execution_review']``. Never a parallel
Gear-3/4. Only ``run_gear3``/``run_gear4`` thread a verdict, so gear-1/2, the gear-3
single-model fallback, and the gear-4 external-consolidation handoff carry an HONEST
null ``text_review_verdict`` (no review gate ran on those paths) — the renderer
omits the text-review line when the verdict is absent.

Phase-4 scope (judge-approved, Architecture A + 4 conditions):
- LIVE at construction: the type, the lane router, and the packet builder run on
  real gear turns; a real packet is built and written TRACE-LOCAL.
- TESTED-BUT-UNWIRED: ``render_for_review`` / ``_format_artifact_for_review`` are
  library functions proven by test — they are NOT installed at the six in-gear
  review sites in P4 (a live packet review is the Phase-6 loop). No live P4
  verifier consumes a packet.
- Evidence lanes are DECLARED-EMPTY (Phase 5's runner fills
  ``generated_by``/``result``/``sufficient``). ``JudgmentLane`` is defined but not
  mass-populated (§5). Every §9 block is RESERVED so later phases fill, not
  retrofit.
- Storage is TRACE-LOCAL only (condition 2): inherits the caller's stealth /
  no-packet behaviour, never a vault or durable store. Phase 7 owns durable tiered
  persistence. ``producer_claim`` may be private, so it lives only where the trace
  already holds the deliverable.
- Ordering (condition 1): ``record_route_observed`` folds ONCE and records
  ``route_observed`` first; the packet is built SEPARATELY from that returned
  signals dict — no double-fold, and NO packet ref is smuggled onto
  ``route_observed``.

Nothing here raises into the pipeline: build/write are best-effort, and a caught
write failure stamps an observable marker (``tool_events._note_failure``) rather
than vanishing silently.
"""

from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ── Provisional constants (flagged per house rule: retunable, not calibrated) ──
_PRODUCER_CLAIM_CAP = 100_000   # producer_claim is trace-local; cap defensively
_TASK_INSTRUCTION_CAP = 20_000
_PACKET_FILENAME = "execution-packet.json"

# output_type enum (provisional names). The RAW declared hint — never rewritten
# from observation (condition 3 / §9 "observed reality overrides").
OUTPUT_TYPE_UNKNOWN = "unknown"
OUTPUT_TYPE_TEXT = "text"
OUTPUT_TYPE_EXECUTION = "execution"


# ── Evaluation lanes (§5) — evidence vs judgment kept STRUCTURALLY separate ────
@dataclass
class EvidenceLane:
    """A mechanical, verifiable lane (§5). Yields a REAL verdict once Phase 5's
    runner fills it. ``sufficient`` is TRI-STATE: ``None`` = unfilled (evidence
    owed, and NOT sufficient), ``True``/``False`` once judged. ``generated_by``
    (§9/§10) records the declared command(s) that produced ``result`` — empty
    until Phase 5, so a lane result ties back to a declared catalog check rather
    than executor self-report."""

    target: str
    lane: str                       # diff_validate | run_observe | render_inspect | deploy_probe | collect_provenance
    generated_by: list[str] = field(default_factory=list)   # §9/§10 — Phase 5 fills
    result: Any = None                                       # Phase 5 fills
    sufficient: bool | None = None                           # tri-state; None = unfilled = NOT sufficient


@dataclass
class JudgmentLane:
    """An interpretive lane (§5). NEVER receives a mechanical verdict — by
    CONSTRUCTION there is no ``verdict``/``sufficient`` field to hold one, so a
    matter of taste can never be dressed up as a passing check."""

    target: str
    critique: str | None = None
    # NB: deliberately NO `verdict` / `sufficient` field (§5 structural separation).


def lane_is_sufficient(lane: EvidenceLane) -> bool:
    """An unfilled lane (``sufficient is None``) is NOT sufficient — evidence owed
    but not produced. Only an explicit ``True`` counts."""
    return getattr(lane, "sufficient", None) is True


def all_evidence_sufficient(lanes: list[EvidenceLane]) -> bool:
    """True only if there is AT LEAST ONE lane and EVERY lane is explicitly
    sufficient. An EMPTY list is NOT 'vacuously passed' (§16-2): no evidence lane
    means nothing was proven, not that everything passed. This is the machine-
    readable analogue of the renderer's 'evidence not yet generated' rule — for
    Phase 5's runner and Phase 6's stop rule that read ``sufficient`` directly."""
    if not lanes:
        return False
    return all(lane_is_sufficient(l) for l in lanes)


# ── The ExecutionPacket (§9) — tier-optional, every block reserved ────────────
@dataclass
class ExecutionPacket:
    """The §9 packet as a Python object. Frontmatter is a flat index
    (``frontmatter()``); large artifacts are REFERENCED (``execution.delta.ref``),
    never inlined. Blocks are tier-optional and reserved even when P4 does not
    populate them, so later phases fill rather than retrofit the type."""

    # --- frontmatter (small, flat, indexable — §9) ---
    task_id: str = ""
    created: str | None = None
    modified: str | None = None
    status: str = "in_progress"                 # in_progress | converged | escalated
    output_type: str = OUTPUT_TYPE_UNKNOWN      # RAW declared hint — NEVER rewritten from observation
    risk_tier: str | None = None
    reversible: bool | None = None
    tags: list[str] = field(default_factory=list)

    # --- body blocks (tier-optional; reserved even when unfilled) ---
    task: dict = field(default_factory=dict)            # instruction / constraints / non_goals
    planning: dict | None = None                        # absent at light; Phase 6 fills (§8)
    execution: dict = field(default_factory=dict)       # enforcement_model / mode / state_* / delta / source_reads / producer_claim
    evidence_lanes: list[EvidenceLane] = field(default_factory=list)
    judgment_lanes: list[JudgmentLane] = field(default_factory=list)
    verification: dict = field(default_factory=dict)    # scoped text-review verdict + reserved confidence/reviewer_a/reviewer_b/findings/invented_tests
    loop: dict | None = None                            # iteration/stop_condition/escalation — reserved, Phase 6
    persistence: dict = field(default_factory=dict)     # tier / redacted — Phase 7
    observed: dict = field(default_factory=dict)        # observed reality-contact character + consistency note (makes "observed overrides" VISIBLE, §9)

    def frontmatter(self) -> dict:
        """Flat, small, indexable metadata ONLY (§9). No nested blob in the header."""
        return {
            "task_id": self.task_id,
            "created": self.created,
            "modified": self.modified,
            "status": self.status,
            "output_type": self.output_type,
            "risk_tier": self.risk_tier,
            "reversible": self.reversible,
            "tags": list(self.tags),
        }

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


# ── The §6 consistency note — record-only, declared-vs-observed (condition 3) ──
def consistency_note(declared_output_type: str | None, signals: dict | None) -> str | None:
    """§6 declared-vs-observed misroute check. RECORD ONLY — never enforced, never
    rewrites the declared hint. Returns a short note or None.

    - declared 'text' but reality-contact observed  → under-review risk.
    - declared 'execution' but neither signal fired → over-heavy.
    Default 'unknown' (P4) yields None on every live turn (the assertion is
    installed + test-covered but dormant until a mode declares ``output_type``)."""
    signals = signals or {}
    dt = declared_output_type or OUTPUT_TYPE_UNKNOWN
    contact = bool(signals.get("any_mutation") or signals.get("source_read_suspected"))
    if dt == OUTPUT_TYPE_TEXT and contact:
        return "declared text, observed reality contact (under-review risk)"
    if dt == OUTPUT_TYPE_EXECUTION and not contact:
        return "declared execution, observed no delta and no source read (over-heavy)"
    return None


# ── The evaluation-lane router (§5) — route by evaluation unit, not whole task ─
def route_lanes(signals: dict | None,
                declared_output_type: str = OUTPUT_TYPE_UNKNOWN,
                mode_meta: dict | None = None,
                declared: list | None = None
                ) -> tuple[list[EvidenceLane], list[JudgmentLane]]:
    """Map the two folded §6 signals onto evidence lanes. Judgment lanes come from
    a mode's declared interpretive targets (``mode_meta['judgment_targets']``) —
    most modes declare none in P4, so ``judgment_lanes`` is normally empty. Evidence
    lanes are DECLARED-EMPTY here (Phase 5 fills the result); an empty result must
    never read as sufficient.

    Phase 8 Chunk C (§4.1): ``declared`` is the Evidence Contract's ``lanes`` block
    (``[{lane, target, recipe}]`` — repo-declared, NOT signal-inferred; deploys are
    declared, spec-aligned). Declared lanes are appended DECLARED-EMPTY, deduped by
    ``(lane, target)`` against the observed lanes and each other."""
    signals = signals or {}
    evidence: list[EvidenceLane] = []
    if signals.get("any_mutation"):
        evidence.append(EvidenceLane(target="state_change", lane="diff_validate"))
    if signals.get("source_read_suspected"):
        evidence.append(EvidenceLane(target="grounded_claims", lane="collect_provenance"))
    seen = {(l.lane, l.target) for l in evidence}
    for d in (declared or []):
        try:
            lane = (d.get("lane") if isinstance(d, dict) else None)
            target = (d.get("target") if isinstance(d, dict) else None)
        except Exception:
            lane, target = None, None
        if not lane or not target:
            continue
        if (lane, target) in seen:
            continue
        seen.add((lane, target))
        evidence.append(EvidenceLane(target=str(target), lane=str(lane)))
    judgment: list[JudgmentLane] = []
    for t in (mode_meta or {}).get("judgment_targets", []) or []:
        if isinstance(t, str) and t.strip():
            judgment.append(JudgmentLane(target=t.strip()))
    return evidence, judgment


# ── The packet-to-review renderer (§12) — evidence FIRST, claim LAST ──────────
# Banner-fence convention (mirrors boot._fenced): syntactically distinct from `#`
# markdown, so it never collides with a body's own headings. Kept local so the
# renderer carries no boot dependency.
def _fence(label: str, body: str) -> str:
    return f"=== {label} ===\n{str(body).strip()}\n=== END {label} ==="


def _render_provenance_lane(l: EvidenceLane, *, durable_summary: bool) -> list[str]:
    """Phase 8 (Chunk A §2.5): render a FILLED collect_provenance lane — the
    only lane whose ``result`` content reaches the review text. Two framing
    rules, both load-bearing:

    - On a MIXED mutation+source-read turn the header is explicitly
      INFORMATIONAL and the bare ``INSUFFICIENT`` token is never emitted —
      otherwise a Level-1 ``sufficient=False`` lane would enter the
      different-family verifier's prompt as a failing check and change
      mutation-turn loop behavior through the prompt, defeating the OQ-4
      stop-rule deferral (judge-approved Rev 4).
    - ``durable_summary=True`` (the escalation-handback render) emits the
      coverage line ONLY — never map rows or excerpts — so lane content
      cannot reach the durable Paused queue through ``render_for_review``
      (the Rev-3 handback-leak blocker fold)."""
    summary = (l.result or {}).get("provenance") if isinstance(l.result, dict) else None
    if not isinstance(summary, dict):
        return []
    cov = summary.get("coverage") or {}
    total = cov.get("claims_total")
    total_str = (str(total) if isinstance(total, int)
                 else f"unknown (Level 1 — {cov.get('claims_examined', 0)} examined)")
    header = ("PROVENANCE (informational — not a convergence input in this phase)"
              if summary.get("mixed_turn") else
              f"PROVENANCE [{'sufficient' if lane_is_sufficient(l) else 'not sufficient'}]")
    lines = [f"{header}: claims_total={total_str}, "
             f"mapped={cov.get('claims_mapped', 0)}, "
             f"supported={cov.get('claims_supported', 0)}, "
             f"unsupported={cov.get('claims_unsupported', 0)}, "
             f"sources={cov.get('sources_total', 0)} "
             f"(used {cov.get('sources_used', 0)}), "
             f"opaque_channels={cov.get('opaque_channels', 0)}, "
             f"missing_timestamps={cov.get('missing_timestamps', 0)}"]
    # §12 honesty: a same-family Level-2 mapper must SAY so wherever its
    # judgments are weighed (pre-check fold — the note was recorded on the
    # lane but never rendered).
    if summary.get("mapper_family"):
        lines.append(f"  mapper family: {summary['mapper_family']}")
    if durable_summary:
        return lines
    for row in summary.get("rows") or []:
        refs = ", ".join(str((r or {}).get("ref") or (r or {}).get("source_id"))
                         for r in (row.get("sources") or [])) or "no source"
        line = (f"  claim {row.get('claim_id')} [{row.get('support_status')}]: "
                f"{row.get('claim_text') or ''} -> {refs}")
        if row.get("excerpt"):
            line += f" | excerpt: {row['excerpt']}"
        lines.append(line)
    if summary.get("rows_truncated"):
        lines.append("  …map rows truncated (full map: provenance-map.json)")
    if cov.get("opaque_channels", 0):
        lines.append("  NOTE: opaque channel(s) contributed — consulted-vs-used "
                     "cannot be verified through an opaque boundary (§17)")
    return lines


# Phase 8 Chunk C (§4): render branches for the two DECLARED lanes. Both mirror
# the provenance branch's two framing rules — an explicitly INFORMATIONAL header
# (never the bare ``INSUFFICIENT`` token that the generic template emits, which
# would drive the different-family verifier on a mixed turn, defeating OQ-4), and
# ``durable_summary=True`` (the escalation-handback render) emits ONLY the verdict
# counts — no refs, reasons, stdout, or rollback free-text (the Rev-3 handback-leak
# rule, generalized to every new lane).
_MAX_PROBE_RENDER_ROWS = 12


def _render_deploy_probe_lane(l: EvidenceLane, *, durable_summary: bool) -> list[str]:
    dp = (l.result or {}).get("deploy_probe")
    if not isinstance(dp, dict):
        return []
    counts = dp.get("verdict_counts") or {}
    state = "sufficient" if getattr(l, "sufficient", None) else "not sufficient"
    lines = [f"DEPLOY PROBE (informational — not a convergence input in this "
             f"phase) [{state}]",
             f"  probes: PASS={counts.get('PASS', 0)} FAIL={counts.get('FAIL', 0)}"
             f" INDETERMINATE={counts.get('INDETERMINATE', 0)}"]
    if durable_summary:
        return lines                      # counts only — no refs/reasons/rollback
    for r in (dp.get("probes") or [])[:_MAX_PROBE_RENDER_ROWS]:
        lines.append(f"  - {r.get('kind')} [{r.get('verdict')}] "
                     f"{r.get('ref') or ''} — {r.get('reason') or ''}")
    if dp.get("probes_truncated"):
        lines.append("  …probes truncated")
    lines.append(f"  rollback: {dp.get('rollback')}")
    return lines


def _render_render_inspect_lane(l: EvidenceLane, *, durable_summary: bool) -> list[str]:
    ri = (l.result or {}).get("render_inspect")
    if not isinstance(ri, dict):
        return []
    state = "sufficient" if getattr(l, "sufficient", None) else "not sufficient"
    lines = [f"RENDER INSPECT (informational — not a convergence input in this "
             f"phase) [{state}]",
             f"  check: {ri.get('check')}"]
    if durable_summary:
        return lines
    for c in (ri.get("checks") or []):
        outcome = ("passed" if c.get("passed")
                   else ("skipped" if c.get("skipped") else "failed"))
        lines.append(f"  - {c.get('name')}: {outcome}"
                     + (f" ({c.get('skip_reason')})" if c.get("skip_reason") else ""))
    return lines


def _render_evidence(packet: ExecutionPacket, *, durable_summary: bool = False) -> str:
    obs = packet.observed or {}
    lines: list[str] = []
    if obs.get("any_mutation"):
        ref = ((packet.execution or {}).get("delta") or {}).get("ref") or "n/a"
        lines.append(f"WHAT CHANGED: mutation observed "
                     f"(max_mutability={obs.get('max_mutability', '?')}); delta ref: {ref}")
    else:
        lines.append("WHAT CHANGED: no mutation observed")
    if obs.get("source_read_suspected"):
        chans = ", ".join(obs.get("source_read_channels") or []) or "unspecified"
        lines.append(f"WHAT WAS READ AS A SOURCE: suspected (channels: {chans})")
    else:
        lines.append("WHAT WAS READ AS A SOURCE: none suspected")
    if packet.evidence_lanes:
        for l in packet.evidence_lanes:
            # Phase 8: a FILLED provenance / deploy_probe / render_inspect lane
            # renders its own INFORMATIONAL block — the generic template's bare
            # INSUFFICIENT token must never speak for it (it would drive the
            # different-family verifier on a mixed turn, defeating OQ-4). An
            # UNFILLED lane (sufficient None) falls through to the owed template.
            lname = getattr(l, "lane", None)
            filled = getattr(l, "sufficient", None) is not None
            if filled:
                branch = None
                if lname == "collect_provenance":
                    branch = _render_provenance_lane(l, durable_summary=durable_summary)
                elif lname == "deploy_probe":
                    branch = _render_deploy_probe_lane(l, durable_summary=durable_summary)
                elif lname == "render_inspect":
                    branch = _render_render_inspect_lane(l, durable_summary=durable_summary)
                if branch:
                    lines.extend(branch)
                    continue
            if not lane_is_sufficient(l):
                # Covers the tri-state unfilled (None) AND an explicit False.
                state = ("evidence not yet generated (owed, not sufficient)"
                         if getattr(l, "sufficient", None) is None
                         else "INSUFFICIENT")
                lines.append(f"EVIDENCE LANE [{l.lane} -> {l.target}]: {state}")
            else:
                by = ", ".join(l.generated_by) or "n/a"
                lines.append(f"EVIDENCE LANE [{l.lane} -> {l.target}]: sufficient (via {by})")
    else:
        lines.append("EVIDENCE LANES: none (degrades to plain text review)")
    note = obs.get("consistency")
    if note:
        lines.append(f"CONSISTENCY: {note}")
    return "\n".join(lines)


def render_for_review(packet: ExecutionPacket, *, durable_summary: bool = False) -> str:
    """§12 packet-to-review renderer: mechanical evidence FIRST, producer claim
    LAST (labeled an unverified claim). Physically enforces "evidence over claims"
    — a fluent claim can't out-argue a failing check because the reviewer meets the
    evidence first and the claim explicitly framed as unverified.

    ``durable_summary=True`` (Phase 8, the escalation-handback render): lane
    RESULT content is suppressed — the provenance block emits its coverage
    line only, never map rows or excerpts — because the handback rides a
    durable queue and bypasses ``redact_for_durable`` (Rev-3 blocker fold)."""
    parts: list[str] = []

    # 1. Task + acceptance criteria — or a LOUD absence (never a silent omission).
    task = packet.task or {}
    instruction = (task.get("instruction") or "").strip()
    if instruction:
        parts.append(_fence("TASK", instruction))
    criteria = ((packet.planning or {}).get("converged_brief") or {}).get("acceptance_criteria")
    if criteria:
        body = criteria if isinstance(criteria, str) else "\n".join(str(c) for c in criteria)
        parts.append(_fence("ACCEPTANCE CRITERIA", body))
    else:
        parts.append(_fence(
            "NO ACCEPTANCE CRITERIA DECLARED — evidence cannot be judged sufficient against a setpoint",
            "No planning stage set acceptance criteria for this task; do not treat the "
            "producer claim below as validated against a standard."))

    # 2. Mechanical evidence FIRST.
    parts.append(_fence("OBSERVED EVIDENCE",
                        _render_evidence(packet, durable_summary=durable_summary)))
    # The in-gear verdict renders as a SCOPED text-review line — never an
    # unqualified green check that could be read as covering the mechanical
    # evidence it never saw.
    tv = (packet.verification or {}).get("text_review_verdict")
    tstatus = (packet.verification or {}).get("status")
    if tv:
        parts.append(_fence(
            "TEXT-REVIEW VERDICT (does not cover state changes or provenance)",
            str(tv)))
    elif tstatus:
        # No valid verdict describes the shipped text (e.g. a FAIL redo produced a
        # new unreviewed deliverable) — surface the scoped status loudly so the
        # producer claim is never read as text-reviewed.
        parts.append(_fence(
            "TEXT-REVIEW STATUS (no verdict covers the shipped text)",
            str(tstatus)))

    # 3. Producer claim LAST, labeled unverified.
    claim = (packet.execution or {}).get("producer_claim") or {}
    claim_text = claim.get("summary") if isinstance(claim, dict) else str(claim)
    parts.append(_fence(
        "UNVERIFIED PRODUCER CLAIM (weigh against the evidence above; do not treat as established)",
        (claim_text or "").strip()))
    return "\n".join(parts)


def _format_artifact_for_review(artifact: Any) -> Any:
    """Polymorphic seam (LIBRARY function — NOT installed at the six in-gear review
    sites in P4). A ``str`` is returned UNCHANGED with ZERO side effects (no
    logging, no fold, no packet attempt): this is what keeps text review byte-
    identical and makes ``msi_run_gear4.invoke_real_gear4`` (the one live path that
    would route through this if it were ever wired) provably unaffected. An
    ``ExecutionPacket`` is rendered evidence-first."""
    if isinstance(artifact, ExecutionPacket):
        return render_for_review(artifact)
    return artifact


# ── Construction (condition 1: from ALREADY-folded signals) + write (2/4) ─────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mark_failure(err: Exception, where: str) -> None:
    """Stamp an OBSERVABLE marker for a caught packet build/write failure via
    ``tool_events._note_failure`` (Rev 1). A construction/write exception must be
    distinguishable from an INTENTIONAL skip (no trace dir / empty output / no
    signals), which returns None WITHOUT a marker. This helper itself never raises,
    so surfacing the failure can never interrupt the user's deliverable."""
    try:
        try:
            import tool_events as _te
        except ImportError:  # pragma: no cover
            from orchestrator import tool_events as _te
        _te._note_failure(err, where)
    except Exception:
        pass


def build_execution_packet(*, signals: dict | None, context_pkg: dict | None = None,
                           output_text: str | None = None, risk_tier: str | None = None,
                           declared_output_type: str = OUTPUT_TYPE_UNKNOWN,
                           consistency: str | None = None, trace_ref: str | None = None,
                           now_iso: str | None = None) -> ExecutionPacket | None:
    """Build the packet from the ALREADY-folded ``signals`` (single fold —
    condition 1) plus the text-review verdict threaded on
    ``context_pkg['execution_review']`` (condition 4). NEVER raises — returns an
    ``ExecutionPacket`` or ``None``. Writes nothing (see ``write_packet``)."""
    try:
        context_pkg = context_pkg or {}
        signals = signals or {}
        now_iso = now_iso or _now_iso()
        er = context_pkg.get("execution_review") or {}

        # verification — SCOPED text-review verdict LABEL only. No raw verifier
        # text is copied in (condition 4: avoid leaking verifier prose; large
        # artifacts referenced/capped, not blindly copied). confidence /
        # reviewer_a / reviewer_b / findings / invented_tests reserved (§12, Phase 6).
        verification = {
            "text_review_verdict": er.get("verdict"),          # PASS | FAIL | BROKEN | None
            "scope": "text_review — does not cover state changes or provenance",
            # `status` records a scoped condition where a verdict does not describe
            # the shipped text — e.g. a gear-3 FAIL redo that produced a NEW
            # unreviewed deliverable (Rev 1). No raw verifier text rides here.
            "status": er.get("status"),
            "reviewer_a": None, "reviewer_b": None, "confidence": None,
            "findings": [], "invented_tests": [],
        }

        # execution block. enforcement_model is honest for a core in-harness gear
        # run; orchestrated / opaque-shell / MSI-custom paths that later produce a
        # packet MUST set it correctly (§7 — TODO owned by the P6 enumeration),
        # never inherit a blanket in_harness.
        producer = output_text or ""
        if len(producer) > _PRODUCER_CLAIM_CAP:
            producer = producer[:_PRODUCER_CLAIM_CAP] + "\n…[capped]"
        execution = {
            "enforcement_model": "in_harness",
            "mode": None, "state_before": None, "state_after": None,   # §11 reserved (Phase 5)
            "delta": {"any_mutation": bool(signals.get("any_mutation")),
                      "max_mutability": signals.get("max_mutability", "read"),
                      "ref": trace_ref},
            "source_reads": signals.get("source_candidate_reads") or [],  # already public-safe (Phase 3)
            "producer_claim": {"summary": producer, "known_limitations": None},
        }

        # observed reality-contact character — makes "observed reality overrides"
        # (§9) VISIBLE in the packet rather than an assertion made only in the note.
        observed = {
            "any_mutation": bool(signals.get("any_mutation")),
            "max_mutability": signals.get("max_mutability", "read"),
            "source_read_suspected": bool(signals.get("source_read_suspected")),
            "source_read_channels": signals.get("source_read_channels") or [],
            "consistency": consistency,
        }

        # Phase 8 Chunk C: DECLARED lanes come from the Evidence Contract's
        # ``lanes`` block (repo-declared at planning; the model cannot invent one
        # — the recipe body is the §6-protected catalog file). Absent/empty on
        # every turn whose catalog declares no recipes (incl. all live ora turns).
        _contract = context_pkg.get("evidence_contract") or {}
        _declared = _contract.get("lanes") if isinstance(_contract, dict) else None
        evidence_lanes, judgment_lanes = route_lanes(
            signals, declared_output_type, context_pkg.get("mode_meta"),
            declared=_declared)

        instruction = (context_pkg.get("raw_prompt")
                       or context_pkg.get("cleaned_prompt") or "")
        if len(instruction) > _TASK_INSTRUCTION_CAP:
            instruction = instruction[:_TASK_INSTRUCTION_CAP] + "…[capped]"

        return ExecutionPacket(
            task_id=str(context_pkg.get("task_id")
                        or context_pkg.get("conversation_id") or ""),
            created=now_iso, modified=now_iso,
            output_type=(declared_output_type or OUTPUT_TYPE_UNKNOWN),  # RAW hint, never from observation
            risk_tier=risk_tier,
            # §9 `reversible` gates whether POST-HOC ROUTING is allowed (§6): it is
            # permitted "inside reversible tiers only", and the only NON-reversible
            # tier is `irreversible` (light/standard/high-risk are all reversible —
            # high-risk carries a rollback check, §8). So this is the tier-boundary
            # flag, NOT a consequence measure; high-risk == reversible is correct.
            reversible=(risk_tier != "irreversible") if risk_tier else None,
            task={"instruction": instruction, "constraints": None, "non_goals": None},
            planning=None,
            execution=execution,
            evidence_lanes=evidence_lanes,
            judgment_lanes=judgment_lanes,
            verification=verification,
            loop=None,
            # §14 default is the CHEAPEST tier ("do not default to durable"); Phase-7
            # execution_persistence.persist_packet recomputes/promotes at the loop terminal
            # (before write_packet, so the trace JSON records the final tier). "trace_local" was
            # the Phase-4 placeholder — not one of the three §14 tiers.
            persistence={"tier": "git_only", "redacted": None},
            observed=observed,
        )
    except Exception as e:
        # Rev 1: a caught BUILD exception (e.g. a malformed context_pkg / signals)
        # must be OBSERVABLE, not a silent None — otherwise a construction bug is
        # indistinguishable from a turn that legitimately had no packet.
        _mark_failure(e, "execution_packet_construct")
        return None


def write_packet(packet: ExecutionPacket | None, trace_dir: str | None) -> str | None:
    """Write the packet TRACE-LOCAL only (condition 2): inherits the trace's
    retention + stealth handling, never a vault or durable store (Phase 7 owns
    durable persistence). Best-effort; returns the path ref or None. A caught
    failure stamps an OBSERVABLE marker (``tool_events._note_failure``) so a crash
    is distinguishable from a legitimately-absent packet."""
    if packet is None or not trace_dir:
        return None
    try:
        os.makedirs(str(trace_dir), exist_ok=True)
        path = os.path.join(str(trace_dir), _PACKET_FILENAME)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(packet.to_dict(), f, default=str, indent=2)
        return path
    except Exception as e:
        _mark_failure(e, "execution_packet_write")
        return None


# ── Phase 6: fill the reserved §9 loop / verification / execution blocks ───────
def planning_block_from_context(context_pkg: dict | None, *,
                                planner_a: Any = None, planner_b: Any = None,
                                approach: str | None = None) -> dict:
    """Thread the planning-stage acceptance criteria + Evidence Contract from
    ``context_pkg`` (set by ``risk_gate.apply_criteria`` +
    ``evidence_runner.apply_evidence_contract`` at the live planning seam) into the
    §9 ``planning`` block the renderer reads (``converged_brief.acceptance_criteria``,
    ``evidence_contract``). ``planner_a``/``planner_b`` are references (dual at
    high-risk/irreversible — §8). Returns a dict; NEVER None — at ``light`` the
    caller passes ``planning=None`` to ``populate_loop_fields`` instead (§9 tier-
    optional: a light packet legitimately has no planning block)."""
    context_pkg = context_pkg or {}
    return {
        "planner_a": planner_a,
        "planner_b": planner_b,
        "converged_brief": {
            "approach": approach,
            "acceptance_criteria": context_pkg.get("acceptance_criteria"),
            "known_risks": None,
            "review_questions": None,
        },
        "evidence_contract": context_pkg.get("evidence_contract"),
    }


def populate_loop_fields(packet: ExecutionPacket | None, *,
                         planning: dict | None = None,
                         verification: dict | None = None,
                         execution: dict | None = None,
                         loop: dict | None = None,
                         now_iso: str | None = None) -> ExecutionPacket | None:
    """Phase 6: FILL (not retrofit) the §9 blocks Phase 4 reserved on a packet
    already built by ``build_execution_packet`` — ``planning``,
    ``verification.reviewer_a``/``reviewer_b``/``findings``/``invented_tests``/
    ``confidence``, ``execution.mode``/``state_before``/``state_after``/
    ``enforcement_model``, and ``loop.*``. It runs ONLY on the non-self-evidencing
    loop path, so ``build_execution_packet`` stays byte-compatible for the common
    self-evidencing turn. Additive + merge-in-place; NEVER raises; returns the packet.

    Invariants held here (do NOT weaken):
    - The ``reversible`` frontmatter flag is NOT recomputed — it is the §6 tier-
      boundary gate set at build time (high-risk == ``reversible: true`` is spec-
      correct; §8 gives high-risk a rollback check, not irreversibility).
    - The Phase-4 scoped ``text_review_verdict``/``scope``/``status`` on
      ``verification`` are PRESERVED (the judgment-lane review, §5) — the Phase-6
      execution-review verify fields layer ON TOP, never clobber them.
    - The Phase-4 ``execution.delta``/``source_reads``/``producer_claim`` are
      PRESERVED — Phase 6 owns only ``mode``/``state_*``/``enforcement_model`` (§11/§7).
    - ``planning`` stays ``None`` at ``light`` (§9 tier-optional — correct, not
      incomplete); the renderer then fires its LOUD absence fence."""
    if packet is None:
        return None
    try:
        if planning is not None:
            packet.planning = planning
        if verification:
            merged_v = dict(packet.verification or {})
            merged_v.update(verification)   # layer P6 fields over the P4 text-review scope
            packet.verification = merged_v
        if execution:
            merged_e = dict(packet.execution or {})
            # ONLY the §11/§7 fields Phase 6 owns — never touch the Phase-4
            # delta / source_reads / producer_claim built from the observed
            # signals. Phase 8 Chunk B adds its isolated-run observability
            # fields to the whitelist (the Rev-3 critic flagged that a key
            # not listed here is silently DROPPED by this merge).
            for k in ("mode", "state_before", "state_after", "enforcement_model",
                      "isolated_checks", "delta_attribution"):
                if k in execution:
                    merged_e[k] = execution[k]
            packet.execution = merged_e
        if loop is not None:
            packet.loop = loop
            sc = (loop or {}).get("stop_condition")
            if sc == "criteria_met":
                packet.status = "converged"
            elif sc == "max_iterations_escalated":
                packet.status = "escalated"
        packet.modified = now_iso or _now_iso()
        return packet
    except Exception as e:
        _mark_failure(e, "execution_packet_populate_loop")
        return packet


def construct_and_write(*, signals: dict | None, context_pkg: dict | None,
                        output_text: str | None, risk_tier: str | None,
                        declared_output_type: str = OUTPUT_TYPE_UNKNOWN,
                        consistency: str | None = None,
                        trace_dir: str | None = None,
                        now_iso: str | None = None) -> str | None:
    """Terminal one-liner: build + write trace-local, guarded. Returns the path ref
    or None. NEVER raises. Constructs a packet ONLY when there is a real deliverable
    AND a trace dir to hold it — no packet on holds / empty output, and no new
    runtime store is invented when tracing is off (condition 2). The caller gates
    on stealth (stealth turns get no packet, inheriting the Phase-1/2/3 model)."""
    try:
        if not trace_dir:
            return None
        if not (output_text and str(output_text).strip()):
            return None
        # A packet describes a turn's observed reality-contact; only write one when
        # the fold that describes it actually produced a signals dict. `signals is
        # None` is unreachable today (fold_route_observed never returns None), but
        # the guard keeps "packet ⇒ successful fold" true if that ever changes,
        # rather than emitting an all-False packet that reads as a no-contact turn.
        if signals is None:
            return None
        pkt = build_execution_packet(
            signals=signals, context_pkg=context_pkg, output_text=output_text,
            risk_tier=risk_tier, declared_output_type=declared_output_type,
            consistency=consistency, trace_ref=str(trace_dir), now_iso=now_iso)
        return write_packet(pkt, trace_dir)
    except Exception as e:
        # Belt: build_execution_packet + write_packet catch (and mark) their own
        # failures, so this fires only on an unexpected error in this wrapper — mark
        # it too, distinctly, so it is never a silent None.
        _mark_failure(e, "execution_packet_construct_and_write")
        return None
