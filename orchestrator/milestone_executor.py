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


class MilestoneExecutionError(Exception):
    """Raised when a milestone fails after MAX_RETRIES attempts."""
    pass


# ---------- Public API ----------

def execute_framework(
    framework_path: str,
    user_input: str,
    config: Optional[dict] = None,
    execution_id: Optional[str] = None,
) -> FrameworkExecutionResult:
    """Execute a framework on the given user input.

    Returns a FrameworkExecutionResult. On success, scratch is cleaned up.
    On failure, scratch is preserved for inspection or resume.

    For multi-mode frameworks: only single-mode execution is supported in
    the MVP. Multi-mode invocations require explicit mode selection (TODO:
    M0 routing wiring).
    """
    # Lazy import of boot.py to avoid circular issues during testing
    from boot import load_endpoints

    if config is None:
        config = load_endpoints()

    fw = parse_framework_file(framework_path)

    if fw.is_multi_mode:
        raise NotImplementedError(
            f"Framework {fw.name!r} is multi-mode. The MVP executor supports "
            "single-mode frameworks only. Multi-mode routing (M0) is a "
            "follow-up build item."
        )

    milestones = fw.milestones_by_mode.get("all", [])
    if not milestones:
        raise FrameworkParseError(
            f"Framework {fw.name!r} declared no milestones to execute."
        )

    scratch = ScratchSession.create(fw.name, execution_id=execution_id)
    started = time.time()
    results: list[MilestoneResult] = []

    try:
        for milestone in milestones:
            result = _run_milestone(fw, milestone, scratch, user_input, config)
            results.append(result)
            if result.drift_status == "DRIFT_DETECTED":
                # MVP behavior: log and continue. Future: pause / surface.
                # Drift is recorded in result.drift_reasoning.
                pass
        # Final output = last milestone's deliverable
        final_output = results[-1].deliverable if results else ""
        scratch.mark_complete()
        scratch.cleanup()
        return FrameworkExecutionResult(
            framework_name=fw.name,
            execution_id=scratch.execution_id,
            user_input=user_input,
            milestones=results,
            final_output=final_output,
            success=True,
            duration_seconds=time.time() - started,
        )
    except MilestoneExecutionError as exc:
        scratch.mark_failed(
            milestone_id=results[-1].milestone_id if results else "unknown",
            reason=str(exc),
        )
        return FrameworkExecutionResult(
            framework_name=fw.name,
            execution_id=scratch.execution_id,
            user_input=user_input,
            milestones=results,
            final_output="",
            success=False,
            failure_reason=str(exc),
            duration_seconds=time.time() - started,
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


# ---------- Slash-command invocation ----------

FRAMEWORK_COMMAND_PREFIX = "/framework "


def is_framework_command(user_input: str) -> bool:
    """Check if user_input starts with the /framework slash command."""
    return user_input.strip().startswith(FRAMEWORK_COMMAND_PREFIX)


def parse_framework_command(user_input: str) -> tuple[str, str]:
    """Parse '/framework <name> <query>' into (framework_filename, query).

    framework_filename gets .md appended if not already present.
    Raises ValueError on missing parts.
    """
    body = user_input.strip()[len(FRAMEWORK_COMMAND_PREFIX):].strip()
    parts = body.split(maxsplit=1)
    if not parts:
        raise ValueError("missing framework name; usage: /framework <name> <query>")
    framework_name = parts[0]
    if not framework_name.endswith(".md"):
        framework_name += ".md"
    framework_query = parts[1] if len(parts) > 1 else ""
    if not framework_query:
        raise ValueError(
            f"framework {framework_name} invoked without a query; "
            f"usage: /framework <name> <query>"
        )
    return framework_name, framework_query


def format_execution_result(result: FrameworkExecutionResult) -> str:
    """Format a FrameworkExecutionResult as user-facing markdown."""
    if not result.success:
        return (
            f"[Framework {result.framework_name} failed at "
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
        f"[Framework: {result.framework_name} | "
        f"Execution: {result.execution_id} | "
        f"Milestones: {len(result.milestones)} | "
        f"Duration: {result.duration_seconds:.1f}s]",
    ]
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
