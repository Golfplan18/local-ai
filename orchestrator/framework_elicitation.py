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
import hashlib
import hmac
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
)
from framework_preflight import (
    FrameworkPreflightError,
    MECHANICAL_REDIRECTS,
    PreparedFramework,
    prepare_framework_execution,
    prepared_input_context,
    reuse_prepared_framework,
)


# ---------- Marker convention ----------

ELICITATION_SLOT = "sidebar"  # small model — same slot as drift check + mode select

MARKER_PATTERN = re.compile(
    r"<!--\s*ora-framework:\s*([A-Za-z0-9_\-\.]+)/([A-Za-z0-9_\-]+)/"
    r"([A-Za-z0-9_\-]+)/([A-Za-z0-9_\-]+)/([0-9a-f]{64})\s*-->",
)
MARKER_CANDIDATE_PATTERN = re.compile(
    r"<!--\s*ora-framework:\s*.*?-->", re.DOTALL,
)
# Retained as a legacy display/test fixture only.  Values produced from this
# unsigned template are candidates that ``is_continuation`` explicitly
# rejects; runtime code must call ``elicitation_marker``.
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
    "context_source_inventory",
    "contributor_bundle",
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
    "optional_context_units",
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
    conversation_id: str | None = None
    authenticated: bool = False


def _marker_key(*, create: bool) -> bytes:
    """Reuse Ora's existing durable server-owned authentication material."""
    try:
        import tool_events as _tool_events
    except ImportError:  # pragma: no cover - package import context
        from orchestrator import tool_events as _tool_events
    if create:
        return _tool_events._approval_auth_key()
    return _tool_events._read_approval_auth_key()


def _marker_signature(
    framework_id: str, mode: str, state: str, token: str, *, create: bool,
) -> str:
    body = f"{framework_id}/{mode}/{state}/{token}".encode("utf-8")
    return hmac.new(_marker_key(create=create), body, hashlib.sha256).hexdigest()


def _decode_execution_context(token: str) -> dict:
    try:
        padding = "=" * (-len(token) % 4)
        value = json.loads(base64.urlsafe_b64decode(token + padding).decode("utf-8"))
    except Exception as exc:
        raise ValueError("framework execution context marker is malformed") from exc
    if not isinstance(value, dict):
        raise ValueError("framework execution context marker schema is invalid")
    required_keys = {
        "conversation_id", "project_nexus", "one_run_profile",
    }
    if not required_keys.issubset(value) or not set(value).issubset(
        required_keys | {"execution_context"}
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
    conversation_id = value.get("conversation_id")
    try:
        if project_nexus is not None:
            from project_meta import validate_nexus
            project_nexus = validate_nexus(project_nexus)
        if one_run_profile is not None:
            from model_profiles import validate_profile_name
            one_run_profile = validate_profile_name(one_run_profile)
        if conversation_id is not None:
            conversation_id = _safe_reference(conversation_id)
            if conversation_id is None:
                raise ValueError("invalid conversation id")
    except (TypeError, ValueError) as exc:
        raise ValueError("framework execution context marker values are invalid") from exc
    return {
        "project_nexus": project_nexus,
        "one_run_profile": one_run_profile,
        "conversation_id": conversation_id,
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
        content = msg.get("content", "") or ""
        candidate = MARKER_CANDIDATE_PATTERN.search(content)
        if not candidate:
            return None
        m = MARKER_PATTERN.search(content)
        if not m or m.span() != candidate.span():
            return ContinuationContext(
                framework_id="unknown", mode="unknown", state="unknown",
                context_error="framework continuation marker is not authenticated",
            )
        try:
            expected = _marker_signature(
                m.group(1), m.group(2), m.group(3), m.group(4), create=False,
            )
        except Exception as exc:
            return ContinuationContext(
                framework_id=m.group(1), mode=m.group(2), state=m.group(3),
                context_error=(
                    "framework continuation authentication is unavailable: "
                    f"{exc}"
                ),
            )
        if not hmac.compare_digest(expected, m.group(5)):
            return ContinuationContext(
                framework_id=m.group(1), mode=m.group(2), state=m.group(3),
                context_error="framework continuation marker authentication failed",
            )
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
            context_error=context_error,
            authenticated=context_error is None,
            **execution_context,
        )
    return None


def _prepare_continuation(
    ctx: ContinuationContext,
    latest_user_text: str,
    conversation_id: str | None,
    current_project_nexus: str | None,
    input_context: dict | None,
    prepared: PreparedFramework | None = None,
) -> tuple[PreparedFramework, dict]:
    if ctx.context_error:
        raise FrameworkPreflightError(ctx.context_error)
    if not ctx.authenticated or ctx.state != ELICITING_STATE:
        raise FrameworkPreflightError(
            "framework continuation is not authenticated server state"
        )
    current_conversation = (
        _safe_reference(conversation_id) if conversation_id is not None else None
    )
    if ctx.conversation_id != current_conversation:
        raise FrameworkPreflightError(
            "framework continuation belongs to a different conversation"
        )
    if ctx.project_nexus != current_project_nexus:
        raise FrameworkPreflightError(
            "the active project changed after elicitation began"
        )
    stored_input = (ctx.execution_context or {}).get("input_context")
    merged_input = dict(stored_input) if isinstance(stored_input, dict) else {}
    # The current server-resolved context is authoritative and carries the
    # complete, freshly selected contributor bundle.  Signed marker context
    # fills continuity gaps but never replaces current explicit choices.
    if isinstance(input_context, dict):
        merged_input.update(input_context)
    if prepared is None:
        prepared = prepare_framework_execution(
            ctx.framework_id,
            latest_user_text,
            requested_mode=ctx.mode,
            project_nexus=ctx.project_nexus,
            one_run_profile=ctx.one_run_profile,
            input_context=merged_input,
        )
    else:
        prepared = reuse_prepared_framework(
            prepared,
            ctx.framework_id,
            latest_user_text,
            requested_mode=ctx.mode,
            project_nexus=ctx.project_nexus,
            one_run_profile=ctx.one_run_profile,
            input_context=merged_input,
        )
    merged_input = prepared_input_context(prepared, merged_input)
    if prepared.mechanical_redirect is not None:
        raise FrameworkPreflightError(
            "a mechanical Framework redirect cannot be continued as elicitation"
        )
    return prepared, merged_input


def _framework_start_boundary(ctx: ContinuationContext, history: list) -> int:
    """Return the signed start index, or refuse an unusable boundary."""
    stored_context = ctx.execution_context or {}
    framework_start = stored_context.get("framework_start")
    if (
        not isinstance(framework_start, int)
        or isinstance(framework_start, bool)
        or framework_start < 0
        or framework_start > len(history or [])
    ):
        raise FrameworkPreflightError(
            "authenticated Framework start boundary is invalid"
        )
    return framework_start


def preflight_continuation(
    history: list,
    latest_user_text: str,
    *,
    conversation_id: str | None,
    current_project_nexus: str | None,
    input_context: dict | None = None,
    prepared: PreparedFramework | None = None,
) -> PreparedFramework | None:
    """Authenticate and preflight a possible continuation without effects."""
    ctx = is_continuation(history)
    if ctx is None:
        return None
    prepared, _ = _prepare_continuation(
        ctx,
        latest_user_text,
        conversation_id,
        current_project_nexus,
        input_context,
        prepared,
    )
    _framework_start_boundary(ctx, history)
    return prepared


def start_elicitation(
    framework_name: str,
    history: list,
    config: dict,
    initial_user_message: str = "",
    conversation_id: str | None = None,
    project_nexus: str | None = None,
    one_run_profile: str | None = None,
    style_context: dict | None = None,
    input_context: dict | None = None,
    images: list | None = None,
    trace_dir: str | None = None,
    conversation_tag: str = "",
    trace_context: dict | None = None,
    prepared: PreparedFramework | None = None,
) -> str:
    """Begin a fresh interactive framework execution.

    framework_name: the name token after /framework (with or without .md)
    history: prior conversation history (so the elicitor sees any preamble)
    config: endpoints config
    initial_user_message: the user's text after the /framework <name> trigger,
        if any. Empty when the user typed only `/framework cff`.

    Returns the assistant message text including the trailing marker.
    """
    try:
        if prepared is None:
            prepared = prepare_framework_execution(
                framework_name,
                initial_user_message,
                project_nexus=project_nexus,
                one_run_profile=one_run_profile,
                input_context=input_context,
            )
        else:
            effective_profile = (
                one_run_profile
                if one_run_profile is not None
                else prepared.one_run_profile
            )
            prepared = reuse_prepared_framework(
                prepared,
                framework_name,
                initial_user_message,
                project_nexus=project_nexus,
                one_run_profile=effective_profile,
                input_context=input_context,
            )
    except FrameworkPreflightError as exc:
        if trace_context is not None:
            trace_context["status"] = "refused"
        return f"[Framework preflight refusal: {exc}]"

    fw = prepared.framework
    if prepared.mechanical_redirect is not None:
        return _mechanical_mode_redirect(
            prepared.canonical_filename, prepared.exact_mode or "",
        ) or f"[Framework preflight refusal: unrecognized mechanical contract]"

    if prepared.exact_mode:
        mode = prepared.exact_mode
        milestone = _first_milestone_for_mode(fw, mode)
    else:
        mode, milestone = _resolve_mode_for_elicitation(
            fw, initial_user_message, config, prepared=prepared,
        )
    if milestone is None:
        return (
            f"[Framework {fw.name!r} has no milestones declared for the requested "
            f"mode. Cannot start elicitation.]"
        )

    if (prepared.canonical_filename, mode) in MECHANICAL_REDIRECTS:
        if trace_context is not None:
            trace_context["status"] = "refused"
        return (
            f"[Framework preflight refusal: mechanical mode {mode!r} must be "
            "selected by an exact first-token identity.]"
        )

    try:
        prepared = reuse_prepared_framework(
            prepared,
            prepared.canonical_filename,
            initial_user_message,
            requested_mode=mode,
            project_nexus=prepared.project_nexus,
            one_run_profile=prepared.one_run_profile,
            input_context=input_context,
        )
    except FrameworkPreflightError as exc:
        if trace_context is not None:
            trace_context["status"] = "refused"
        return f"[Framework preflight refusal: {exc}]"
    project_nexus = prepared.project_nexus
    one_run_profile = prepared.one_run_profile
    input_context = prepared_input_context(prepared, input_context)

    conversation_id = conversation_id or _conversation_id_from_context(
        input_context, style_context,
    )

    return _run_elicitation_turn(
        fw, mode, milestone, history, config,
        latest_user_text=initial_user_message,
        prepared=prepared,
        conversation_id=conversation_id,
        project_nexus=project_nexus,
        one_run_profile=one_run_profile,
        style_context=style_context,
        input_context=input_context,
        images=images,
        trace_dir=trace_dir,
        conversation_tag=conversation_tag,
        trace_context=trace_context,
        framework_start=len(history or []),
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
    prepared: PreparedFramework | None = None,
) -> str:
    """Advance an in-progress framework execution by one turn.

    Reads the conversation, summarizes what's been elicited, and either asks
    the next question or produces the final deliverable.

    ``conversation_id`` (Execution Review Phase 2): binds the irreversible-
    deliverable approval token to THIS conversation, so an approval in one
    conversation can't admit the same framework/mode deliverable in another.
    """
    authenticated_ctx = is_continuation(history or [])
    if authenticated_ctx is None or authenticated_ctx != ctx:
        if trace_context is not None:
            trace_context["status"] = "refused"
        return (
            "[Framework continuation rejected: supplied continuation state "
            "does not match the authenticated Dialogue marker.]"
        )
    ctx = authenticated_ctx
    try:
        prepared, merged_input = _prepare_continuation(
            ctx,
            latest_user_text,
            conversation_id,
            current_project_nexus,
            input_context,
            prepared,
        )
    except FrameworkPreflightError as exc:
        if trace_context is not None:
            trace_context["status"] = "refused"
        return f"[Framework continuation rejected: {exc}.]"

    # The marker is the conversation's existing state carrier. Prefer the
    # first-turn context stored there over the current request so a guided
    # continuation cannot silently drop style, attachments, canvas, privacy,
    # or trace inputs when the browser sends only the new answer.
    stored_context = ctx.execution_context or {}
    try:
        framework_start = _framework_start_boundary(ctx, history)
    except FrameworkPreflightError:
        if trace_context is not None:
            trace_context["status"] = "refused"
        return (
            "[Framework continuation rejected: authenticated Framework start "
            "boundary is invalid.]"
        )
    if "style_context" in stored_context:
        style_context = stored_context["style_context"]
    input_context = merged_input
    if "trace_dir" in stored_context:
        trace_dir = stored_context["trace_dir"]
    if "conversation_tag" in stored_context:
        conversation_tag = stored_context["conversation_tag"]
    if "trace_context" in stored_context:
        stored_trace_context = stored_context["trace_context"]
        if isinstance(trace_context, dict) and isinstance(stored_trace_context, dict):
            for key, value in stored_trace_context.items():
                trace_context.setdefault(key, value)
        elif isinstance(stored_trace_context, dict):
            trace_context = dict(stored_trace_context)

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

    fw = prepared.framework

    milestone = _first_milestone_for_mode(fw, ctx.mode)
    if milestone is None:
        return (
            f"[Mid-framework continuation lost its target: framework {fw.name!r} "
            f"declares no milestones for mode {ctx.mode!r}.]"
        )

    return _run_elicitation_turn(
        fw, ctx.mode, milestone, history, config,
        latest_user_text=latest_user_text,
        prepared=prepared,
        conversation_id=conversation_id,
        project_nexus=ctx.project_nexus,
        one_run_profile=ctx.one_run_profile,
        style_context=style_context,
        input_context=input_context,
        images=images,
        trace_dir=trace_dir,
        conversation_tag=conversation_tag,
        trace_context=trace_context,
        framework_start=framework_start,
    )


# ---------- Per-turn execution ----------

def _run_elicitation_turn(
    fw: Framework,
    mode: str,
    milestone: Milestone,
    history: list,
    config: dict,
    latest_user_text: str,
    prepared: PreparedFramework,
    conversation_id: str | None = None,
    project_nexus: str | None = None,
    one_run_profile: str | None = None,
    style_context: dict | None = None,
    input_context: dict | None = None,
    images: list | None = None,
    trace_dir: str | None = None,
    conversation_tag: str = "",
    trace_context: dict | None = None,
    framework_start: int = 0,
) -> str:
    """One elicitation turn: summarize state, decide next step, emit response."""
    segment_history = list(history or [])[framework_start:]
    profile_resolution = prepared.contract_for(
        mode, milestone.id,
    ).model_profile_resolution
    effective_profile = profile_resolution["selected"]["runtime_name"]
    summary = _ask_summarizer(
        fw, mode, milestone, segment_history, latest_user_text, config,
        config_name=effective_profile,
    )

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
            conversation_id=conversation_id,
            execution_context=_build_execution_context(
                style_context, input_context, images, trace_dir,
                conversation_tag, trace_context,
                framework_start=framework_start,
            ),
        )

    if summary.action == "PRODUCE_DELIVERABLE":
        return _produce_deliverable(fw, mode, milestone, summary, segment_history,
                                    latest_user_text, config,
                                    prepared=prepared,
                                    conversation_id=conversation_id,
                                    project_nexus=project_nexus,
                                    one_run_profile=one_run_profile,
                                    style_context=style_context,
                                    input_context=input_context,
                                    images=images,
                                    trace_dir=trace_dir,
                                    conversation_tag=conversation_tag,
                                    trace_context=trace_context,
                                    framework_start=framework_start)

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
        conversation_id=conversation_id,
        execution_context=_build_execution_context(
            style_context, input_context, images, trace_dir,
            conversation_tag, trace_context,
            framework_start=framework_start,
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
    prepared: PreparedFramework,
    conversation_id: str | None = None,
    project_nexus: str | None = None,
    one_run_profile: str | None = None,
    style_context: dict | None = None,
    input_context: dict | None = None,
    images: list | None = None,
    trace_dir: str | None = None,
    conversation_tag: str = "",
    trace_context: dict | None = None,
    framework_start: int = 0,
) -> str:
    """Hand control to the existing milestone executor with the elicited facts
    as the user input. The result is rendered with format_execution_result.

    The final turn carries NO marker — that signals back to normal chat.
    """
    authoritative_messages = []
    for message in history or []:
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str) and content:
            authoritative_messages.append(content)
    if latest_user_text:
        authoritative_messages.append(latest_user_text)
    authoritative_input = "\n\n--- next user message ---\n\n".join(
        authoritative_messages
    )
    deliverable_input = (
        f"{mode} Produce the milestone deliverable from the user's "
        "authoritative messages below. Preserve their wording and intent; "
        "do not substitute the elicitation model's summary.\n\n"
        f"AUTHORITATIVE USER MESSAGES:\n{authoritative_input}"
    )

    fw_filename = fw.name if fw.name.endswith(".md") else fw.name + ".md"
    try:
        prepared = reuse_prepared_framework(
            prepared,
            fw_filename,
            deliverable_input,
            requested_mode=mode,
            project_nexus=project_nexus,
            one_run_profile=prepared.one_run_profile,
            input_context=input_context,
        )
        input_context = prepared_input_context(prepared, input_context)
    except FrameworkPreflightError as exc:
        if trace_context is not None:
            trace_context["status"] = "refused"
        return f"[Framework preflight refusal: {exc}]"

    from milestone_executor import execute_framework, format_execution_result

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
                "conversation_id": conversation_id,
                "project_nexus": project_nexus,
                "one_run_profile": one_run_profile,
                "execution_context": _build_execution_context(
                    style_context, input_context, images, trace_dir,
                    conversation_tag, trace_context,
                    framework_start=framework_start,
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
            prepared=prepared,
        )
    except Exception as exc:
        return f"[Final deliverable production failed: {exc}]"
    finally:
        try:
            # Phase 3: pass the produced deliverable so the source-read "makes
            # claims" test runs; None when execution failed (no grounded output).
            if not (
                isinstance(trace_context, dict)
                and trace_context.get("status") == "refused"
            ):
                _dl_out = (
                    format_execution_result(result)
                    if result is not None else None
                )
                _rgate.record_route_observed(
                    (conversation_id, _dl_turn_ts or ""),
                    risk_tier=_dl_tier,
                    output_text=_dl_out,
                )
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
    config_name: str | None = None,
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
        get_slot_endpoint(config, ELICITATION_SLOT, config_name=config_name)
        or (get_active_endpoint(config) if config_name is None else None)
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
    fw: Framework,
    initial_user_text: str,
    config: dict,
    *,
    prepared: PreparedFramework,
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
    model_modes = tuple(
        mode for mode in fw.modes
        if any(contract_mode == mode for contract_mode, _ in prepared.contracts)
    )
    mode, _, _ = select_mode(
        fw,
        initial_user_text,
        config,
        allowed_modes=model_modes,
        config_name=(
            prepared.selector_profile_resolution["selected"]["runtime_name"]
        ),
    )
    milestone = _first_milestone_for_mode(fw, mode)
    return (mode, milestone)


def _first_milestone_for_mode(fw: Framework, mode: str) -> Optional[Milestone]:
    ms_list = fw.milestones_by_mode.get(mode, [])
    return ms_list[0] if ms_list else None


def _mechanical_mode_redirect(framework_name: str, mode: str) -> Optional[str]:
    """Surface the matching slash command for mechanical modes; return None
    if the mode is model-driven.

    Uses the same exact registered identity/mode table as preflight, but emits
    a fuller user-facing message (we're at the start of an interactive session, so
    the user explicitly asked for elicitation — be clear that this mode
    isn't elicitation-driven).
    """
    canonical_filename = (
        framework_name if framework_name.endswith(".md")
        else framework_name + ".md"
    )
    slash = MECHANICAL_REDIRECTS.get((canonical_filename, mode))
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
    conversation_id: str | None = None,
    execution_context: dict | None = None,
) -> str:
    """Append the eliciting marker on its own line at the end of the message."""
    marker = elicitation_marker(
        framework_id, mode, project_nexus, one_run_profile,
        conversation_id=conversation_id,
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
    *,
    framework_start: int | None = None,
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
    if framework_start is not None:
        context["framework_start"] = framework_start
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
    conversation_id: str | None = None,
    execution_context: dict | None = None,
) -> str:
    """The eliciting-state marker for a framework/mode. Public so the Phase 2
    task gate can re-attach it to an approval reply and keep the elicitation
    flow alive across an irreversible-deliverable hold."""
    fw_id = framework_id[:-3] if framework_id.endswith(".md") else framework_id
    safe_conversation_id = (
        _safe_reference(conversation_id) if conversation_id is not None else None
    )
    if conversation_id is not None and safe_conversation_id is None:
        raise ValueError("invalid framework elicitation conversation id")
    safe_execution_context = _sanitize_marker_value(execution_context)
    context_payload = {
        "conversation_id": safe_conversation_id,
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
            framework_start = safe_execution_context.get("framework_start")
            if isinstance(framework_start, int) and not isinstance(framework_start, bool):
                bounded["framework_start"] = framework_start
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
            minimal_context = {}
            if isinstance(safe_execution_context, dict):
                framework_start = safe_execution_context.get("framework_start")
                if isinstance(framework_start, int) and not isinstance(framework_start, bool):
                    minimal_context["framework_start"] = framework_start
            if minimal_context:
                context_payload["execution_context"] = minimal_context
            else:
                context_payload.pop("execution_context", None)
            context = json.dumps(
                context_payload,
                sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            ).encode("utf-8")
    token = base64.urlsafe_b64encode(context).decode("ascii").rstrip("=")
    signature = _marker_signature(
        fw_id, mode or "", ELICITING_STATE, token, create=True,
    )
    return (
        f"<!-- ora-framework: {fw_id}/{mode or ''}/{ELICITING_STATE}/"
        f"{token}/{signature} -->"
    )
