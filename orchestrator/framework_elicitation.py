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
from pathlib import Path
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
MARKER_CONTEXT_MAX_BYTES = 8 * 1024

# Attachment bytes and paths are deliberately not marker state.  The marker
# points at the existing submission record instead; continuation rehydrates
# the bytes from that record or from the owned session files it names.
_SAFE_REFERENCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MARKER_DROP_KEYS = frozenset({
    "annotations",
    "attachments",
    "base64",
    "canvas_preview_path",
    "data",
    "data_url",
    "exhibits_submission",
    "image",
    "image_b64",
    "image_bytes",
    "image_data_url",
    "image_path",
    "images",
    "prior_annotations",
    "prior_spatial_representation",
    "spatial_representation",
    "visual_checkpoint_id",
    "visual_native_path",
})
_MARKER_INTERNAL_KEYS = frozenset({
    "_framework_submission_id",
})

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
    execution_context: dict | None = None
    context_error: str | None = None


def _decode_execution_context(token: str | None) -> dict:
    if not token:
        return {
            "project_nexus": None,
            "one_run_profile": None,
            "execution_context": None,
        }
    try:
        padding = "=" * (-len(token) % 4)
        value = json.loads(base64.urlsafe_b64decode(token + padding).decode("utf-8"))
    except Exception as exc:
        raise ValueError("framework execution context marker is malformed") from exc
    if not isinstance(value, dict):
        raise ValueError("framework execution context marker schema is invalid")
    if set(value) not in (
        {"project_nexus", "one_run_profile"},
        {"project_nexus", "one_run_profile", "execution_context"},
    ):
        raise ValueError("framework execution context marker schema is invalid")
    execution_context = value.get("execution_context")
    if execution_context is not None and not isinstance(execution_context, dict):
        raise ValueError("framework execution context marker values are invalid")
    if execution_context is not None:
        # This also scrubs markers written by an older build that carried
        # image payloads.  Those bytes are not trusted state and cannot be
        # used as a continuation attachment source.
        execution_context = _sanitize_marker_value(execution_context)
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
        "execution_context": execution_context,
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
            execution_context = {
                "project_nexus": None,
                "one_run_profile": None,
                "execution_context": None,
            }
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
    style_context: dict | None = None,
    input_context: dict | None = None,
    images: list | None = None,
    trace_dir: str | None = None,
    conversation_tag: str = "",
    trace_context: dict | None = None,
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
        style_context=style_context,
        input_context=input_context,
        images=images,
        trace_dir=trace_dir,
        conversation_tag=conversation_tag,
        trace_context=trace_context,
    )


def continue_elicitation(
    ctx: ContinuationContext,
    history: list,
    config: dict,
    latest_user_text: str = "",
    conversation_id: str | None = None,
    current_project_nexus: str | None = None,
    style_context: dict | None = None,
    input_context: dict | None = None,
    images: list | None = None,
    trace_dir: str | None = None,
    conversation_tag: str = "",
    trace_context: dict | None = None,
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

    # The marker is the conversation's existing state carrier. Prefer the
    # first-turn context stored there over the current request so a guided
    # continuation cannot silently drop style, attachments, canvas, privacy,
    # or trace inputs when the browser sends only the new answer.
    stored_context = ctx.execution_context or {}
    if "style_context" in stored_context:
        style_context = stored_context["style_context"]
    if "input_context" in stored_context:
        input_context = stored_context["input_context"]
    if "trace_dir" in stored_context:
        trace_dir = stored_context["trace_dir"]
    if "conversation_tag" in stored_context:
        conversation_tag = stored_context["conversation_tag"]
    if "trace_context" in stored_context:
        trace_context = stored_context["trace_context"]

    # Attachment bytes never come from the marker.  Rehydrate only from the
    # existing submission record, and only after validating any file paths in
    # that record against this conversation's owned session directories.
    try:
        rehydrated = _rehydrate_submission_context(
            stored_context.get("attachment_state"), conversation_id,
        )
    except Exception as exc:
        # A malformed or stale reference must not turn a continuation into a
        # storage/model crash.  The already-sanitized non-image context above
        # remains usable, and the current turn's image input remains intact.
        print(f"[framework-elicitation] attachment rehydration skipped: {exc}")
        rehydrated = None
    if rehydrated:
        if rehydrated.get("images"):
            images = rehydrated["images"]
        hydrated_input = rehydrated.get("input_context") or {}
        if hydrated_input:
            merged_input = dict(input_context or {})
            merged_input.update(hydrated_input)
            input_context = merged_input

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
        style_context=style_context,
        input_context=input_context,
        images=images,
        trace_dir=trace_dir,
        conversation_tag=conversation_tag,
        trace_context=trace_context,
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
    style_context: dict | None = None,
    input_context: dict | None = None,
    images: list | None = None,
    trace_dir: str | None = None,
    conversation_tag: str = "",
    trace_context: dict | None = None,
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
            execution_context=_build_execution_context(
                style_context, input_context, images, trace_dir,
                conversation_tag, trace_context,
            ),
        )

    if summary.action == "PRODUCE_DELIVERABLE":
        return _produce_deliverable(fw, mode, milestone, summary, history,
                                    latest_user_text, config,
                                    conversation_id=conversation_id,
                                    project_nexus=project_nexus,
                                    one_run_profile=one_run_profile,
                                    style_context=style_context,
                                    input_context=input_context,
                                    images=images,
                                    trace_dir=trace_dir,
                                    conversation_tag=conversation_tag,
                                    trace_context=trace_context)

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
        execution_context=_build_execution_context(
            style_context, input_context, images, trace_dir,
            conversation_tag, trace_context,
        ),
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
    style_context: dict | None = None,
    input_context: dict | None = None,
    images: list | None = None,
    trace_dir: str | None = None,
    conversation_tag: str = "",
    trace_context: dict | None = None,
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
                "execution_context": _build_execution_context(
                    style_context, input_context, images, trace_dir,
                    conversation_tag, trace_context,
                ),
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
            style_context=style_context, input_context=input_context,
            images=images, trace_dir=trace_dir,
            conversation_tag=conversation_tag, trace_context=trace_context,
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
        from boot import (
            call_model,
            get_slot_endpoint,
            get_active_endpoint,
            pack_conversation_history,
        )
    except Exception:
        return None

    endpoint = (
        get_slot_endpoint(config, ELICITATION_SLOT)
        or get_active_endpoint(config)
    )
    if endpoint is None:
        return None

    serialized_history = _serialized_conversation_messages(history, "")
    required_prompt = _build_summarizer_prompt(
        fw, mode, milestone, "", latest_user_text,
    )
    packed_history, _history_budget = pack_conversation_history(
        serialized_history,
        endpoint,
        [
            {
                "role": "system",
                "content": "You are a careful elicitation summarizer.",
            },
            {"role": "user", "content": required_prompt},
        ],
    )
    conversation_text = "\n\n".join(
        message["content"] for message in packed_history
    )
    prompt = _build_summarizer_prompt(
        fw, mode, milestone, conversation_text, latest_user_text,
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
        "PRIOR CONVERSATION:\n"
        f"{conversation_text or '(no prior elicitation facts yet)'}\n\n"
        "CURRENT USER REPLY (required):\n"
        f"USER: {latest_user_text or '(none supplied)'}\n"
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


def _conversation_messages(history: list, latest_user_text: str) -> list[dict]:
    """Return truthful elicitation content with only scaffolding removed."""
    messages = []
    for msg in history:
        if not isinstance(msg, dict):
            continue
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
        cleaned = dict(msg)
        cleaned["role"] = role
        cleaned["content"] = content
        messages.append(cleaned)
    if latest_user_text:
        messages.append({
            "role": "user",
            "content": latest_user_text,
            "_ora_history_segment": "local",
        })
    return messages


def _serialized_conversation_messages(
    history: list,
    latest_user_text: str,
) -> list[dict]:
    """Prepare role-labelled messages for whole-unit capacity packing."""
    serialized = []
    for message in _conversation_messages(history, latest_user_text):
        item = dict(message)
        item["content"] = f"{item['role'].upper()}: {item['content']}"
        serialized.append(item)
    return serialized


def _format_conversation(history: list, latest_user_text: str) -> str:
    """Format the complete eligible conversation without fixed truncation."""
    return "\n\n".join(
        message["content"]
        for message in _serialized_conversation_messages(
            history, latest_user_text,
        )
    )


def _wrap_with_marker(
    body: str,
    framework_id: str,
    mode: str,
    project_nexus: str | None = None,
    one_run_profile: str | None = None,
    execution_context: dict | None = None,
) -> str:
    """Append the eliciting marker on its own line at the end of the message."""
    marker = elicitation_marker(
        framework_id, mode, project_nexus, one_run_profile,
        execution_context=execution_context,
    )
    return f"{body.rstrip()}\n\n{marker}"


def _build_execution_context(
    style_context: dict | None,
    input_context: dict | None,
    images: list | None,
    trace_dir: str | None,
    conversation_tag: str,
    trace_context: dict | None,
) -> dict | None:
    """Return bounded, non-payload state carried by the existing marker."""
    context = {}
    safe_style = _sanitize_marker_value(style_context)
    safe_input = _sanitize_marker_value(input_context)
    if safe_style:
        context["style_context"] = safe_style
    if safe_input:
        context["input_context"] = safe_input

    submission_id = _submission_id_from_context(style_context, input_context)
    conversation_id = _conversation_id_from_context(style_context, input_context)
    if submission_id:
        attachment_state = {"submission_id": submission_id}
        if conversation_id:
            attachment_state["conversation_id"] = conversation_id
        context["attachment_state"] = attachment_state

    safe_trace_dir = _validated_trace_dir(trace_dir)
    if safe_trace_dir is not None:
        context["trace_dir"] = safe_trace_dir
    if conversation_tag:
        context["conversation_tag"] = str(conversation_tag)[:128]
    safe_trace_context = _sanitize_marker_value(trace_context)
    if safe_trace_context:
        context["trace_context"] = safe_trace_context
    return context or None


def _sanitize_marker_value(value, *, depth: int = 0):
    """Copy JSON-like context while dropping attachment payloads/references."""
    if depth > 6:
        return None
    if isinstance(value, dict):
        result = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            key_lower = key.casefold()
            if key_lower in _MARKER_DROP_KEYS or key_lower in _MARKER_INTERNAL_KEYS:
                continue
            child = _sanitize_marker_value(raw_value, depth=depth + 1)
            if child is not None:
                result[key[:128]] = child
        return result
    if isinstance(value, (list, tuple)):
        result = []
        for item in list(value)[:32]:
            child = _sanitize_marker_value(item, depth=depth + 1)
            if child is not None:
                result.append(child)
        return result
    if isinstance(value, str):
        return value[:2048]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:2048]


def _safe_reference(value: object) -> str | None:
    candidate = str(value or "")
    if not _SAFE_REFERENCE_RE.fullmatch(candidate):
        return None
    return candidate


def _submission_id_from_context(*contexts: dict | None) -> str | None:
    for context in contexts:
        if not isinstance(context, dict):
            continue
        candidate = context.get("_framework_submission_id")
        if candidate is None:
            candidate = context.get("submission_id")
        if candidate is None and isinstance(context.get("exhibits_submission"), dict):
            candidate = context["exhibits_submission"].get("submission_id")
        safe = _safe_reference(candidate)
        if safe:
            return safe
    return None


def _conversation_id_from_context(*contexts: dict | None) -> str | None:
    for context in contexts:
        if not isinstance(context, dict):
            continue
        candidate = _safe_reference(context.get("conversation_id"))
        if candidate:
            return candidate
    return None


def _validated_trace_dir(trace_dir: str | None) -> str | None:
    """Keep trace continuity only for an existing owned trace directory."""
    if not trace_dir:
        return None
    try:
        try:
            from pipeline_trace import _validated_existing_trace_dir
        except ImportError:
            from orchestrator.pipeline_trace import _validated_existing_trace_dir
        return str(_validated_existing_trace_dir(trace_dir))
    except Exception:
        # Trace continuity is optional; an untrusted/stale path is dropped.
        return None


def _raw_submission_root() -> Path:
    try:
        import runtime_paths as rp
    except ImportError:
        from orchestrator import runtime_paths as rp
    return Path(rp.CONVERSATIONS_STR) / "raw"


def _session_root_for_conversation(conversation_id: str) -> Path:
    try:
        import runtime_paths as rp
    except ImportError:
        from orchestrator import runtime_paths as rp
    return Path(rp.ORA_HOME) / "sessions" / conversation_id


def _load_submission_record(
    submission_id: object, conversation_id: str | None,
) -> dict | None:
    """Load one existing pending/processed record without trusting its path."""
    safe_id = _safe_reference(submission_id)
    if not safe_id:
        return None
    expected_conversation = _safe_reference(conversation_id)
    root = _raw_submission_root()
    for state in ("pending", "processed"):
        directory = root / state
        candidate = directory / f"{safe_id}.json"
        try:
            if candidate.is_symlink() or not candidate.is_file():
                continue
            if not _within_base(candidate, root):
                continue
            with candidate.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
            if not isinstance(payload, dict) or payload.get("submission_id") != safe_id:
                continue
            record_conversation = _safe_reference(payload.get("conversation_id"))
            if expected_conversation and record_conversation != expected_conversation:
                continue
            return payload
        except Exception as exc:
            print(f"[framework-elicitation] submission record skipped: {exc}")
    return None


def _within_base(path: Path, base: Path) -> bool:
    try:
        try:
            import runtime_paths as rp
        except ImportError:
            from orchestrator import runtime_paths as rp
        return rp.within_base(path, base)
    except Exception:
        return False


def _owned_file(raw_path: object, root: Path) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path or not os.path.isabs(raw_path):
        return None
    candidate = Path(raw_path)
    try:
        if candidate.is_symlink() or not candidate.is_file():
            return None
        resolved_root = root.resolve(strict=False)
        resolved_candidate = candidate.resolve(strict=True)
        if not _within_base(resolved_candidate, resolved_root):
            return None
        return resolved_candidate
    except Exception:
        return None


def _images_from_attachment_record(record: dict) -> list[dict]:
    images = []
    for attachment in record.get("attachments") or []:
        if not isinstance(attachment, dict):
            continue
        mime = str(attachment.get("type") or "")
        data_url = attachment.get("data")
        if not mime.startswith("image/") or not isinstance(data_url, str) or not data_url:
            continue
        raw_b64 = data_url.split(",", 1)[-1] if "," in data_url else data_url
        if raw_b64:
            images.append({
                "name": str(attachment.get("name") or "file")[:256],
                "mime": mime[:128],
                "base64": raw_b64,
                "source": "submission",
            })
    return images


def _image_from_owned_file(path: Path, *, name: str, mime: str, source: str) -> dict | None:
    try:
        return {
            "name": name[:256],
            "mime": mime[:128],
            "base64": base64.b64encode(path.read_bytes()).decode("ascii"),
            "source": source,
        }
    except Exception as exc:
        print(f"[framework-elicitation] owned image read skipped: {exc}")
        return None


def _rehydrate_submission_context(
    attachment_state: object, conversation_id: str | None,
) -> dict | None:
    if not isinstance(attachment_state, dict):
        return None
    submission_id = _safe_reference(attachment_state.get("submission_id"))
    if not submission_id:
        return None
    record_conversation = _safe_reference(attachment_state.get("conversation_id"))
    if conversation_id and record_conversation and record_conversation != _safe_reference(conversation_id):
        return None
    record = _load_submission_record(submission_id, conversation_id or record_conversation)
    if not record:
        return None
    record_conversation = _safe_reference(record.get("conversation_id"))
    if not record_conversation:
        return None
    session_root = _session_root_for_conversation(record_conversation)
    upload_root = session_root / "uploads"
    canvas_root = session_root / "canvas"
    images = _images_from_attachment_record(record)
    input_context = {}

    image_path = _owned_file(record.get("image_path"), upload_root)
    if image_path:
        image = _image_from_owned_file(
            image_path, name=image_path.name,
            mime=str(record.get("image_mime") or "image/png"), source="upload",
        )
        if image:
            images.append(image)
            input_context["image_path"] = str(image_path)

    canvas_path = _owned_file(record.get("canvas_preview_path"), canvas_root)
    if canvas_path:
        image = _image_from_owned_file(
            canvas_path, name=canvas_path.name, mime="image/png",
            source=("v3_canvas_preview" if record.get("visual_checkpoint_id")
                    else "legacy_canvas_preview"),
        )
        if image:
            images.append(image)
            if "image_path" not in input_context:
                input_context["image_path"] = str(canvas_path)
                input_context["image_source"] = "canvas_preview"

    if record.get("visual_checkpoint_id"):
        checkpoint_id = _safe_reference(record.get("visual_checkpoint_id"))
        if checkpoint_id:
            input_context["visual_checkpoint_id"] = checkpoint_id

    try:
        spatial_raw = record.get("spatial_raw")
        if isinstance(spatial_raw, str) and spatial_raw:
            spatial = json.loads(spatial_raw)
            if isinstance(spatial, dict):
                input_context["spatial_representation"] = spatial
    except Exception:
        pass
    try:
        annotations_raw = record.get("annotations_raw")
        if isinstance(annotations_raw, str) and annotations_raw:
            annotations = json.loads(annotations_raw)
            input_context["annotations"] = (
                {"annotations": annotations}
                if isinstance(annotations, list) else annotations
            )
    except Exception:
        pass

    return {"images": images, "input_context": input_context}


def elicitation_marker(
    framework_id: str,
    mode: str,
    project_nexus: str | None = None,
    one_run_profile: str | None = None,
    execution_context: dict | None = None,
) -> str:
    """The eliciting-state marker for a framework/mode. Public so the Phase 2
    task gate can re-attach it to an approval reply and keep the elicitation
    flow alive across an irreversible-deliverable hold."""
    fw_id = framework_id[:-3] if framework_id.endswith(".md") else framework_id
    marker = MARKER_TEMPLATE.format(
        framework_id=fw_id, mode=mode or "", state=ELICITING_STATE)
    if (
        project_nexus is None
        and one_run_profile is None
        and not execution_context
    ):
        return marker
    safe_execution_context = _sanitize_marker_value(execution_context)
    context_payload = {
        "project_nexus": project_nexus,
        "one_run_profile": one_run_profile,
    }
    if safe_execution_context:
        context_payload["execution_context"] = safe_execution_context
    context = json.dumps(
        context_payload,
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    if len(context) > MARKER_CONTEXT_MAX_BYTES:
        # Preserve the reference and the smallest useful context first.  The
        # marker is a transport envelope, not a second attachment store.
        bounded = {}
        if isinstance(safe_execution_context, dict):
            attachment_state = safe_execution_context.get("attachment_state")
            if attachment_state:
                bounded["attachment_state"] = attachment_state
            for key in ("style_context", "input_context", "trace_context"):
                value = safe_execution_context.get(key)
                if value is None:
                    continue
                candidate = dict(context_payload)
                candidate["execution_context"] = dict(bounded, **{key: value})
                encoded = json.dumps(
                    candidate, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
                if len(encoded) <= MARKER_CONTEXT_MAX_BYTES:
                    bounded[key] = value
            bounded["context_truncated"] = True
        context_payload["execution_context"] = bounded
        context = json.dumps(
            context_payload,
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
        if len(context) > MARKER_CONTEXT_MAX_BYTES:
            context_payload.pop("execution_context", None)
            context = json.dumps(
                context_payload,
                sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            ).encode("utf-8")
    token = base64.urlsafe_b64encode(context).decode("ascii").rstrip("=")
    return marker[:-4] + f"/{token} -->"
