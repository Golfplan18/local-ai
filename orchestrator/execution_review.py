"""Execution Review Phase 8 Chunk D — the programmatic (non-terminal) packet record.

`record_program_run` runs the SAME packet-build + declared-lane fill + redaction +
persistence gauntlet that the live gear terminal (`boot._execution_review_terminal`)
runs, but for a programmatic run that never flows through `run_pipeline`/`server`
(e.g. MSI's `invoke_real_gear4` → `boot.run_gear4`).

The load-bearing invariants (spec §16, design §5, ⚖ Rev-3):
- **Signals are FOLDED from the run's OWN tool-event log, never caller-narrated**
  (§16-3). The caller routes the run's events to a per-run trace dir
  (`tool_events.set_turn_context(trace_dir=…)`) and passes that `trace_dir`; the
  fold reads `<trace_dir>/tool-events.jsonl` whole-file via the landed
  `risk_gate.record_route_observed` (the exact terminal path).
- **Evidence lanes are filled ONLY by the registered fillers** — the target repo's
  `standing:true` deploy_probe/render_inspect recipes are routed onto the packet via
  the landed Chunk-C seam (`evidence_contract['lanes']` → `route_lanes` in
  `build_execution_packet`), then `execution_loop.fill_declared_lanes` runs them.
  Never accepts lane verdicts as caller data.
- **`enforcement_model` is caller-MANDATORY, validated, no default** — the honest
  exception the design names (the regime is the integrator's knowledge, not
  derivable from the log); a missing/invalid value REFUSES rather than inheriting a
  false `in_harness` (the P6 TODO in `execution_packet.build_execution_packet`).
- **Caller free-text → `producer_claim`**, rendered last, labeled unverified (§12).
- **Trace-local packet is always written** (`persist_packet` decides the durable
  tier; `write_packet` writes `execution-packet.json`) — a `git_only` /
  `instrumentation:none` run still leaves the trace-local record.

Never raises (returns None on any failure); stealth → no record.
"""
from __future__ import annotations

from typing import Any

try:
    import tool_events as _te
except ImportError:  # pragma: no cover
    from orchestrator import tool_events as _te
try:
    import risk_gate as _rgate
except ImportError:  # pragma: no cover
    from orchestrator import risk_gate as _rgate
try:
    import execution_packet as _ep
except ImportError:  # pragma: no cover
    from orchestrator import execution_packet as _ep
try:
    import execution_persistence as _epersist
except ImportError:  # pragma: no cover
    from orchestrator import execution_persistence as _epersist
try:
    import evidence_runner as _er
except ImportError:  # pragma: no cover
    from orchestrator import evidence_runner as _er


def _mark_failure(err: Exception, where: str) -> None:
    try:
        _te._note_failure(err, f"execution_review_{where}")
    except Exception:
        pass


def _standing_declared_lanes(repo_root: str | None, runner: Any) -> list:
    """The target repo's `standing:true` declared lanes, built from
    `catalog.recipes` directly (`lanes_from_catalog` DROPS `standing`, so its
    output cannot be filtered — judge P3). Empty when no catalog / no standing
    recipe. Never raises."""
    if not repo_root:
        return []
    try:
        cat_path = runner.discover_catalog(repo_root)
        if not cat_path:
            return []
        catalog = runner.parse_catalog(cat_path)
    except Exception as e:
        _mark_failure(e, "catalog")
        return []
    out: list = []
    for name, r in (getattr(catalog, "recipes", None) or {}).items():
        if getattr(r, "standing", False) and getattr(r, "lane", None) \
                and getattr(r, "target", None):
            out.append({"lane": r.lane, "target": r.target, "recipe": name})
    return out


def record_program_run(*, trace_dir: str, output_text: str,
                       enforcement_model: str,
                       repo_root: str | None = None,
                       risk_tier: str | None = None,
                       output_type: str = "execution",
                       producer_claim: str | None = None,
                       stealth: bool = False,
                       runner: Any = None,
                       now_iso: str | None = None) -> str | None:
    """Record a programmatic run's ExecutionPacket. Returns the trace-local packet
    path (or None on stealth / refusal / failure). The run's events MUST already be
    in `<trace_dir>/tool-events.jsonl` (the caller sets a per-run turn context so
    they route there). Never raises."""
    runner = runner or _er
    try:
        if stealth or not trace_dir:
            return None
        # enforcement_model caller-MANDATORY, no default — validated (§7/§5). A
        # missing/invalid value REFUSES rather than inheriting a false in_harness.
        if enforcement_model not in _te.ENFORCEMENT:
            _mark_failure(ValueError(
                f"enforcement_model {enforcement_model!r} not in {sorted(_te.ENFORCEMENT)}"),
                "enforcement_model")
            return None

        # 1. Signals FOLDED from the run's OWN event log (§16-3) — the terminal's
        # exact path: record_route_observed(trace_dir) folds <dir>/tool-events.jsonl
        # whole-file and returns {signals, consistency, output_type, divergence}.
        ro = _rgate.record_route_observed(
            str(trace_dir), risk_tier=risk_tier, output_text=output_text,
            declared_output_type=output_type) or {}
        signals = ro.get("signals") or {}
        # An empty log = disclosed instrumentation blindness (not a caller green).
        instrumentation = "none" if not signals.get("events_scanned") else "observed"

        # 2. The target repo's standing declared lanes → the Chunk-C attach seam
        # (evidence_contract['lanes'] → route_lanes inside build_execution_packet).
        context_pkg: dict = {}
        if repo_root:
            context_pkg["repo_root"] = repo_root
        declared = _standing_declared_lanes(repo_root, runner)
        if declared:
            context_pkg["evidence_contract"] = {"lanes": declared}

        # 3. Build the packet from the folded signals (never terminal-specific).
        packet = _ep.build_execution_packet(
            signals=signals, context_pkg=context_pkg, output_text=output_text,
            risk_tier=risk_tier,
            declared_output_type=ro.get("output_type", output_type),
            consistency=ro.get("consistency"),
            trace_ref=str(trace_dir), now_iso=now_iso)
        if packet is None:
            return None

        # 4. Correct the hardcoded in_harness enforcement_model via the whitelisted
        # override seam; stamp instrumentation + the caller's producer note.
        _ep.populate_loop_fields(
            packet, execution={"enforcement_model": enforcement_model},
            now_iso=now_iso)
        try:
            if isinstance(packet.execution, dict):
                packet.execution["instrumentation"] = instrumentation
                if producer_claim:
                    # Caller free-text → producer_claim.known_limitations (the
                    # summary already carries the shipped prose); rendered last,
                    # labeled unverified (§12). Never a signal, never a lane.
                    pc = dict(packet.execution.get("producer_claim") or {})
                    pc["known_limitations"] = str(producer_claim)[:2000]
                    packet.execution["producer_claim"] = pc
        except Exception as e:
            _mark_failure(e, "stamp")

        # 5. Fill the declared lanes (deploy_probe / render_inspect) — registered
        # fillers only, against the matching standing recipe. No recipe → owed.
        try:
            import execution_loop as _el
        except ImportError:  # pragma: no cover
            from orchestrator import execution_loop as _el
        _el.fill_declared_lanes(packet, context_pkg=context_pkg,
                                trace_dir=trace_dir, stealth=stealth, runner=runner)

        # 6. Persist (durable tier) THEN write the trace-local packet — persist_packet
        # only writes the ledger/note WHEN promoted, so write_packet is what leaves
        # the trace-local execution-packet.json on a git_only / instrumentation:none
        # run (judge P2). set_turn_context (the caller's per-run context) supplies
        # persist's conversation_id.
        try:
            _epersist.persist_packet(
                packet, sig={"max_sensitivity": signals.get("max_sensitivity")},
                trace_dir=trace_dir, stealth=stealth, now_iso=now_iso)
        except Exception as e:
            _mark_failure(e, "persist")
        return _ep.write_packet(packet, trace_dir)
    except Exception as e:
        _mark_failure(e, "record")
        return None
