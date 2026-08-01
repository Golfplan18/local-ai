"""Framework elicitation — multi-turn interactive framework execution.

Implements conversation-mediated framework execution per the design called
out in the meta-layer handoff §"Genuinely Deferred (Next Session)" item 6,
without a separate persistence layer. The conversation transcript IS the
state. Each mid-framework turn is tagged with an HTML-comment marker that
encodes (framework_id, mode); on the next turn the executor sees the
marker, routes to this handler, asks a small-model summarizer to extract
what has been elicited so far, and either asks the next question or
produces the final deliverable.

Public API:
    is_continuation(history)            -> Optional[ContinuationContext]
    start_elicitation(...)              -> str
    continue_elicitation(...)           -> str

The marker format:

    <!-- ora-framework: <framework_id>/<mode>/eliciting -->

is appended at the very end of the assistant message, on its own line.
HTML comments are invisible in markdown render but trivially regex-able.
The final deliverable turn is emitted WITHOUT a marker, signaling back to
normal chat — there is no "complete" state to detect, just absence.

Per Reference — Meta-Layer Architecture; the deferred multi-step
elicitation item from the 2026-05-04 implementation handoff.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Optional

_ORCH_DIR = os.path.dirname(os.path.abspath(__file__))
if _ORCH_DIR not in sys.path:
    sys.path.insert(0, _ORCH_DIR)

from framework_parser import (
    Framework,
    Milestone,
    parse_framework_file,
    FrameworkParseError,
)


# ---------- Marker convention ----------

ELICITATION_SLOT = "sidebar"  # small model — same slot as drift check + mode select

MARKER_PATTERN = re.compile(
    r"<!--\s*ora-framework:\s*([A-Za-z0-9_\-\.]+)/([A-Za-z0-9_\-]+)/"
    r"([A-Za-z0-9_\-]+)(?:/([A-Za-z0-9_\-]+))?\s*-->",
)
MARKER_TEMPLATE = "<!-- ora-framework: {framework_id}/{mode}/{state} -->"
ELICITING_STATE = "eliciting"

# Execution Review Phase 2: a hold reply carries this marker; such a turn is
# risk-gate scaffolding, not elicited content, so the summarizer skips it.
_TASK_GATE_MARKER_RE = re.compile(r"<!--\s*ora-task-gate:.*?-->", re.DOTALL)


@dataclass
class ContinuationContext:
    framework_id: str   # framework filename without .md (e.g., "corpus-formalization")
    mode: str           # mode name (e.g., "C-Design")
    state: str          # currently always "eliciting"
    project_nexus: str | None = None
    one_run_profile: str | None = None
    context_error: str | None = None


def _decode_execution_context(token: str | None) -> dict:
    if not token:
        return {"project_nexus": None, "one_run_profile": None}
    try:
        padding = "=" * (-len(token) % 4)
        value = json.loads(base64.urlsafe_b64decode(token + padding).decode("utf-8"))
    except Exception as exc:
        raise ValueError("framework execution context marker is malformed") from exc
    if not isinstance(value, dict) or set(value) != {"project_nexus", "one_run_profile"}:
        raise ValueError("framework execution context marker schema is invalid")
    project_nexus = value.get("project_nexus")
    one_run_profile = value.get("one_run_profile")
    try:
        if project_nexus is not None:
            from project_meta import validate_nexus
            project_nexus = validate_nexus(project_nexus)
        if one_run_profile is not None:
            from model_profiles import validate_profile_name
            one_run_profile = validate_profile_name(one_run_profile)
    except (TypeError, ValueError) as exc:
        raise ValueError("framework execution context marker values are invalid") from exc
    return {
        "project_nexus": project_nexus,
        "one_run_profile": one_run_profile,
    }


# ---------- Public API ----------

def is_continuation(history: list) -> Optional[ContinuationContext]:
    """Return a ContinuationContext if the most recent assistant message in
    history carries a mid-framework marker. None otherwise.

    history is a list of message dicts in the standard {"role": "...", "content": "..."}
    shape. The most recent assistant message is the last one with role=="assistant";
    if there is no assistant message, returns None.
    """
    if not history:
        return None
    for msg in reversed(history):
        if msg.get("role") != "assistant":
            continue
        m = MARKER_PATTERN.search(msg.get("content", "") or "")
        if not m:
            return None
        try:
            execution_context = _decode_execution_context(m.group(4))
            context_error = None
        except ValueError as exc:
            execution_context = {"project_nexus": None, "one_run_profile": None}
            context_error = str(exc)
        return ContinuationContext(
            framework_id=m.group(1), mode=m.group(2), state=m.group(3),
            context_error=context_error, **execution_context,
        )
    return None


def start_elicitation(
    framework_name: str,
    history: list,
    config: dict,
    initial_user_message: str = "",
    project_nexus: str | None = None,
    one_run_profile: str | None = None,
) -> str:
    """Begin a fresh interactive framework execution.

    framework_name: the name token after /framework (with or without .md)
    history: prior conversation history (so the elicitor sees any preamble)
    config: endpoints config
    initial_user_message: the user's text after the /framework <name> trigger,
        if any. Empty when the user typed only `/framework cff`.

    Returns the assistant message text including the trailing marker.
    """
    fw_filename = framework_name if framework_name.endswith(".md") else framework_name + ".md"
    try:
        fw = parse_framework_file(fw_filename)
    except FileNotFoundError:
        return f"[Framework file not found: {fw_filename}]"
    except FrameworkParseError as exc:
        return f"[Framework parse error: {exc}]"

    mode, milestone = _resolve_mode_for_elicitation(fw, initial_user_message, config)
    if milestone is None:
        return (
            f"[Framework {fw.name!r} has no milestones declared for the requested "
            f"mode. Cannot start elicitation.]"
        )

    # Mechanical modes don't need elicitation — redirect to the slash command.
    redirect = _mechanical_mode_redirect(fw.name, mode)
    if redirect:
        return redirect

    return _run_elicitation_turn(
        fw, mode, milestone, history, config,
        latest_user_text=initial_user_message,
        project_nexus=project_nexus,
        one_run_profile=one_run_profile,
    )


def continue_elicitation(
    ctx: ContinuationContext,
    history: list,
    config: dict,
    latest_user_text: str = "",
    conversation_id: str | None = None,
    current_project_nexus: str | None = None,
) -> str:
    """Advance an in-progress framework execution by one turn.

    Reads the conversation, summarizes what's been elicited, and either asks
    the next question or produces the final deliverable.

    ``conversation_id`` (Execution Review Phase 2): binds the irreversible-
    deliverable approval token to THIS conversation, so an approval in one
    conversation can't admit the same framework/mode deliverable in another.
    """
    if ctx.context_error:
        return f"[Framework continuation rejected: {ctx.context_error}.]"
    if ctx.project_nexus != current_project_nexus:
        return (
            "[Framework continuation rejected: the active project changed after "
            "elicitation began. Restart the framework in the intended project.]"
        )

    fw_filename = (
        ctx.framework_id if ctx.framework_id.endswith(".md") else ctx.framework_id + ".md"
    )
    try:
        fw = parse_framework_file(fw_filename)
    except FileNotFoundError:
        return f"[Framework file not found: {fw_filename}]"
    except FrameworkParseError as exc:
        return f"[Framework parse error: {exc}]"

    milestone = _first_milestone_for_mode(fw, ctx.mode)
    if milestone is None:
        return (
            f"[Mid-framework continuation lost its target: framework {fw.name!r} "
            f"declares no milestones for mode {ctx.mode!r}.]"
        )

    return _run_elicitation_turn(
        fw, ctx.mode, milestone, history, config,
        latest_user_text=latest_user_text,
        conversation_id=conversation_id,
        project_nexus=ctx.project_nexus,
        one_run_profile=ctx.one_run_profile,
    )


# ---------- Per-turn execution ----------

def _run_elicitation_turn(
    fw: Framework,
    mode: str,
    milestone: Milestone,
    history: list,
    config: dict,
    latest_user_text: str,
    conversation_id: str | None = None,
    project_nexus: str | None = None,
    one_run_profile: str | None = None,
) -> str:
    """One elicitation turn: summarize state, decide next step, emit response."""
    summary = _ask_summarizer(fw, mode, milestone, history, latest_user_text, config)

    if summary is None:
        # Summarizer unavailable or unparseable — emit a graceful question
        # asking the user to tell us what's most relevant to producing the milestone
        # deliverable, with the marker still attached so the next turn re-tries.
        question = (
            f"To produce the {fw.name} / {mode} deliverable I need a few pieces of "
            "information. Could you start by describing the workflow or context this "
            "is for, and any sources/inputs the framework should know about?"
        )
        return _wrap_with_marker(
            question, fw.name, mode, project_nexus, one_run_profile,
        )

    if summary.action == "PRODUCE_DELIVERABLE":
        return _produce_deliverable(fw, mode, milestone, summary, history,
                                    latest_user_text, config,
                                    conversation_id=conversation_id,
                                    project_nexus=project_nexus,
                                    one_run_profile=one_run_profile)

    # ASK_NEXT path
    question = summary.next_question or (
        "What additional information should I have before I produce the deliverable?"
    )
    body = question
    if summary.elicited_bullets:
        body = (
            "_So far I have:_\n"
            + "\n".join(f"- {b}" for b in summary.elicited_bullets)
            + "\n\n"
            + question
        )
    return _wrap_with_marker(
        body, fw.name, mode, project_nexus, one_run_profile,
    )


def _produce_deliverable(
    fw: Framework,
    mode: str,
    milestone: Milestone,
    summary: "_SummaryState",
    history: list,
    latest_user_text: str,
    config: dict,
    conversation_id: str | None = None,
    project_nexus: str | None = None,
    one_run_profile: str | None = None,
) -> str:
    """Hand control to the existing milestone executor with the elicited facts
    as the user input. The result is rendered with format_execution_result.

    The final turn carries NO marker — that signals back to normal chat.
    """
    from milestone_executor import execute_framework, format_execution_result

    elicited = "\n".join(f"- {b}" for b in summary.elicited_bullets) or (
        "(no facts extracted from the prior conversation)"
    )
    deliverable_input = (
        f"{mode} Produce the milestone deliverable using the following "
        f"elicited information:\n\n{elicited}"
    )

    fw_filename = fw.name if fw.name.endswith(".md") else fw.name + ".md"

    # Execution Review Phase 2 (judge condition 4): the interactive
    # final-deliverable path calls execute_framework() DIRECTLY, bypassing
    # the server/boot framework branches — so the irreversible-tier hold must
    # fire here too, before the executor runs. Fail-safe: a risk-gate error
    # never blocks a legitimate deliverable.
    try:
        import risk_gate as _rgate
    except ImportError:
        from orchestrator import risk_gate as _rgate
    try:
        # Classify the tier from the ACTUAL deliverable content (a "publish
        # to all subscribers" deliverable is irreversible). The fingerprint
        # binds: conversation (conversation_id), framework+mode, AND a CONTENT
        # NONCE identifying THIS held instance. The nonce is a hash of the
        # normalized WORD MULTISET of the deliverable content (all word tokens,
        # lowercased, sorted) — recomputed every turn, NOT carried:
        #   * summarizer drift that only REORDERS bullets or words (the common
        #     nondeterminism) → identical nonce, so an approved deliverable
        #     still produces on resume (no re-hold);
        #   * a MATERIALLY different later deliverable (different words) → a
        #     distinct nonce → a distinct token → it CANNOT reuse an earlier
        #     hold's approval, even a still-live one (no carried nonce to
        #     inherit — this closes the approve-then-pivot reuse). Genuine
        #     word-substitution drift falls to a SAFE re-hold (re-approve), not
        #     reuse. Hashing the whole deliverable text (not just the bullets)
        #     means an empty-fact deliverable is not a constant nonce — it
        #     still carries the mode + boilerplate words, so two empty-fact
        #     deliverables collide only when they are genuinely identical.
        import hashlib as _hl
        import re as _re
        _facts = " ".join(sorted(
            _re.findall(r"\w+", (deliverable_input or "").lower())))
        _hnonce = _hl.sha1(_facts.encode("utf-8", "replace")).hexdigest()[:12]
        _stable_id = f"framework-deliverable::{fw.name}::{mode or ''}::{_hnonce}"
        _r = _rgate.assign_tier(deliverable_input, conversation_id,
                                surface="framework")
        _hold, _ = _rgate.evaluate_hold(
            _r["risk_tier"], conversation_id=conversation_id, prompt=_stable_id,
            surface="framework", mode_id=(fw.name + "/" + (mode or "")),
            description=f"Framework deliverable: {fw.name} {mode}".strip(),
            # Keep the elicitation flow alive across the hold: the approval
            # re-attaches the framework marker so the next turn re-produces
            # the deliverable (now with a valid token).
            resume={
                "fw": fw.name, "mode": mode or "",
                "project_nexus": project_nexus,
                "one_run_profile": one_run_profile,
            })
        if _hold is not None:
            return _hold
    except Exception as _rge:
        print(f"[risk-gate] framework-deliverable hold skipped: {_rge}")

    # Execution Review Phase 2 (judge finding 3): record route_observed on
    # this framework terminal path too — turn_ts captured BEFORE execution so
    # the fold counts this run's events; in a finally so a failed execution
    # still records what it did before dying.
    try:
        _dl_turn_ts = _rgate.now_ts()
        _dl_tier = _r.get("risk_tier") if isinstance(_r, dict) else None
    except Exception:
        _dl_turn_ts, _dl_tier = None, None
    # Seed the turn context so the deliverable's tool events carry this
    # conversation_id (the elicitation path bypasses step-2 seeding); without
    # it the route_observed fold below finds zero events on the server surface.
    try:
        import tool_events as _te_dl
        _te_dl.set_turn_context(conversation_id=conversation_id,
                                surface="framework", risk_tier=_dl_tier)
    except Exception:
        pass
    result = None
    try:
        result = execute_framework(
            fw_filename, deliverable_input, config=config,
            project_nexus=project_nexus, config_name=one_run_profile,
        )
    except Exception as exc:
        return f"[Final deliverable production failed: {exc}]"
    finally:
        try:
            # Phase 3: pass the produced deliverable so the source-read "makes
            # claims" test runs; None when execution failed (no grounded output).
            _dl_out = format_execution_result(result) if result is not None else None
            _rgate.record_route_observed((conversation_id, _dl_turn_ts or ""),
                                         risk_tier=_dl_tier, output_text=_dl_out)
        except Exception:
            pass

    return format_execution_result(result)


# ---------- Summarizer prompt + parsing ----------

@dataclass
class _SummaryState:
    elicited_bullets: list
    pending_bullets: list
    action: str  # "ASK_NEXT" or "PRODUCE_DELIVERABLE"
    next_question: str


def _ask_summarizer(
    fw: Framework,
    mode: str,
    milestone: Milestone,
    history: list,
    latest_user_text: str,
    config: dict,
) -> Optional[_SummaryState]:
    """Send a structured prompt to the small-model slot. Returns parsed state
    or None if the call fails / response is unparseable."""
    try:
        from boot import call_model, get_slot_endpoint, get_active_endpoint
    except Exception:
        return None

    endpoint = (
        get_slot_endpoint(config, ELICITATION_SLOT)
        or get_active_endpoint(config)
    )
    if endpoint is None:
        return None

    conversation_text = _format_conversation(history, latest_user_text)
    prompt = _build_summarizer_prompt(
        fw, mode, milestone, conversation_text, latest_user_text
    )
    messages = [
        {"role": "system", "content": "You are a careful elicitation summarizer."},
        {"role": "user", "content": prompt},
    ]

    try:
        response = call_model(messages, endpoint)
    except Exception:
        return None

    return _parse_summary_response(response)


def _build_summarizer_prompt(
    fw: Framework,
    mode: str,
    milestone: Milestone,
    conversation_text: str,
    latest_user_text: str,
) -> str:
    """Build the prompt the summarizer/elicitor sees each turn."""
    return (
        "You are guiding a user through a multi-turn elicitation for the "
        f"{fw.name} framework, mode {mode}. At every turn your job is to:\n\n"
        "1. Read the conversation so far and identify what has already been elicited.\n"
        "2. Compare against what the milestone needs (declared below).\n"
        "3. Decide whether to ask one more question (ASK_NEXT) or signal that "
        "enough information has been collected (PRODUCE_DELIVERABLE).\n\n"
        "Ask only ONE question per turn. Prefer questions that unblock the most "
        "downstream work. Do not ask the user to repeat information they have "
        "already provided.\n\n"
        f"ENDPOINT THE FRAMEWORK MUST PRODUCE:\n{milestone.endpoint_produced}\n\n"
        f"VERIFICATION CRITERION:\n{milestone.verification_criterion}\n\n"
        f"OUTPUT FORMAT REQUIRED:\n{milestone.output_format or '(use mode default)'}\n\n"
        "Respond in this EXACT format. Do not add prose outside these labels.\n\n"
        "ELICITED:\n"
        "- <one bullet per piece of information already collected, written as a complete fact>\n"
        "- <or write \"(none yet)\" if the conversation is just starting>\n\n"
        "PENDING:\n"
        "- <one bullet per piece of information still missing>\n"
        "- <or write \"(none)\" if everything is collected>\n\n"
        "ACTION: ASK_NEXT | PRODUCE_DELIVERABLE\n\n"
        "QUESTION: <the single next question to ask the user, plain language. "
        "Omit this field entirely if ACTION is PRODUCE_DELIVERABLE.>\n\n"
        "===\n"
        "CONVERSATION SO FAR:\n"
        f"{conversation_text}\n\n"
        "USER'S MOST RECENT MESSAGE:\n"
        f"{latest_user_text or '(no message — the user just invoked the framework)'}\n"
    )


def _parse_summary_response(response: str) -> Optional[_SummaryState]:
    """Extract ELICITED / PENDING / ACTION / QUESTION from the response.

    Returns None if ACTION can't be determined — caller falls back to a
    graceful default question.
    """
    if not response:
        return None

    elicited = _parse_bullet_block(response, "ELICITED")
    pending = _parse_bullet_block(response, "PENDING")

    action_match = re.search(
        r"ACTION:\s*(ASK_NEXT|PRODUCE_DELIVERABLE)", response, re.I
    )
    if not action_match:
        return None
    action = action_match.group(1).upper()

    question = ""
    q_match = re.search(
        r"QUESTION:\s*(.+?)(?:\n[A-Z][A-Z_]+:|\Z)",
        response, re.I | re.DOTALL,
    )
    if q_match:
        question = q_match.group(1).strip()

    return _SummaryState(
        elicited_bullets=elicited,
        pending_bullets=pending,
        action=action,
        next_question=question,
    )


def _parse_bullet_block(response: str, label: str) -> list:
    """Pull bullets under a `LABEL:` heading until the next `LABEL:` or EOF.

    Filters out the literal placeholder strings the prompt allows the model
    to use when the section is empty.
    """
    pattern = re.compile(
        rf"{re.escape(label)}:\s*\n(.*?)(?:\n[A-Z][A-Z_]+:|\Z)",
        re.DOTALL,
    )
    m = pattern.search(response)
    if not m:
        return []
    block = m.group(1)
    bullets = []
    for raw in block.split("\n"):
        line = raw.strip()
        if not line.startswith("-"):
            continue
        text = line[1:].strip()
        if not text:
            continue
        # Drop literal placeholders the prompt explicitly allows
        if text.lower() in {"(none yet)", "(none)"}:
            continue
        bullets.append(text)
    return bullets


# ---------- Helpers ----------

def _resolve_mode_for_elicitation(
    fw: Framework, initial_user_text: str, config: dict
) -> tuple:
    """Pick the mode for an elicitation start.

    For multi-mode frameworks, routes through milestone_executor.select_mode
    so the same priority chain (explicit prefix → in-input mention → LLM
    classifier → first declared) applies. For single-mode frameworks,
    returns ("all", first milestone).
    """
    if not fw.is_multi_mode:
        ms_list = fw.milestones_by_mode.get("all", [])
        return ("all", ms_list[0] if ms_list else None)

    from milestone_executor import select_mode
    mode, _, _ = select_mode(fw, initial_user_text, config)
    milestone = _first_milestone_for_mode(fw, mode)
    return (mode, milestone)


def _first_milestone_for_mode(fw: Framework, mode: str) -> Optional[Milestone]:
    ms_list = fw.milestones_by_mode.get(mode, [])
    return ms_list[0] if ms_list else None


def _mechanical_mode_redirect(framework_name: str, mode: str) -> Optional[str]:
    """Surface the matching slash command for mechanical modes; return None
    if the mode is model-driven.

    Mirrors milestone_executor.MECHANICAL_MODE_REDIRECTS but emits a fuller
    user-facing message (we're at the start of an interactive session, so
    the user explicitly asked for elicitation — be clear that this mode
    isn't elicitation-driven).
    """
    from milestone_executor import MECHANICAL_MODE_REDIRECTS
    slash = MECHANICAL_MODE_REDIRECTS.get(mode)
    if not slash:
        return None
    return (
        f"**{framework_name} — mode {mode} is mechanical, not elicitation-driven.**\n\n"
        f"Use the runtime slash command directly:\n\n```\n{slash}\n```"
    )


def _format_conversation(history: list, latest_user_text: str) -> str:
    """Format prior history + the latest user message for the summarizer prompt.

    Drops system messages; trims content per turn so the prompt doesn't
    explode on long sessions.
    """
    lines = []
    for msg in history:
        role = msg.get("role", "")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content", "") or ""
        # A risk-gate hold reply is pure scaffolding (the ⚠️ approve/cancel
        # prose + the ora-task-gate marker), NOT elicited facts — skip it
        # wholesale so it can't pollute the summarizer's fact extraction.
        if _TASK_GATE_MARKER_RE.search(content):
            continue
        # Strip any embedded framework markers from prior assistant turns so
        # the summarizer doesn't see its own scaffolding
        content = MARKER_PATTERN.sub("", content).strip()
        if not content:
            continue
        # Risk-gate approval / cancellation / resume replies are also
        # scaffolding (not facts) — skip them so they don't accumulate in the
        # summarizer's context across re-hold cycles.
        if role == "assistant" and content[:1] in ("✅", "❌"):
            continue
        if len(content) > 1500:
            content = content[:1500] + "…"
        lines.append(f"{role.upper()}: {content}")
    if latest_user_text:
        lines.append(f"USER: {latest_user_text}")
    return "\n\n".join(lines)


def _wrap_with_marker(
    body: str,
    framework_id: str,
    mode: str,
    project_nexus: str | None = None,
    one_run_profile: str | None = None,
) -> str:
    """Append the eliciting marker on its own line at the end of the message."""
    return (
        f"{body.rstrip()}\n\n"
        f"{elicitation_marker(framework_id, mode, project_nexus, one_run_profile)}"
    )


def elicitation_marker(
    framework_id: str,
    mode: str,
    project_nexus: str | None = None,
    one_run_profile: str | None = None,
) -> str:
    """The eliciting-state marker for a framework/mode. Public so the Phase 2
    task gate can re-attach it to an approval reply and keep the elicitation
    flow alive across an irreversible-deliverable hold."""
    fw_id = framework_id[:-3] if framework_id.endswith(".md") else framework_id
    marker = MARKER_TEMPLATE.format(
        framework_id=fw_id, mode=mode or "", state=ELICITING_STATE)
    if project_nexus is None and one_run_profile is None:
        return marker
    context = json.dumps(
        {"project_nexus": project_nexus, "one_run_profile": one_run_profile},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    token = base64.urlsafe_b64encode(context).decode("ascii").rstrip("=")
    return marker[:-4] + f"/{token} -->"
