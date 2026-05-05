"""Oversight router — consumes events, loads context, dispatches actions.

Implements the routing table from Reference — Meta-Layer Architecture §7.
The router is registered as an event handler against ``oversight_events`` so
events emitted by hooks and watchers automatically flow through it.

For each event:
  1. Determine if oversight should fire (per the routing table).
  2. Load the context bundle via oversight_context.
  3. Invoke Process Coherence (Framework — Process Coherence) through
     milestone_executor.execute_framework against the bundled context.
  4. Pass the verdict to oversight_actions for verdict-action dispatch.

For the MVP, Process Coherence invocation is wired but optional — when the
framework file isn't loaded (e.g., during early integration), the router
records the event and the would-be invocation in the audit log without
calling the model. Set ``ORA_OVERSIGHT_LIVE=1`` to enable live model calls.

Author: meta-layer implementation per Reference — Meta-Layer Architecture §7.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional

from oversight_context import (
    OversightContextBundle,
    classify_event,
    load_context,
    PROJECT_LEVEL_EVENTS,
    WORKFLOW_LEVEL_EVENTS,
)


WORKSPACE = os.path.expanduser("~/ora/")
VAULT = os.path.expanduser("~/Documents/vault/")
PROCESS_COHERENCE_PATH = os.path.join(VAULT, "Framework — Process Coherence.md")
ROUTER_LOG_PATH = os.path.join(WORKSPACE, "data/oversight/router.jsonl")


# Mapping from event type to PC mode
EVENT_TO_PC_MODE = {
    # Project-level
    "MilestoneClaimed": "PC-Milestone",
    "FrameworkComplete": "PC-Milestone",
    "MilestoneComplete": "PC-Milestone",  # only when DRIFT_DETECTED
    "MilestoneBlocked": "PC-Block",
    "RedefinitionEvidence": "PC-Redefinition",
    # Workflow-level
    "CorpusSectionPopulated": "PC-Milestone",
    "CorpusValidated": "PC-Milestone",
    "OFFRendered": "PC-Milestone",
    "ChainPropagationRequired": "PC-Milestone",
    "CorpusTemplateVersionChanged": "PC-Milestone",
    # Drift events
    "WorkflowSpecDrift": "PC-Milestone",
}

# Events that don't trigger PC oversight (logged only)
LOG_ONLY_EVENTS = {
    "FrameworkStarted",
    "CorpusInstanceCreated",
}


def should_route_to_oversight(event: dict) -> bool:
    """Return True if this event should fire Process Coherence per §7."""
    et = event.get("event_type", "")

    # Always log-only events
    if et in LOG_ONLY_EVENTS:
        return False

    # Standalone invocation — no project_nexus and no workflow_id → skip
    if not event.get("project_nexus") and not event.get("workflow_id"):
        return False

    # MilestoneComplete only routes when drift was detected
    if et == "MilestoneComplete":
        return event.get("drift_status") == "DRIFT_DETECTED"

    # CorpusSectionPopulated: only route when section has declared schema/cadence
    # (handled in the context loader — if no oversight rules, deliverable is empty)
    # Default: route if there's a workflow_id

    return et in EVENT_TO_PC_MODE


def process_event(event: dict, live: Optional[bool] = None) -> dict:
    """Process a single event. Returns a dict describing the action taken.

    Args:
        event: the event dict.
        live: if True, actually invoke Process Coherence. If False, simulate
            (record the would-be invocation). If None, defer to env var
            ORA_OVERSIGHT_LIVE (default False).

    Returns: action dict with keys {event_type, action, mode, verdict (if any)}.
    """
    if live is None:
        live = os.environ.get("ORA_OVERSIGHT_LIVE") == "1"

    # Fan-out audit records (synthesized by oversight_relationships.notify_parent
    # to surface a child's progress on the parent's PED) are not re-processed —
    # they're already-handled informational records. Skip routing entirely.
    from oversight_relationships import is_fan_out_event
    if is_fan_out_event(event):
        action = {
            "event_type": event.get("event_type", ""),
            "timestamp": _now_iso(),
            "project_nexus": event.get("project_nexus", ""),
            "child_nexus": event.get("child_nexus", ""),
            "action": "fan_out_audit_only",
        }
        _append_router_log(action)
        return action

    et = event.get("event_type", "")
    action: dict = {
        "event_type": et,
        "timestamp": _now_iso(),
        "project_nexus": event.get("project_nexus", ""),
        "workflow_id": event.get("workflow_id", ""),
        "section_id": event.get("section_id", ""),
    }

    if not should_route_to_oversight(event):
        action["action"] = "logged_only"
        _append_router_log(action)
        # Cross-project oversight: even logged-only events fan out to a parent
        # if the source project has one declared.
        _maybe_fan_out_to_parent(event)
        return action

    bundle = load_context(event)
    mode = EVENT_TO_PC_MODE.get(et, "PC-Milestone")
    action["mode"] = mode
    action["context_class"] = bundle.event_class
    action["context_complete"] = bundle.is_complete

    if not bundle.is_complete:
        action["action"] = "context_load_failed"
        action["load_errors"] = bundle.load_errors
        _append_router_log(action)
        return action

    if not live:
        action["action"] = "simulated"
        action["note"] = (
            "Live Process Coherence invocation skipped (set ORA_OVERSIGHT_LIVE=1 to enable). "
            "Bundled context is ready and the framework would be invoked."
        )
        _append_router_log(action)
        _maybe_fan_out_to_parent(event)
        return action

    # Live: invoke Process Coherence
    if not os.path.isfile(PROCESS_COHERENCE_PATH):
        action["action"] = "framework_not_found"
        action["note"] = f"Framework file not found at {PROCESS_COHERENCE_PATH}"
        _append_router_log(action)
        _maybe_fan_out_to_parent(event)
        return action

    verdict = invoke_process_coherence(bundle, mode)
    action["action"] = "invoked"
    action["verdict"] = verdict
    _append_router_log(action)

    # Verdict actions are dispatched separately by oversight_actions
    try:
        from oversight_actions import apply_verdict
        apply_verdict(event=event, bundle=bundle, mode=mode, verdict=verdict)
    except ImportError:
        pass
    except Exception as e:
        print(f"[oversight_router] verdict action failed: {e}")

    _maybe_fan_out_to_parent(event)
    return action


def _maybe_fan_out_to_parent(event: dict):
    """If the source project has a parent declared, surface the event on the
    parent's PED. Best-effort — failures are swallowed so the primary router
    path is unaffected.
    """
    try:
        from oversight_relationships import (
            get_parent_nexus, notify_parent, should_fan_out,
        )
        if not should_fan_out(event):
            return
        child_nexus = event.get("project_nexus", "")
        if not child_nexus:
            return
        parent_nexus = get_parent_nexus(child_nexus)
        if not parent_nexus:
            return
        notify_parent(event, parent_nexus)
    except Exception as e:
        # Cross-project oversight is observational; swallow failures.
        print(f"[oversight_router] fan-out to parent failed: {e}")


def invoke_process_coherence(bundle: OversightContextBundle, mode: str) -> dict:
    """Invoke the Process Coherence framework with the bundled context.

    The bundle is serialized into a structured input for the framework
    pathway; milestone_executor handles the gear pipeline; the verdict is
    parsed from the framework's output.
    """
    from milestone_executor import execute_framework

    framework_input = _bundle_to_framework_input(bundle, mode)

    try:
        result = execute_framework(
            framework_path=PROCESS_COHERENCE_PATH,
            user_input=framework_input,
            project_nexus=None,  # PC's own execution is not itself under oversight
        )
    except Exception as e:
        return {"verdict": "ERROR", "reasoning": f"PC invocation raised: {e}"}

    if not result.success:
        return {
            "verdict": "ERROR",
            "reasoning": result.failure_reason or "PC execution failed",
        }

    return _parse_pc_verdict(result.final_output)


def _bundle_to_framework_input(bundle: OversightContextBundle, mode: str) -> str:
    """Serialize the context bundle as plain-text input for Process Coherence."""
    lines = []
    lines.append(f"# Process Coherence Invocation — Mode: {mode}")
    lines.append("")
    lines.append(f"**Event class:** {bundle.event_class}")
    lines.append(f"**Event type:** {bundle.event.get('event_type', '')}")
    lines.append("")

    if bundle.project_level_locks:
        lines.append("## Project-Level Locked Definitions")
        m = bundle.project_level_locks
        lines.append(f"**Mission Resolution Statement:** {m.get('mission_resolution_statement', '')}")
        lines.append("**Excluded Outcomes:**")
        for o in m.get("excluded_outcomes", []) or []:
            lines.append(f"- {o}")
        lines.append("**Constraints:**")
        for c in m.get("constraints", []) or []:
            lines.append(f"- {c.get('classification')}: {c.get('statement')}")
            if c.get("rationale"):
                lines.append(f"  Rationale: {c['rationale']}")
            if c.get("revisit_trigger"):
                lines.append(f"  Revisit trigger: {c['revisit_trigger']}")
        lines.append("")

    if bundle.workflow_level_locks:
        lines.append("## Workflow-Level Locked Definitions")
        w = bundle.workflow_level_locks
        if "section" in w:
            s = w["section"]
            lines.append(f"**Affected Section:** {s.get('id')} — {s.get('name')}")
            ov = s.get("oversight") or {}
            if ov.get("schema"):
                lines.append(f"  Schema: {ov['schema']}")
            if ov.get("cadence"):
                lines.append(f"  Cadence: {ov['cadence']}")
            if ov.get("cross_section_rules"):
                lines.append("  Cross-section rules:")
                for r in ov["cross_section_rules"]:
                    lines.append(f"    - {r}")
        if "topology" in w:
            lines.append("**Topology:**")
            t = w["topology"]
            for r in t.get("chain_propagation_rules", []):
                lines.append(f"  Chain: {r['source']} → {r['dependent']} ({r['action']} on {r['condition']})")
            for r in t.get("off_dependency_rules", []):
                lines.append(f"  OFF dep: {r['off_id']} reads {r['sections_required']} (stale_threshold={r['stale_threshold_days']}d)")
        lines.append("")

    if bundle.output_contract:
        lines.append("## Output Contract")
        lines.append(bundle.output_contract)
        lines.append("")

    lines.append("## Executing Entity's Claim")
    lines.append(bundle.claim or "(no explicit claim)")
    lines.append("")

    lines.append("## Deliverable")
    lines.append("```")
    lines.append((bundle.deliverable or "")[:8000])
    lines.append("```")
    lines.append("")

    if bundle.framework_chain:
        lines.append("## Current Plan (Framework Chain)")
        for f in bundle.framework_chain:
            if isinstance(f, dict):
                lines.append(f"- {f.get('id', '')}")
            else:
                lines.append(f"- {f}")
        lines.append("")

    if bundle.decision_log_excerpt:
        lines.append("## Project Decision Log (recent entries)")
        for d in bundle.decision_log_excerpt:
            lines.append(f"### {d.get('date', '')}")
            lines.append(d.get("raw_text", ""))
        lines.append("")

    lines.append("## PEF Diagnostic Toolkit Reference")
    lines.append(bundle.pef_toolkit_reference)
    lines.append("")

    return "\n".join(lines)


def _parse_pc_verdict(output: str) -> dict:
    """Parse Process Coherence's output for a verdict line."""
    import re
    verdict = "UNKNOWN"
    reasoning = (output or "").strip()[:1000]

    # Look for explicit verdict markers
    m = re.search(
        r"VERDICT:\s*(PROCEED|REVISE|ESCALATE(?:\s*\(redefinition\))?)",
        output, re.IGNORECASE,
    )
    if m:
        verdict = m.group(1).upper()

    return {"verdict": verdict, "reasoning": reasoning, "raw_output": output[:2000]}


def _append_router_log(entry: dict):
    os.makedirs(os.path.dirname(ROUTER_LOG_PATH), exist_ok=True)
    with open(ROUTER_LOG_PATH, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def install():
    """Register the router as an event handler. Call once during boot."""
    from oversight_events import register_handler
    register_handler(process_event)


# ---------- CLI smoke test ----------

if __name__ == "__main__":
    """Simulate processing of a synthetic event."""
    import sys
    test_event = {
        "event_type": "MilestoneClaimed",
        "project_nexus": sys.argv[1] if len(sys.argv) > 1 else "test_project",
        "milestone_text": "First draft is complete",
        "claimer": "user",
    }
    result = process_event(test_event, live=False)
    print(json.dumps(result, indent=2, default=str))
