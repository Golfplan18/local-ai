"""Milestone executor — runs a framework as a sequence of milestone-bounded
gear pipeline passes with drift detection at each boundary.

Implements the layered execution model declared in Process Formalization
Framework v2.1 §2.3. For each milestone in declared order:

  1. Assemble a structured handoff packet containing the user's original
     input, prior milestone deliverables from scratch, the layer
     instructions for this milestone's covered layers, the milestone's
     output specification, verification criterion, and drift check question.
  2. Run the milestone through the gear pipeline (default Gear 4) — this
     IS the adversarial review machinery; no extra wiring needed.
  3. Save the reviewed deliverable to scratch.
  4. Run a drift check: ask the milestone's drift_check_question against
     the deliverable + original user input; surface any DRIFT_DETECTED.
  5. On exception, retry up to 3 times. On 3rd failure, mark the scratch
     session failed and raise.

Phase A.5 cleanup and mode classification are bypassed entirely between
milestones — milestone handoffs are framework-generated and already clean.

Single-mode frameworks (DRP-style) are the MVP target. Multi-mode
frameworks with M0 routing are recognized but their routing logic is
not yet wired in (an executor TODO).
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Optional

# Ensure orchestrator is on the path for direct invocation
_ORCH_DIR = os.path.dirname(os.path.abspath(__file__))
if _ORCH_DIR not in sys.path:
    sys.path.insert(0, _ORCH_DIR)

from framework_parser import (
    Framework,
    Milestone,
    parse_framework_file,
    FrameworkParseError,
)
from scratch import ScratchSession


MAX_RETRIES = 3
DRIFT_CHECK_SLOT = "sidebar"  # small model, cheap
MODE_SELECT_SLOT = "sidebar"  # routing classifier; small model is sufficient

# Mechanical modes are runtime-handled, not model-driven. Routing one through
# /framework would otherwise produce model hallucination of an artifact rather
# than actually creating a file. Instead we short-circuit and return a
# redirect notice pointing at the matching slash command.
MECHANICAL_MODE_REDIRECTS = {
    "C-Instance": "/instance <template> <period> [<instance-dir>]",
    "C-Validate": "/validate <instance> [<template>]",
    "O-Render": "/render <off-spec> <instance> [<output-dir>]",
}


# ---------- Result types ----------

@dataclass
class MilestoneResult:
    milestone_id: str
    name: str
    deliverable: str
    drift_status: str  # "IN_SCOPE", "DRIFT_DETECTED", or "DRIFT_CHECK_SKIPPED"
    drift_reasoning: str
    attempts: int


@dataclass
class FrameworkExecutionResult:
    framework_name: str
    execution_id: str
    user_input: str
    milestones: list[MilestoneResult]
    final_output: str
    success: bool
    failure_reason: Optional[str] = None
    duration_seconds: float = 0.0
    mode: str = "all"             # "all" for single-mode; mode name for multi-mode
    mode_reasoning: str = ""       # how the mode was selected (for transparency)


class MilestoneExecutionError(Exception):
    """Raised when a milestone fails after MAX_RETRIES attempts."""
    pass


# ---------- Public API ----------

def execute_framework(
    framework_path: str,
    user_input: str,
    config: Optional[dict] = None,
    execution_id: Optional[str] = None,
    project_nexus: Optional[str] = None,
) -> FrameworkExecutionResult:
    """Execute a framework on the given user input.

    Returns a FrameworkExecutionResult. On success, scratch is cleaned up.
    On failure, scratch is preserved for inspection or resume.

    Multi-mode frameworks (PEF, MOM, Process Formalization, etc.): the
    executor calls ``select_mode`` to choose which mode to run, then
    executes only that mode's declared milestones. Selection priority:
    explicit prefix in user input → mode name mentioned in user input →
    LLM-based routing classifier → first declared mode. The chosen mode
    and the reasoning are recorded on the result and emitted with the
    oversight events.

    project_nexus: optional. When set, framework-level oversight events
    are emitted with the project context for the meta-layer's Layer B
    routing (see Reference — Meta-Layer Architecture). When None, events
    fire with project_nexus=None and the oversight router filters them out.
    """
    # Lazy import of boot.py to avoid circular issues during testing
    from boot import load_endpoints

    # Lazy import of oversight events — keeps the executor usable
    # standalone when no oversight infrastructure is loaded.
    try:
        from oversight_events import emit as emit_oversight_event
    except ImportError:
        def emit_oversight_event(_evt):  # type: ignore
            return None

    if config is None:
        config = load_endpoints()

    fw = parse_framework_file(framework_path)

    if fw.is_multi_mode:
        selected_mode, mode_reasoning, effective_input = select_mode(
            fw, user_input, config
        )
        milestones = fw.milestones_by_mode.get(selected_mode, [])
        if not milestones:
            raise FrameworkParseError(
                f"Framework {fw.name!r} has no milestones declared for mode "
                f"{selected_mode!r}."
            )
        # Mechanical-mode redirect — short-circuit before scratch / model calls.
        if selected_mode in MECHANICAL_MODE_REDIRECTS:
            return _build_mechanical_redirect(
                fw, selected_mode, mode_reasoning, effective_input,
                execution_id=execution_id,
            )
    else:
        selected_mode = "all"
        mode_reasoning = "single-mode framework"
        effective_input = user_input
        milestones = fw.milestones_by_mode.get("all", [])
        if not milestones:
            raise FrameworkParseError(
                f"Framework {fw.name!r} declared no milestones to execute."
            )

    scratch = ScratchSession.create(fw.name, execution_id=execution_id)
    started = time.time()
    results: list[MilestoneResult] = []

    # ---- Oversight hook: FrameworkStarted ----
    emit_oversight_event({
        "event_type": "FrameworkStarted",
        "framework_id": fw.name,
        "mode": selected_mode,
        "mode_reasoning": mode_reasoning,
        "execution_id": scratch.execution_id,
        "project_nexus": project_nexus,
        "user_input": effective_input,
    })

    try:
        for milestone in milestones:
            result = _run_milestone(fw, milestone, scratch, effective_input, config)
            results.append(result)

            # ---- Oversight hook: MilestoneComplete ----
            emit_oversight_event({
                "event_type": "MilestoneComplete",
                "framework_id": fw.name,
                "mode": selected_mode,
                "execution_id": scratch.execution_id,
                "milestone_id": milestone.id,
                "milestone_name": milestone.name,
                "deliverable_path": str(getattr(scratch, "session_dir", "")),
                "drift_status": result.drift_status,
                "drift_reasoning": result.drift_reasoning,
                "project_nexus": project_nexus,
            })

            if result.drift_status == "DRIFT_DETECTED":
                # MVP behavior: log and continue. Future: pause / surface.
                # Drift is recorded in result.drift_reasoning.
                pass

        # Final output = last milestone's deliverable
        final_output = results[-1].deliverable if results else ""
        scratch.mark_complete()

        # ---- Oversight hook: FrameworkComplete (success) ----
        emit_oversight_event({
            "event_type": "FrameworkComplete",
            "framework_id": fw.name,
            "mode": selected_mode,
            "execution_id": scratch.execution_id,
            "final_output_path": str(getattr(scratch, "session_dir", "")),
            "milestones": [
                {
                    "milestone_id": r.milestone_id,
                    "name": r.name,
                    "drift_status": r.drift_status,
                    "attempts": r.attempts,
                }
                for r in results
            ],
            "project_nexus": project_nexus,
            "success": True,
        })

        scratch.cleanup()
        return FrameworkExecutionResult(
            framework_name=fw.name,
            execution_id=scratch.execution_id,
            user_input=effective_input,
            milestones=results,
            final_output=final_output,
            success=True,
            duration_seconds=time.time() - started,
            mode=selected_mode,
            mode_reasoning=mode_reasoning,
        )
    except MilestoneExecutionError as exc:
        scratch.mark_failed(
            milestone_id=results[-1].milestone_id if results else "unknown",
            reason=str(exc),
        )

        # ---- Oversight hook: FrameworkComplete (failure) + MilestoneBlocked ----
        emit_oversight_event({
            "event_type": "MilestoneBlocked",
            "framework_id": fw.name,
            "mode": selected_mode,
            "execution_id": scratch.execution_id,
            "milestone_id": results[-1].milestone_id if results else "unknown",
            "block_reason": str(exc),
            "block_evidence": "",
            "project_nexus": project_nexus,
        })
        emit_oversight_event({
            "event_type": "FrameworkComplete",
            "framework_id": fw.name,
            "mode": selected_mode,
            "execution_id": scratch.execution_id,
            "final_output_path": "",
            "milestones": [
                {
                    "milestone_id": r.milestone_id,
                    "name": r.name,
                    "drift_status": r.drift_status,
                    "attempts": r.attempts,
                }
                for r in results
            ],
            "project_nexus": project_nexus,
            "success": False,
            "failure_reason": str(exc),
        })

        return FrameworkExecutionResult(
            framework_name=fw.name,
            execution_id=scratch.execution_id,
            user_input=effective_input,
            milestones=results,
            final_output="",
            success=False,
            failure_reason=str(exc),
            duration_seconds=time.time() - started,
            mode=selected_mode,
            mode_reasoning=mode_reasoning,
        )


# ---------- Per-milestone execution ----------

def _run_milestone(
    framework: Framework,
    milestone: Milestone,
    scratch: ScratchSession,
    user_input: str,
    config: dict,
) -> MilestoneResult:
    """Execute a single milestone with retry. Returns a MilestoneResult.

    Raises MilestoneExecutionError on 3rd failure.
    """
    handoff = _build_handoff_packet(framework, milestone, scratch, user_input)

    last_exception: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            deliverable = _run_through_gear_pipeline(handoff, milestone, config)
            scratch.write_milestone(milestone.id, deliverable)

            drift_status, drift_reasoning = _run_drift_check(
                milestone, deliverable, user_input, config
            )
            return MilestoneResult(
                milestone_id=milestone.id,
                name=milestone.name,
                deliverable=deliverable,
                drift_status=drift_status,
                drift_reasoning=drift_reasoning,
                attempts=attempt,
            )
        except Exception as exc:
            last_exception = exc
            # Brief backoff between retries
            if attempt < MAX_RETRIES:
                time.sleep(2 ** (attempt - 1))

    raise MilestoneExecutionError(
        f"Milestone {milestone.id} ({milestone.name!r}) failed after "
        f"{MAX_RETRIES} attempts. Last error: {last_exception}"
    )


# ---------- Handoff packet construction ----------

def _build_handoff_packet(
    framework: Framework,
    milestone: Milestone,
    scratch: ScratchSession,
    user_input: str,
) -> str:
    """Assemble the structured handoff packet that becomes the user message
    to the gear pipeline. Properties are bound inline to this milestone's path.
    """
    sections = []

    sections.append(f"ORIGINAL USER INPUT:\n{user_input}")
    sections.append("")

    prior_deliverables = scratch.read_all_prior(milestone.required_prior)
    if prior_deliverables:
        sections.append("PRIOR MILESTONE DELIVERABLES:")
        for mid in milestone.required_prior:
            content = prior_deliverables.get(mid, "<missing>")
            sections.append(f"  {mid}:")
            sections.append(_indent(content, "    "))
            sections.append("")
    else:
        sections.append("PRIOR MILESTONE DELIVERABLES: (none)")
        sections.append("")

    sections.append(
        f"CURRENT MILESTONE: {milestone.id} — {milestone.name}"
    )
    sections.append("")

    layer_bodies = _collect_layer_bodies(framework, milestone)
    if layer_bodies:
        sections.append("LAYER INSTRUCTIONS:")
        sections.append("")
        for label, body in layer_bodies:
            sections.append(f"## LAYER {label}: (covered by {milestone.id})")
            sections.append(body)
            sections.append("")
    else:
        sections.append(
            "LAYER INSTRUCTIONS: (none parsed — milestone references layers "
            f"{milestone.layers_covered} but no matching ## LAYER blocks "
            "were found in the framework)"
        )
        sections.append("")

    sections.append("OUTPUT SPECIFICATION:")
    sections.append(milestone.output_format or "(use the format implied by the layer instructions)")
    sections.append("")

    sections.append("VERIFICATION CRITERION (success target for this milestone):")
    sections.append(milestone.verification_criterion)
    sections.append("")

    if milestone.conditional_layers:
        sections.append("CONDITIONAL LAYERS (apply only when stated condition holds):")
        sections.append(milestone.conditional_layers)
        sections.append("")

    sections.append(
        f"Produce the milestone deliverable now. The deliverable should "
        f"satisfy the verification criterion above and conform to the "
        f"output specification."
    )

    return "\n".join(sections)


def _collect_layer_bodies(
    framework: Framework, milestone: Milestone
) -> list[tuple[str, str]]:
    """Look up Layer bodies for each layer in milestone.layers_covered.
    Returns list of (label, body) tuples in the order declared.
    Layers not found are silently skipped — caller's handoff packet notes the gap.
    """
    out = []
    for label in milestone.layers_covered:
        # Try exact match first; then strip trailing punctuation
        if label in framework.layers:
            out.append((label, framework.layers[label].body))
            continue
        stripped = label.rstrip(".,;")
        if stripped in framework.layers:
            out.append((stripped, framework.layers[stripped].body))
            continue
        # Try matching by integer if the label is numeric
        try:
            num = int(stripped)
            for raw_label, layer in framework.layers.items():
                if layer.number == num:
                    out.append((raw_label, layer.body))
                    break
        except ValueError:
            pass
    return out


def _indent(text: str, prefix: str) -> str:
    return "\n".join(prefix + line for line in text.split("\n"))


# ---------- Gear pipeline invocation ----------

def _run_through_gear_pipeline(
    handoff_packet: str, milestone: Milestone, config: dict
) -> str:
    """Send the handoff packet through the existing gear pipeline.

    For Gear 4 (default), uses run_gear4 from boot.py. Lower gears fall back
    to run_gear3 or a single-model pass.

    Bypasses Phase A.5 cleanup and mode classification — the handoff packet
    is structured framework-generated content, not raw human input. The mode
    is set to 'synthesis' as a sensible default (gear-4 capable, synthesis-
    shaped) but the framework's layer instructions in the handoff dominate.
    """
    from boot import run_gear3, run_gear4, build_system_prompt_for_gear

    context_pkg = _build_context_pkg(handoff_packet, milestone)

    if milestone.gear >= 4:
        return run_gear4(context_pkg, config)
    elif milestone.gear == 3:
        return run_gear3(context_pkg, config)
    else:
        # Gear 1-2: single-pass via existing helper
        from boot import _run_model_with_tools, get_active_endpoint, get_slot_endpoint
        endpoint = (
            get_slot_endpoint(config, "classification") if milestone.gear == 1
            else get_active_endpoint(config)
        )
        if endpoint is None:
            raise MilestoneExecutionError(
                f"No endpoint available for gear {milestone.gear}"
            )
        system_prompt = build_system_prompt_for_gear(context_pkg, "breadth")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": handoff_packet},
        ]
        return _run_model_with_tools(messages, endpoint)


def _build_context_pkg(handoff_packet: str, milestone: Milestone) -> dict:
    """Build the minimal context_pkg that run_gear3/4 expect."""
    return {
        "cleaned_prompt": handoff_packet,
        "operational_notation": handoff_packet,
        "mode": "synthesis",  # MVP default; layer instructions dominate
        "gear": milestone.gear,
        "triage_tier": 1,
        "conversation_rag": "",
        "concept_rag": "",
        "framework_execution": True,
        "milestone_id": milestone.id,
    }


# ---------- Drift check ----------

def _run_drift_check(
    milestone: Milestone,
    deliverable: str,
    user_input: str,
    config: dict,
) -> tuple[str, str]:
    """Ask the milestone's drift_check_question against the deliverable.

    Returns (status, reasoning) where status is one of:
      - "IN_SCOPE": deliverable addresses the user's original input
      - "DRIFT_DETECTED": deliverable has wandered
      - "DRIFT_CHECK_SKIPPED": no drift question, or no available endpoint
    """
    if not milestone.drift_check_question:
        return ("DRIFT_CHECK_SKIPPED", "No drift check question declared.")

    from boot import call_model, get_slot_endpoint, get_active_endpoint
    endpoint = get_slot_endpoint(config, DRIFT_CHECK_SLOT) or get_active_endpoint(config)
    if endpoint is None:
        return ("DRIFT_CHECK_SKIPPED", "No endpoint available for drift check.")

    prompt = (
        "You are a drift-detection auditor. Compare the milestone deliverable "
        "below against the user's original input, then answer the specific "
        "drift check question.\n\n"
        f"USER'S ORIGINAL INPUT:\n{user_input}\n\n"
        f"MILESTONE DELIVERABLE:\n{deliverable}\n\n"
        f"DRIFT CHECK QUESTION:\n{milestone.drift_check_question}\n\n"
        "Answer in this exact format:\n"
        "STATUS: <IN_SCOPE | DRIFT_DETECTED>\n"
        "REASONING: <one or two sentences explaining your verdict>\n"
    )
    messages = [
        {"role": "system", "content": "You are a careful auditor."},
        {"role": "user", "content": prompt},
    ]

    try:
        response = call_model(messages, endpoint)
    except Exception as exc:
        return ("DRIFT_CHECK_SKIPPED", f"Drift check call failed: {exc}")

    return _parse_drift_response(response)


def _parse_drift_response(response: str) -> tuple[str, str]:
    """Extract STATUS and REASONING from the drift check response."""
    import re
    status = "DRIFT_CHECK_SKIPPED"
    reasoning = response.strip()[:500]

    status_match = re.search(r"STATUS:\s*(IN_SCOPE|DRIFT_DETECTED)", response, re.I)
    if status_match:
        status = status_match.group(1).upper()

    reasoning_match = re.search(
        r"REASONING:\s*(.+?)(?:\n[A-Z]+:|\Z)", response, re.I | re.DOTALL
    )
    if reasoning_match:
        reasoning = reasoning_match.group(1).strip()

    return (status, reasoning)


# ---------- Multi-mode dispatch ----------

def _build_mechanical_redirect(
    fw: Framework,
    selected_mode: str,
    mode_reasoning: str,
    effective_input: str,
    execution_id: Optional[str] = None,
) -> FrameworkExecutionResult:
    """Return a FrameworkExecutionResult that redirects the user to the
    matching slash command instead of running the gear pipeline.

    Mechanical modes (C-Instance / C-Validate / O-Render) are handled by
    runtime functions, not by model passes. Running them through /framework
    would produce a hallucinated artifact rather than actually creating a
    file. This redirect surfaces the canonical invocation so the user can
    re-issue the request via the slash command.
    """
    slash_form = MECHANICAL_MODE_REDIRECTS[selected_mode]
    body = (
        f"**{fw.name} — mode {selected_mode} is mechanical.**\n\n"
        f"This mode is handled by the runtime, not by the framework executor. "
        f"To run it, use:\n\n"
        f"```\n{slash_form}\n```\n\n"
        f"Routing detail: {mode_reasoning}.\n"
    )
    if effective_input:
        body += f"\nYour input was: {effective_input!r}"

    exec_id = execution_id or "no-execution"
    return FrameworkExecutionResult(
        framework_name=fw.name,
        execution_id=exec_id,
        user_input=effective_input,
        milestones=[],
        final_output=body,
        success=True,
        duration_seconds=0.0,
        mode=selected_mode,
        mode_reasoning=mode_reasoning,
    )


def select_mode(
    fw: Framework, user_input: str, config: dict
) -> tuple[str, str, str]:
    """Pick the operating mode for a multi-mode framework.

    Selection priority:
      1. Explicit prefix — first whitespace-separated token of user_input
         matches one of the framework's declared modes (case-insensitive).
         The token is consumed; remaining text becomes the effective input.
      2. In-input mention — any declared mode name appears anywhere in
         user_input (case-insensitive). First match wins. effective_input
         is the original user_input.
      3. LLM-based routing classifier — small-model call with the M0 routing
         function text and a one-line catalog of modes. Skipped when no
         endpoint is available.
      4. Default to the first declared mode.

    Returns (mode, reasoning, effective_input). For single-mode frameworks
    or frameworks with no declared modes, returns ("all", reason, user_input).
    """
    if not fw.is_multi_mode or not fw.modes:
        return ("all", "single-mode framework", user_input)

    # 1. Explicit prefix
    parts = user_input.strip().split(maxsplit=1)
    if parts:
        first = parts[0]
        for mode_name in fw.modes:
            if first.lower() == mode_name.lower():
                remaining = parts[1] if len(parts) > 1 else ""
                return (
                    mode_name,
                    f"explicit prefix: first token matched mode {mode_name!r}",
                    remaining,
                )

    # 2. In-input mention
    lower_input = user_input.lower()
    for mode_name in fw.modes:
        if mode_name.lower() in lower_input:
            return (
                mode_name,
                f"mode {mode_name!r} mentioned in user input",
                user_input,
            )

    # 3. LLM-based routing classifier
    selected = _llm_select_mode(fw, user_input, config)
    if selected:
        mode, reasoning = selected
        return (mode, reasoning, user_input)

    # 4. Default to first declared mode
    first_mode = fw.modes[0]
    return (
        first_mode,
        f"no mode signal detected; defaulting to first declared mode "
        f"{first_mode!r}",
        user_input,
    )


def _llm_select_mode(
    fw: Framework, user_input: str, config: dict
) -> Optional[tuple[str, str]]:
    """Ask a small model to pick a mode given the user input.

    Returns (mode, reasoning) on success, None on failure or when no
    endpoint is available. The selected mode is matched against
    fw.modes case-insensitively; an out-of-list response yields None.
    """
    try:
        from boot import call_model, get_slot_endpoint, get_active_endpoint
    except Exception:
        return None

    endpoint = (
        get_slot_endpoint(config, MODE_SELECT_SLOT)
        or get_active_endpoint(config)
    )
    if endpoint is None:
        return None

    catalog = _build_mode_catalog(fw)

    prompt = (
        "You are a routing classifier for a multi-mode framework. Read the "
        "framework's mode catalog and the user's request, then pick the single "
        "best-fit mode.\n\n"
        f"FRAMEWORK: {fw.name}\n\n"
        f"MODE CATALOG:\n{catalog}\n\n"
        f"USER REQUEST:\n{user_input}\n\n"
        "Answer in this exact format:\n"
        "MODE: <one mode name from the catalog, exactly as written>\n"
        "REASONING: <one sentence>"
    )
    messages = [
        {"role": "system", "content": "You are a careful routing classifier."},
        {"role": "user", "content": prompt},
    ]

    try:
        response = call_model(messages, endpoint)
    except Exception:
        return None

    return _parse_mode_response(response, fw.modes)


def _build_mode_catalog(fw: Framework) -> str:
    """Construct a short catalog string for the routing classifier prompt."""
    lines: list[str] = []
    if fw.m0_routing and fw.m0_routing.function:
        lines.append(f"Routing function: {fw.m0_routing.function}")
        lines.append("")
    for mode_name in fw.modes:
        ms_list = fw.milestones_by_mode.get(mode_name, [])
        if ms_list:
            lines.append(f"- {mode_name}: {ms_list[0].name}")
        else:
            lines.append(f"- {mode_name}")
    return "\n".join(lines)


def _parse_mode_response(
    response: str, valid_modes: list[str]
) -> Optional[tuple[str, str]]:
    """Extract MODE and REASONING from the routing response.

    Returns None if no MODE line is found or the value isn't a declared mode.
    """
    import re
    m = re.search(r"MODE:\s*(\S+)", response, re.I)
    if not m:
        return None
    raw_mode = m.group(1).strip().rstrip(".,;:")
    for vm in valid_modes:
        if raw_mode.lower() == vm.lower():
            r = re.search(r"REASONING:\s*(.+)", response, re.I | re.DOTALL)
            reasoning = (
                r.group(1).strip()[:300] if r else "selected by routing classifier"
            )
            return (vm, f"routing classifier picked {vm!r}: {reasoning}")
    return None


# ---------- Slash-command invocation ----------

FRAMEWORK_COMMAND_PREFIX = "/framework "


def is_framework_command(user_input: str) -> bool:
    """Check if user_input starts with the /framework slash command."""
    return user_input.strip().startswith(FRAMEWORK_COMMAND_PREFIX)


def parse_framework_command(user_input: str) -> tuple[str, str]:
    """Parse '/framework <name> [<query>]' into (framework_filename, query).

    framework_filename gets .md appended if not already present.
    Raises ValueError if the framework name is missing.

    An empty query is allowed and returned as "". The caller decides how to
    handle it: ``run_framework_command`` treats empty as an error (it expects
    a one-shot invocation), while ``framework_elicitation.start_elicitation``
    treats empty as the trigger for an interactive multi-turn session.

    Multi-mode dispatch: the executor inspects the query for a mode token
    (either as the first word or anywhere in the body). To force a specific
    mode, prefix the query with the mode name — e.g.
    ``/framework problem-evolution PE-Init walk through the new project``
    runs PE-Init regardless of context. Without an explicit token, the
    executor's ``select_mode`` falls through to in-input mention, then to
    LLM-based routing, then to the first declared mode.
    """
    body = user_input.strip()[len(FRAMEWORK_COMMAND_PREFIX):].strip()
    parts = body.split(maxsplit=1)
    if not parts:
        raise ValueError("missing framework name; usage: /framework <name> [<query>]")
    framework_name = parts[0]
    if not framework_name.endswith(".md"):
        framework_name += ".md"
    framework_query = parts[1] if len(parts) > 1 else ""
    return framework_name, framework_query


def framework_command_has_query(user_input: str) -> bool:
    """Return True iff /framework <name> was invoked with a non-empty query.

    Used by the chat handler to choose between one-shot dispatch
    (``run_framework_command``) and interactive elicitation
    (``framework_elicitation.start_elicitation``).
    """
    try:
        _, query = parse_framework_command(user_input)
    except ValueError:
        return False
    return bool(query.strip())


def format_execution_result(result: FrameworkExecutionResult) -> str:
    """Format a FrameworkExecutionResult as user-facing markdown."""
    mode_suffix = (
        f" / mode {result.mode}"
        if result.mode and result.mode != "all"
        else ""
    )
    if not result.success:
        return (
            f"[Framework {result.framework_name}{mode_suffix} failed at "
            f"{len(result.milestones)} milestone(s). {result.failure_reason}]\n\n"
            f"Scratch preserved at ~/ora/scratch/{result.execution_id}/"
        )

    drift_warnings = []
    for ms in result.milestones:
        if ms.drift_status == "DRIFT_DETECTED":
            drift_warnings.append(
                f"  - {ms.milestone_id} ({ms.name}): {ms.drift_reasoning}"
            )

    parts = [
        f"[Framework: {result.framework_name}{mode_suffix} | "
        f"Execution: {result.execution_id} | "
        f"Milestones: {len(result.milestones)} | "
        f"Duration: {result.duration_seconds:.1f}s]",
    ]
    if mode_suffix and result.mode_reasoning:
        parts.append(f"[Mode selection: {result.mode_reasoning}]")
    if drift_warnings:
        parts.append("[Drift warnings]:")
        parts.extend(drift_warnings)
    parts.append("")
    parts.append(result.final_output)
    return "\n".join(parts)


def run_framework_command(user_input: str, config: dict) -> str:
    """Top-level: parse a slash command + execute + format. Used by boot.py
    and server.py as the entry point for /framework slash-command invocations.

    Returns a formatted user-facing string. Errors are caught and surfaced
    in the returned string rather than raising, so the chat UI always
    receives a renderable response.
    """
    try:
        framework_name, framework_query = parse_framework_command(user_input)
    except ValueError as exc:
        return f"[Framework command error: {exc}]"

    if not framework_query.strip():
        return (
            f"[Framework {framework_name} invoked without a query. For one-shot "
            f"execution, supply a query: `/framework {framework_name} <your input>`. "
            f"For interactive elicitation, the chat handler should route empty-query "
            f"invocations through framework_elicitation.start_elicitation rather than "
            f"this entry point.]"
        )

    try:
        result = execute_framework(framework_name, framework_query, config)
    except FileNotFoundError as exc:
        return f"[Framework file not found: {exc}]"
    except FrameworkParseError as exc:
        return f"[Framework parse error: {exc}]"
    except NotImplementedError as exc:
        return f"[Framework execution not yet supported: {exc}]"
    except Exception as exc:
        return f"[Unexpected error during framework execution: {exc}]"

    return format_execution_result(result)


# ---------- CLI smoke test ----------

if __name__ == "__main__":
    """Run a parser-only dry-run to verify the executor can build handoff
    packets without actually calling models."""
    target = sys.argv[1] if len(sys.argv) > 1 else "deep-research-protocol.md"

    fw = parse_framework_file(target)
    print(f"Framework: {fw.name}")
    print(f"  multi-mode: {fw.is_multi_mode}")
    if fw.is_multi_mode:
        print("  (executor MVP supports single-mode only — would skip)")
        sys.exit(0)

    milestones = fw.milestones_by_mode["all"]
    print(f"  milestones: {len(milestones)}")

    # Simulate a scratch session and build a handoff packet for each milestone
    sess = ScratchSession.create(fw.name)
    user_input = "What does AI mean for the future of human cognition?"

    for ms in milestones:
        # Fake prior milestone outputs for handoff packet preview
        for prior in ms.required_prior:
            if not sess.has_milestone(prior):
                sess.write_milestone(prior, f"<simulated content for {prior}>")
        packet = _build_handoff_packet(fw, ms, sess, user_input)
        print(f"\n--- Handoff packet for {ms.id} ({ms.name}) ---")
        print(packet[:1500] + ("..." if len(packet) > 1500 else ""))

    sess.cleanup()
    print(f"\n[Smoke test complete. Cleaned up scratch.]")
