"""Milestone executor — runs a framework as a sequence of milestone-bounded
gear pipeline passes with drift detection at each boundary.

Implements the layered execution model declared in Process Formalization
Framework §2.3 (Milestones Delivered). For each milestone in declared order:

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

import copy
import hashlib
import json
import os
import re
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
    FrameworkParseError,
)
from framework_invocability import resolve_user_invocable_framework
from framework_preflight import (
    FrameworkPreflightError,
    MECHANICAL_REDIRECTS as EXACT_MECHANICAL_REDIRECTS,
    PreparedFramework,
    ResolvedMilestoneContract,
    _consume_first_token,
    is_framework_command_syntax,
    parse_framework_command_bytes,
    prepare_framework_execution,
    prepared_input_context,
    reuse_prepared_framework,
    _thaw_value,
)
from scratch import ScratchSession
import runtime_paths as _rp


MAX_RETRIES = 3
DRIFT_CHECK_SLOT = "sidebar"  # small model, cheap
MODE_SELECT_SLOT = "sidebar"  # routing classifier; small model is sufficient

# ---------- Result types ----------

@dataclass
class MilestoneResult:
    milestone_id: str
    name: str
    deliverable: str
    drift_status: str  # "IN_SCOPE", "DRIFT_DETECTED", or "DRIFT_CHECK_SKIPPED"
    drift_reasoning: str
    attempts: int
    completed: bool = True
    deliverable_path: str = ""


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
    terminal_state: str = "succeeded"
    failed_milestone_id: Optional[str] = None
    resume_available: bool = False
    recovery_path: Optional[str] = None
    resumed: bool = False


class MilestoneExecutionError(Exception):
    """Raised when a milestone fails after MAX_RETRIES attempts."""

    def __init__(
        self,
        message: str,
        *,
        milestone_id: Optional[str] = None,
        terminal_state: str = "failed",
        candidate: str = "",
    ) -> None:
        super().__init__(message)
        self.milestone_id = milestone_id
        self.terminal_state = terminal_state
        self.candidate = candidate


class FrameworkPipelineError(Exception):
    """A Gear pipeline returned an unshippable Framework candidate."""

    def __init__(
        self,
        message: str,
        *,
        candidate: str = "",
        terminal_state: str = "failed",
    ) -> None:
        super().__init__(message)
        self.candidate = candidate
        self.terminal_state = terminal_state


# ---------- Public API ----------

# ─── Framework → configuration routing (Chunk 3) ─────────────────────────
#
# config/framework-routing.json maps framework names to default named
# configurations from config/configurations/. When a framework is invoked
# without an explicit config_name, this layer supplies the framework's
# preferred configuration. When the lookup misses or the file is missing,
# the Router auto-derives from execution_context (see DEFAULT_CONFIG_FOR
# _CONTEXT in router.py).
#
# The mapping lives in JSON (not framework YAML frontmatter) per the user's
# standing preference: YAML stays minimal — navigation + RAG triggers only.

_FRAMEWORK_ROUTING_CACHE: Optional[dict] = None


def _load_framework_routing() -> dict:
    """Load (and cache) config/framework-routing.json. Returns {} on missing
    file or parse failure — callers treat that as "no per-framework default."
    """
    global _FRAMEWORK_ROUTING_CACHE
    if _FRAMEWORK_ROUTING_CACHE is not None:
        return _FRAMEWORK_ROUTING_CACHE
    from pathlib import Path
    import json as _json
    path = Path(__file__).resolve().parent.parent / "config" / "framework-routing.json"
    if not path.exists():
        _FRAMEWORK_ROUTING_CACHE = {}
        return _FRAMEWORK_ROUTING_CACHE
    try:
        with open(path) as f:
            _FRAMEWORK_ROUTING_CACHE = _json.load(f) or {}
    except Exception as exc:  # pragma: no cover
        print(f"[milestone_executor] framework-routing.json load failed: {exc}")
        _FRAMEWORK_ROUTING_CACHE = {}
    return _FRAMEWORK_ROUTING_CACHE


def reset_framework_routing_cache() -> None:
    """Clear the framework-routing cache. Called by tests; also useful when
    the routing file is edited at runtime."""
    global _FRAMEWORK_ROUTING_CACHE
    _FRAMEWORK_ROUTING_CACHE = None


def _lookup_framework_default_configuration(framework_name: str) -> Optional[str]:
    """Return the configuration name declared as default for a framework,
    or None when no entry exists."""
    routing = _load_framework_routing()
    mappings = routing.get("frameworks", {}) or {}
    entry = mappings.get(framework_name)
    if isinstance(entry, dict):
        return entry.get("default_configuration")
    if isinstance(entry, str):
        # Shorthand: framework_name → configuration_name string
        return entry
    return None


def _resolve_milestone_model_profile(
    *,
    project_nexus: Optional[str],
    process_profile: Optional[str],
    milestone,
    one_run_profile: Optional[str],
) -> dict:
    """Resolve G1.16's five-level profile chain for one exact step.

    ``config_name`` on ``execute_framework`` is the one-run override.  The
    framework-routing entry is the process default and a milestone's optional
    ``Model Profile`` property is the step override.  Keeping the three names
    separate prevents the old implementation from collapsing process and
    one-run authority into one caller-controlled value.
    """
    try:
        from . import model_profiles
    except ImportError:
        import model_profiles  # type: ignore
    return model_profiles.resolve_effective_profile(
        project_nexus=project_nexus,
        process_profile=process_profile,
        step_profile=getattr(milestone, "model_profile", None),
        one_run_profile=one_run_profile,
    )


def _authenticated_project_visual_locks(project_nexus: Optional[str]) -> dict | None:
    """Load the exact project's visual locks for framework context assembly."""
    if not isinstance(project_nexus, str) or not project_nexus.strip():
        return None
    if project_nexus.strip().lower() in ("commons", "general"):
        return None
    try:
        from . import model_profiles, project_meta
    except ImportError:
        import model_profiles  # type: ignore
        import project_meta  # type: ignore
    nexus = project_meta.validate_nexus(project_nexus.strip())
    record = project_meta.read_project_meta(nexus)
    if not record or not record.get("default_model_profile"):
        return None
    return model_profiles.validate_project_binding(record, expected_nexus=nexus)


def _framework_conversation_id(
    explicit: Optional[str], trace_context: Optional[dict],
) -> Optional[str]:
    """Resolve the owning conversation identity without inventing one."""
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    if isinstance(trace_context, dict):
        value = trace_context.get("conversation_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    try:
        try:
            import tool_events as _tool_events
        except ImportError:
            from orchestrator import tool_events as _tool_events
        value = _tool_events.get_turn_context().get("conversation_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    except Exception:
        pass
    return None


def _contract_digest(prepared: PreparedFramework) -> str:
    return "sha256:" + hashlib.sha256(
        prepared.contract_text.encode("utf-8")
    ).hexdigest()


def _resume_identity_payload(
    prepared: PreparedFramework,
    *,
    selected_mode: str,
    effective_input: str,
) -> dict:
    """Return the deterministic admitted identity needed to verify resume."""
    contracts = prepared.framework.milestones_by_mode.get(selected_mode)
    if not contracts:
        raise FrameworkPreflightError(
            "Framework resume identity has no selected milestone contracts"
        )
    return {
        "schema_version": 1,
        "canonical_filename": prepared.canonical_filename,
        "original_input": prepared.original_input,
        "exact_mode": prepared.exact_mode,
        "selected_mode": selected_mode,
        "effective_input": effective_input,
        "project_nexus": prepared.project_nexus,
        "project_profile": prepared.project_profile,
        "one_run_profile": prepared.one_run_profile,
        "selector_profile_resolution": _thaw_value(
            prepared.selector_profile_resolution
        ),
        "input_context": _thaw_value(prepared.input_context),
        "milestone_contracts": [
            {
                "mode": contract.mode,
                "milestone_id": contract.milestone_id,
                "name": contract.name,
                "endpoint_produced": contract.endpoint_produced,
                "methods": [
                    {
                        "id": method.id,
                        "name": method.name,
                        "body": method.body,
                        "legacy": method.legacy,
                    }
                    for method in contract.methods
                ],
                "required_prior": list(contract.required_prior),
                "external_prerequisites": [
                    [key, _thaw_value(value)]
                    for key, value in contract.external_prerequisites
                ],
                "verification_criterion": contract.verification_criterion,
                "output_specification": contract.output_format,
                "gear": contract.gear,
                "gear4_purpose": contract.gear4_purpose,
                "drift_check_question": contract.drift_check_question,
                "conditional_layers": contract.conditional_layers,
                "declared_model_profile": contract.declared_model_profile,
                "model_profile_resolution": _thaw_value(
                    contract.model_profile_resolution
                ),
            }
            for contract in contracts
        ],
    }


def _resume_identity_digest(
    prepared: PreparedFramework,
    *,
    selected_mode: str,
    effective_input: str,
) -> str:
    try:
        encoded = json.dumps(
            _resume_identity_payload(
                prepared,
                selected_mode=selected_mode,
                effective_input=effective_input,
            ),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FrameworkPreflightError(
            "Framework resume identity is not deterministically serializable"
        ) from exc
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _maybe_persist_self_mindspec(framework_name, mode, final_output):
    """Archive MSI-Self and compile one inactive Persona.

    Returns a user-visible status line. ``mind.md`` is never read or written:
    it describes the user, while Persona describes Ora's behavior.
    """
    if framework_name != "mindspec-interview" or mode != "MSI-Self" or not final_output:
        return ""
    try:
        import os as _os
        ora = str(_rp.ORA_HOME)
        archive_path = _os.path.join(ora, "mindspec", "self-spec.md")
        _os.makedirs(_os.path.dirname(archive_path), exist_ok=True)
        _rp.atomic_write_text(archive_path, final_output)
        try:
            try:
                import persona as _persona
            except ImportError:
                from orchestrator import persona as _persona
            personas_dir = _os.path.join(ora, "personas")
            selected = _persona.resolve_persona(personas_dir=personas_dir)
            result = _persona.compile_self_spec(
                final_output, base_id=selected["id"], personas_dir=personas_dir)
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        if not result.get("ok"):
            return (
                "MindSpec was archived, but Persona compilation failed: "
                + str(result.get("error") or "unknown error")
                + ". mind.md was not changed."
            )
        return (
            f"MindSpec was archived and inactive Persona {result['id']!r} "
            "was created. Review or select it in Output Styles; mind.md was not changed."
        )
    except Exception as exc:
        return f"MindSpec archive failed: {exc}"


def execute_framework(
    framework_path: str,
    user_input: str,
    config: Optional[dict] = None,
    execution_id: Optional[str] = None,
    project_nexus: Optional[str] = None,
    config_name: Optional[str] = None,
    trace_dir: Optional[str] = None,
    conversation_tag: str = "",
    trace_context: Optional[dict] = None,
    style_context: Optional[dict] = None,
    input_context: Optional[dict] = None,
    images: Optional[list] = None,
    prepared: Optional[PreparedFramework] = None,
    conversation_id: Optional[str] = None,
    _resume: bool = False,
    _resume_selected_mode: Optional[str] = None,
    _resume_mode_reasoning: Optional[str] = None,
) -> FrameworkExecutionResult:
    """Execute a framework on the given user input.

    Returns a FrameworkExecutionResult. On success, scratch is cleaned up.
    On a normal failure, scratch is preserved for inspection or resume.
    Stealth scratch is removed on every terminal path.

    Multi-mode frameworks (PEF, MOM, Process Formalization, etc.): the
    executor calls ``select_mode`` to choose which mode to run, then
    executes only that mode's declared milestones. Selection priority:
    exact first-token prefix in user input → LLM-based routing classifier →
    first declared mode. The chosen mode
    and the reasoning are recorded on the result and emitted with the
    oversight events.

    project_nexus: optional. When set, framework-level oversight events
    are emitted with the project context for the meta-layer's Layer B
    routing (see Reference — Meta-Layer Architecture). When None, events
    fire with project_nexus=None and the oversight router filters them out.

    config_name (install Chunk 3): optional named configuration from
    config/configurations/<name>.json. When None, the framework's default
    configuration is looked up via config/framework-routing.json; if no
    mapping exists, falls through to the Router's auto-derivation from
    execution_context (interactive → user-pipeline). When provided, the
    name takes precedence — used by ``/framework <name> --config X ...``
    invocations and by multi-step orchestration chains (when those land)
    that specify per-step configuration.
    """
    # This is the direct-executor boundary.  It deliberately runs before
    # configuration/persona loading, mode selection, trace writes, scratch,
    # oversight events, or any model-capable import path below.
    if prepared is None:
        prepared = prepare_framework_execution(
            framework_path,
            user_input,
            project_nexus=project_nexus,
            one_run_profile=config_name,
            input_context=input_context,
        )
    elif user_input != prepared.original_input:
        reuse_kwargs = dict(
            requested_mode=prepared.exact_mode,
            project_nexus=project_nexus,
            input_context=input_context,
        )
        if config_name is not None:
            reuse_kwargs["one_run_profile"] = config_name
        prepared = reuse_prepared_framework(
            prepared,
            framework_path,
            user_input,
            **reuse_kwargs,
        )
    else:
        reuse_kwargs = dict(
            project_nexus=project_nexus,
            input_context=input_context,
        )
        if config_name is not None:
            reuse_kwargs["one_run_profile"] = config_name
        prepared = reuse_prepared_framework(
            prepared,
            framework_path,
            user_input,
            **reuse_kwargs,
        )
    project_nexus = prepared.project_nexus
    config_name = prepared.one_run_profile
    input_context = prepared_input_context(prepared, input_context)
    fw = prepared.framework
    if trace_context is not None:
        trace_context["framework_id"] = fw.name
        if prepared.exact_mode:
            trace_context["mode"] = prepared.exact_mode

    if prepared.mechanical_redirect is not None:
        return _build_mechanical_redirect(
            fw,
            prepared.exact_mode or "",
            prepared.mode_reasoning or "exact mechanical contract",
            prepared.effective_input,
            execution_id=execution_id,
            slash_form=prepared.mechanical_redirect,
        )

    # Lazy import of boot.py to avoid circular issues during testing.
    from boot import load_routing_config

    persona_resolution = None
    try:
        try:
            from persona import resolve_persona
        except ImportError:
            from orchestrator.persona import resolve_persona
        persona_resolution = resolve_persona(project_nexus=project_nexus)
    except Exception as exc:
        print(f"[persona] framework Persona unavailable: {exc}",
              file=sys.stderr, flush=True)
        persona_resolution = None

    # Lazy import of oversight events — keeps the executor usable
    # standalone when no oversight infrastructure is loaded.
    try:
        from oversight_events import emit as emit_oversight_event
    except ImportError:
        def emit_oversight_event(_evt):  # type: ignore
            return None

    if config is None:
        config = load_routing_config()

    project_visual_locks = _authenticated_project_visual_locks(project_nexus)

    if fw.is_multi_mode:
        if _resume:
            if (
                not isinstance(_resume_selected_mode, str)
                or _resume_selected_mode not in fw.modes
            ):
                raise FrameworkPreflightError(
                    "Framework resume refused because its selected mode is invalid"
                )
            selected_mode = _resume_selected_mode
            mode_reasoning = (
                _resume_mode_reasoning
                or "stored admitted Framework mode selection"
            )
            effective_input = prepared.effective_input
        elif prepared.exact_mode:
            selected_mode = prepared.exact_mode
            mode_reasoning = prepared.mode_reasoning or "exact mode"
            effective_input = prepared.effective_input
        else:
            model_modes = tuple(
                mode for mode in fw.modes
                if any(contract_mode == mode for contract_mode, _ in prepared.contracts)
            )
            selected_mode, mode_reasoning, effective_input = select_mode(
                fw, user_input, config, allowed_modes=model_modes,
                config_name=(
                    prepared.selector_profile_resolution["selected"]["runtime_name"]
                ),
            )
        if trace_context is not None:
            trace_context["mode"] = selected_mode
        milestones = fw.milestones_by_mode.get(selected_mode, [])
        if trace_dir:
            try:
                import trace_debug as _tdbg
            except ImportError:
                from orchestrator import trace_debug as _tdbg
            _tdbg.record_contract_snapshot(
                trace_dir, _tdbg.framework_contract_bundle(fw, milestones, selected_mode=selected_mode))
        if not milestones:
            raise FrameworkParseError(
                f"Framework {fw.name!r} has no milestones declared for mode "
                f"{selected_mode!r}."
            )
        if (prepared.canonical_filename, selected_mode) in EXACT_MECHANICAL_REDIRECTS:
            # Mechanical modes must be chosen explicitly so the exact pair can
            # be authenticated before mode-selection model spend.
            raise FrameworkPreflightError(
                f"Framework preflight refused {prepared.canonical_filename}: "
                f"mechanical mode {selected_mode!r} must be the exact first token"
            )
    else:
        if _resume and _resume_selected_mode not in (None, "all"):
            raise FrameworkPreflightError(
                "Framework resume refused because its selected mode changed"
            )
        selected_mode = "all"
        mode_reasoning = "single-mode framework"
        effective_input = prepared.effective_input
        if trace_context is not None:
            trace_context["mode"] = selected_mode
        milestones = fw.milestones_by_mode.get("all", [])
        if trace_dir:
            try:
                import trace_debug as _tdbg
            except ImportError:
                from orchestrator import trace_debug as _tdbg
            _tdbg.record_contract_snapshot(
                trace_dir, _tdbg.framework_contract_bundle(fw, milestones, selected_mode=selected_mode))
        if not milestones:
            raise FrameworkParseError(
                f"Framework {fw.name!r} declared no milestones to execute."
            )

    conversation_id = _framework_conversation_id(conversation_id, trace_context)
    if trace_context is not None and conversation_id:
        trace_context["conversation_id"] = conversation_id

    scratch: Optional[ScratchSession] = None
    setup_error: Optional[BaseException] = None
    try:
        if _resume:
            if not execution_id:
                raise ValueError("resume requires an execution id")
            scratch = ScratchSession.attach(execution_id)
            resume_manifest = scratch.manifest()
            expected = {
                "framework_name": fw.name,
                "canonical_filename": prepared.canonical_filename,
                "selected_mode": selected_mode,
                "contract_digest": _contract_digest(prepared),
                "original_input": prepared.original_input,
                "effective_input": effective_input,
                "exact_mode": prepared.exact_mode,
                "project_nexus": prepared.project_nexus,
                "project_profile": prepared.project_profile,
                "one_run_profile": prepared.one_run_profile,
                "input_context": _thaw_value(prepared.input_context),
                "resume_identity_digest": _resume_identity_digest(
                    prepared,
                    selected_mode=selected_mode,
                    effective_input=effective_input,
                ),
            }
            mismatched = [
                key for key, value in expected.items()
                if resume_manifest.get(key) != value
            ]
            if mismatched:
                raise FrameworkPreflightError(
                    "Framework resume refused because the admitted run identity "
                    f"changed: {', '.join(mismatched)}"
                )
            if resume_manifest.get("conversation_tag") == "stealth":
                raise FrameworkPreflightError(
                    "Stealth Framework runs cannot be resumed"
                )
            if resume_manifest.get("original_input") != user_input:
                raise FrameworkPreflightError(
                    "Framework resume refused because the original input changed"
                )
            scratch.mark_resumed()
        else:
            scratch = ScratchSession.create(
                fw.name,
                execution_id=execution_id,
                conversation_id=conversation_id,
                conversation_tag=conversation_tag,
            )
            scratch.record_run(
                canonical_filename=prepared.canonical_filename,
                contract_digest=_contract_digest(prepared),
                original_input=prepared.original_input,
                effective_input=effective_input,
                exact_mode=prepared.exact_mode,
                selected_mode=selected_mode,
                mode_reasoning=mode_reasoning,
                project_nexus=project_nexus,
                project_profile=prepared.project_profile,
                one_run_profile=config_name,
                input_context=_thaw_value(prepared.input_context),
                resume_identity_digest=_resume_identity_digest(
                    prepared,
                    selected_mode=selected_mode,
                    effective_input=effective_input,
                ),
            )
    except BaseException as exc:
        if scratch is None:
            raise
        setup_error = exc

    if scratch is None:
        raise RuntimeError("Framework scratch lifecycle did not initialize")

    if trace_context is not None:
        trace_context["execution_id"] = scratch.execution_id
    started = time.time()
    results: list[MilestoneResult] = []
    current_milestone_id: Optional[str] = None
    parent_trace_ref = None
    completed_ids: set[str] = set()
    declared_ids = [milestone.id for milestone in milestones]

    try:
        if setup_error is not None:
            raise setup_error
        if trace_dir:
            try:
                import pipeline_trace
                parent_trace_ref = pipeline_trace.trace_ref_for_dir(trace_dir)
            except ImportError:
                from orchestrator import pipeline_trace
                parent_trace_ref = pipeline_trace.trace_ref_for_dir(trace_dir)

        completed_ids = set(scratch.completed_milestone_ids())
        unknown_completed = completed_ids - set(declared_ids)
        expected_prefix = declared_ids[:len(completed_ids)]
        if unknown_completed or expected_prefix != [
            milestone_id for milestone_id in declared_ids
            if milestone_id in completed_ids
        ]:
            raise FrameworkPreflightError(
                "Framework resume refused because completed milestone state is "
                "not a valid declared prefix"
            )

        emit_oversight_event({
            "event_type": "FrameworkStarted",
            "framework_id": fw.name,
            "mode": selected_mode,
            "mode_reasoning": mode_reasoning,
            "execution_id": scratch.execution_id,
            "project_nexus": project_nexus,
            "user_input": effective_input,
            "resumed": bool(_resume),
            "ephemeral_handoff": {
                "kind": "framework_scratch_manifest",
                "path": scratch.manifest_path,
                "lifetime": "until terminal lifecycle handling",
            },
        })

        for milestone in milestones:
            current_milestone_id = milestone.id
            contract = prepared.contract_for(selected_mode, milestone.id)
            if milestone.id in completed_ids:
                metadata = scratch.milestone_result_metadata(milestone.id)
                if metadata.get("drift_status") != "IN_SCOPE":
                    raise FrameworkPreflightError(
                        f"Framework resume refused invalid completed state for {milestone.id}"
                    )
                completed_deliverable = scratch.read_milestone(milestone.id)
                completed_digest = "sha256:" + hashlib.sha256(
                    completed_deliverable.encode("utf-8")
                ).hexdigest()
                if metadata.get("deliverable_digest") != completed_digest:
                    raise FrameworkPreflightError(
                        "Framework resume refused because completed milestone "
                        f"{milestone.id} changed"
                    )
                results.append(MilestoneResult(
                    milestone_id=milestone.id,
                    name=metadata.get("name") or milestone.name,
                    deliverable=completed_deliverable,
                    drift_status="IN_SCOPE",
                    drift_reasoning=metadata.get("drift_reasoning") or "",
                    attempts=int(metadata.get("attempts") or 1),
                    completed=True,
                    deliverable_path=scratch.milestone_path(milestone.id),
                ))
                continue

            profile_resolution = contract.model_profile_resolution
            effective_profile = profile_resolution["selected"]["runtime_name"]
            if trace_context is not None:
                trace_context["model_profile_resolution"] = _thaw_value(
                    profile_resolution
                )
                trace_context.setdefault("model_profile_resolutions", []).append(
                    _thaw_value(profile_resolution)
                )
            result = _run_milestone(
                fw, milestone, contract,
                scratch, effective_input, config,
                config_name=effective_profile, parent_trace_dir=trace_dir,
                parent_trace_ref=parent_trace_ref,
                selected_mode=selected_mode,
                project_model_locks=project_visual_locks,
                conversation_tag=conversation_tag,
                trace_context=trace_context,
                persona_resolution=persona_resolution,
                style_context=style_context,
                input_context=input_context,
                images=images)
            results.append(result)

            if result.drift_status != "IN_SCOPE":
                raise MilestoneExecutionError(
                    f"Milestone {milestone.id} stopped at the boundary with "
                    f"{result.drift_status}: {result.drift_reasoning}",
                    milestone_id=milestone.id,
                    terminal_state=result.drift_status.lower(),
                    candidate=result.deliverable,
                )

            emit_oversight_event({
                "event_type": "MilestoneComplete",
                "framework_id": fw.name,
                "mode": selected_mode,
                "execution_id": scratch.execution_id,
                "milestone_id": milestone.id,
                "milestone_name": milestone.name,
                "deliverable_path": result.deliverable_path,
                "deliverable_location": {
                    "kind": "ephemeral_framework_handoff",
                    "path": result.deliverable_path,
                    "lifetime": "through synchronous event dispatch",
                },
                "drift_status": result.drift_status,
                "drift_reasoning": result.drift_reasoning,
                "project_nexus": project_nexus,
                "model_profile": profile_resolution["selected"],
            })

        final_output = results[-1].deliverable if results else ""
        persistence_notice = _maybe_persist_self_mindspec(
            fw.name, selected_mode, final_output)
        if persistence_notice:
            final_output = final_output.rstrip() + "\n\n---\n\n" + persistence_notice
        final_output_path = scratch.write_final_output(final_output)
        scratch.mark_complete()

        emit_oversight_event({
            "event_type": "FrameworkComplete",
            "framework_id": fw.name,
            "mode": selected_mode,
            "execution_id": scratch.execution_id,
            "final_output_path": final_output_path,
            "final_output_location": {
                "kind": "ephemeral_framework_handoff",
                "path": final_output_path,
                "lifetime": "through synchronous event dispatch",
            },
            "milestones": [
                {
                    "milestone_id": result.milestone_id,
                    "name": result.name,
                    "drift_status": result.drift_status,
                    "attempts": result.attempts,
                    "deliverable_path": result.deliverable_path,
                }
                for result in results
            ],
            "project_nexus": project_nexus,
            "success": True,
            "terminal_state": "succeeded",
        })

        if conversation_tag != "stealth":
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
            terminal_state="succeeded",
            resumed=bool(_resume),
        )
    except BaseException as exc:
        failed_milestone_id = (
            getattr(exc, "milestone_id", None)
            or current_milestone_id
            or next((mid for mid in declared_ids if mid not in completed_ids), None)
            or "unknown"
        )
        terminal_state = getattr(exc, "terminal_state", "failed")
        candidate = getattr(exc, "candidate", "")
        candidate_path = ""
        if isinstance(candidate, str) and candidate.strip():
            candidate_path = scratch.write_unaccepted_candidate(
                failed_milestone_id, candidate,
            )
        scratch.mark_failed(
            milestone_id=failed_milestone_id,
            reason=f"{type(exc).__name__}: {exc}",
            terminal_state=terminal_state,
        )
        recovery_path = None if conversation_tag == "stealth" else scratch.folder
        event_error = ""
        try:
            emit_oversight_event({
                "event_type": "MilestoneBlocked",
                "framework_id": fw.name,
                "mode": selected_mode,
                "execution_id": scratch.execution_id,
                "milestone_id": failed_milestone_id,
                "block_reason": str(exc),
                "block_evidence": candidate_path,
                "terminal_state": terminal_state,
                "recovery_path": recovery_path,
                "project_nexus": project_nexus,
            })
            emit_oversight_event({
                "event_type": "FrameworkComplete",
                "framework_id": fw.name,
                "mode": selected_mode,
                "execution_id": scratch.execution_id,
                "final_output_path": None,
                "recovery_path": recovery_path,
                "milestones": [
                    {
                        "milestone_id": result.milestone_id,
                        "name": result.name,
                        "drift_status": result.drift_status,
                        "attempts": result.attempts,
                        "completed": result.completed,
                        "deliverable_path": result.deliverable_path,
                    }
                    for result in results
                ],
                "project_nexus": project_nexus,
                "success": False,
                "terminal_state": terminal_state,
                "failure_reason": str(exc),
            })
        except Exception as oversight_exc:
            event_error = (
                f"; oversight event delivery also failed: "
                f"{type(oversight_exc).__name__}: {oversight_exc}"
            )
        if not isinstance(exc, Exception):
            raise
        return FrameworkExecutionResult(
            framework_name=fw.name,
            execution_id=scratch.execution_id,
            user_input=effective_input,
            milestones=results,
            final_output="",
            success=False,
            failure_reason=f"{exc}{event_error}",
            duration_seconds=time.time() - started,
            mode=selected_mode,
            mode_reasoning=mode_reasoning,
            terminal_state=terminal_state,
            failed_milestone_id=failed_milestone_id,
            resume_available=(conversation_tag != "stealth"),
            recovery_path=recovery_path,
            resumed=bool(_resume),
        )
    finally:
        if conversation_tag == "stealth":
            scratch.cleanup()


# ---------- Per-milestone execution ----------

def _run_milestone(
    framework: Framework,
    milestone: Milestone,
    contract: ResolvedMilestoneContract,
    scratch: ScratchSession,
    user_input: str,
    config: dict,
    config_name: Optional[str] = None,
    parent_trace_dir: Optional[str] = None,
    parent_trace_ref: Optional[str] = None,
    selected_mode: Optional[str] = None,
    project_model_locks: Optional[dict] = None,
    conversation_tag: str = "",
    trace_context: Optional[dict] = None,
    persona_resolution: Optional[dict] = None,
    style_context: Optional[dict] = None,
    input_context: Optional[dict] = None,
    images: Optional[list] = None,
) -> MilestoneResult:
    """Execute a single milestone with retry. Returns a MilestoneResult.

    Raises MilestoneExecutionError on 3rd failure.
    """
    if (
        milestone.id != contract.milestone_id
        or milestone.gear != contract.gear
    ):
        raise FrameworkPreflightError(
            "Framework milestone execution does not match its admitted contract"
        )
    handoff = _build_handoff_packet(
        framework, milestone, contract, scratch, user_input,
    )

    last_exception: Optional[Exception] = None
    last_candidate = ""
    last_terminal_state = "failed"
    for attempt in range(1, MAX_RETRIES + 1):
        child_trace_dir = _start_child_trace(
            parent_trace_dir, handoff, framework, milestone,
            parent_trace_ref, selected_mode, contract.gear,
            conversation_tag, trace_context)
        child_status = "error"
        try:
            deliverable = _run_child_attempt(
                child_trace_dir, parent_trace_ref, handoff, milestone,
                contract,
                config, config_name=config_name, framework_id=framework.name,
                selected_mode=selected_mode,
                project_model_locks=project_model_locks,
                stealth=(conversation_tag == "stealth"),
                persona_resolution=persona_resolution,
                style_context=style_context,
                input_context=input_context,
                images=images)
            _drift_trace_token, _drift_tool_token = _bind_trace_context(
                child_trace_dir, stealth=(conversation_tag == "stealth"),
                surface="framework")
            try:
                drift_status, drift_reasoning = _run_drift_check(
                    milestone, deliverable, user_input, config,
                    config_name=config_name,
                )
            finally:
                _reset_trace_context(_drift_trace_token, _drift_tool_token)
            completed = drift_status == "IN_SCOPE"
            metadata = {
                "name": milestone.name,
                "drift_status": drift_status,
                "drift_reasoning": drift_reasoning,
                "attempts": attempt,
                "deliverable_digest": "sha256:" + hashlib.sha256(
                    deliverable.encode("utf-8")
                ).hexdigest(),
            }
            if completed:
                deliverable_path = scratch.write_milestone(
                    milestone.id, deliverable, result_metadata=metadata,
                )
            else:
                deliverable_path = scratch.write_unaccepted_candidate(
                    milestone.id, deliverable,
                )
            if child_trace_dir:
                try:
                    try:
                        import pipeline_trace as _pt_terminal
                    except ImportError:
                        from orchestrator import pipeline_trace as _pt_terminal
                    _pt_terminal.record_terminal_output(
                        child_trace_dir, deliverable,
                        route=(
                            "framework-milestone-scratch"
                            if completed else "framework-unaccepted-candidate"
                        ),
                        output_target=milestone.id,
                        persisted=bool(deliverable_path),
                    )
                except Exception:
                    pass
            child_status = "completed" if completed else "error"
            return MilestoneResult(
                milestone_id=milestone.id,
                name=milestone.name,
                deliverable=deliverable,
                drift_status=drift_status,
                drift_reasoning=drift_reasoning,
                attempts=attempt,
                completed=completed,
                deliverable_path=deliverable_path,
            )
        except FrameworkPipelineError as exc:
            child_status = "error"
            last_exception = exc
            last_candidate = exc.candidate
            last_terminal_state = exc.terminal_state
            if attempt < MAX_RETRIES:
                time.sleep(2 ** (attempt - 1))
        except Exception as exc:
            child_status = "error"
            last_exception = exc
            last_candidate = getattr(exc, "candidate", last_candidate)
            last_terminal_state = getattr(
                exc, "terminal_state", last_terminal_state,
            )
            # Brief backoff between retries
            if attempt < MAX_RETRIES:
                time.sleep(2 ** (attempt - 1))
        except BaseException:
            child_status = "error"
            raise
        finally:
            _finalize_child_trace(
                child_trace_dir, child_status, framework.name,
                milestone.id, selected_mode, contract.gear,
                parent_trace_ref)

    raise MilestoneExecutionError(
        f"Milestone {milestone.id} ({milestone.name!r}) failed after "
        f"{MAX_RETRIES} attempts. Last error: {last_exception}",
        milestone_id=milestone.id,
        terminal_state=last_terminal_state,
        candidate=last_candidate,
    )


# ---------- Handoff packet construction ----------

def _build_handoff_packet(
    framework: Framework,
    milestone: Milestone,
    contract: ResolvedMilestoneContract,
    scratch: ScratchSession,
    user_input: str,
) -> str:
    """Assemble the structured handoff packet that becomes the user message
    to the gear pipeline. Properties are bound inline to this milestone's path.
    """
    sections = []

    sections.append(f"ORIGINAL USER INPUT:\n{user_input}")
    sections.append("")

    prior_deliverables = scratch.read_all_prior(list(contract.required_prior))
    missing_priors = [
        prior for prior in contract.required_prior
        if prior not in prior_deliverables or prior_deliverables[prior] is None
    ]
    if missing_priors:
        raise FrameworkPreflightError(
            f"Framework preflight refused {framework.name}: "
            f"{contract.mode}.{contract.milestone_id} is missing resolved "
            f"same-run prior deliverable(s): {', '.join(missing_priors)}"
        )
    if contract.required_prior:
        sections.append("PRIOR MILESTONE DELIVERABLES:")
        for mid in contract.required_prior:
            content = prior_deliverables[mid]
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

    sections.append("RESOLVED METHOD INSTRUCTIONS:")
    sections.append("")
    for method in contract.methods:
        heading = "LAYER" if method.legacy else "METHOD"
        sections.append(
            f"## {heading} {method.id}: {method.name} "
            f"(resolved for {milestone.id})"
        )
        sections.append(method.body)
        sections.append("")

    if contract.external_prerequisites:
        sections.append("RESOLVED EXTERNAL PREREQUISITES:")
        for prerequisite_id, value in contract.external_prerequisites:
            sections.append(f"  {prerequisite_id}:")
            sections.append(_indent(str(_thaw_value(value)), "    "))
            sections.append("")

    sections.append("OUTPUT SPECIFICATION:")
    sections.append(contract.output_format)
    sections.append("")

    sections.append("VERIFICATION CRITERION (success target for this milestone):")
    sections.append(contract.verification_criterion)
    sections.append("")

    if contract.gear4_purpose:
        sections.append("GEAR 4 SECOND-LANE PURPOSE:")
        sections.append(contract.gear4_purpose)
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
    handoff_packet: str, milestone: Milestone,
    contract: ResolvedMilestoneContract, config: dict,
    config_name: Optional[str] = None,
    trace_dir: Optional[str] = None,
    parent_trace_ref: Optional[str] = None,
    framework_id: Optional[str] = None,
    selected_mode: Optional[str] = None,
    project_model_locks: Optional[dict] = None,
    persona_resolution: Optional[dict] = None,
    style_context: Optional[dict] = None,
    input_context: Optional[dict] = None,
    images: Optional[list] = None,
) -> str:
    """Send the handoff packet through the existing gear pipeline.

    Uses exactly the Gear admitted by preflight: Gear 4's genuine dual lane,
    Gear 3's authoritative sequential lane, or the rare Gear 2 single pass.

    Bypasses Phase A.5 cleanup and mode classification — the handoff packet
    is structured framework-generated content, not raw human input. The mode
    is a Framework-native milestone contract; no Dialogue mode supplies hidden
    authority, retrieval, tool, or project semantics.

    ``config_name`` (install Chunk 3) routes the gear pipeline through a
    named configuration. None defers to the Router's context-derived default.
    """
    from boot import (
        _resolve_effective_style_id,
        build_system_prompt_for_gear,
        run_single_pass_with_tools,
        run_gear3,
        run_gear4,
    )

    context_pkg = _build_context_pkg(
        handoff_packet, milestone, contract, trace_dir=trace_dir,
        parent_trace_ref=parent_trace_ref, framework_id=framework_id,
        selected_mode=selected_mode,
        project_model_locks=project_model_locks,
        input_context=input_context)
    if persona_resolution:
        context_pkg["persona_resolution"] = persona_resolution
    for key in ("style_id", "style_register", "style_deltas"):
        if isinstance(style_context, dict) and key in style_context:
            context_pkg[key] = style_context[key]
    if "style_id" not in context_pkg:
        context_pkg["style_id"] = (
            _resolve_effective_style_id(config)
            or ("__persona__" if persona_resolution else "")
        )
    context_pkg.setdefault("style_register", "written")
    context_pkg.setdefault("style_deltas", None)
    execution_context = context_pkg.get("execution_context", "interactive")

    if contract.gear == 4:
        response = run_gear4(
            context_pkg, config, images=images,
            execution_context=execution_context, config_name=config_name,
        )
    elif contract.gear == 3:
        response = run_gear3(
            context_pkg, config, images=images, config_name=config_name,
        )
    else:
        # Model-executed contracts admit Gear 2 only on the single-pass path;
        # Gear 1 is reserved for an exact authenticated mechanical redirect.
        from boot import resolve_single_pass_endpoint
        endpoint, endpoint_cell = resolve_single_pass_endpoint(
            config, contract.gear, config_name=config_name
        )
        if endpoint is None:
            if trace_dir:
                try:
                    try:
                        import pipeline_trace
                    except ImportError:
                        from orchestrator import pipeline_trace
                    pipeline_trace.write_step(
                        trace_dir, "step3-direct-no-endpoint", {
                            "gear": contract.gear,
                            "endpoint_available": False,
                        })
                except Exception:
                    pass
            raise MilestoneExecutionError(
                f"No endpoint available for gear {contract.gear} "
                f"cell {endpoint_cell!r} in configuration {config_name!r}"
            )
        system_prompt = build_system_prompt_for_gear(context_pkg, "breadth")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": handoff_packet},
        ]
        response = run_single_pass_with_tools(
            messages, endpoint,
            slot=endpoint_cell,
            gear=contract.gear,
            config_name=config_name,
            images=images,
            step_name="step3-direct-response",
            context_pkg=context_pkg,
        )
        if trace_dir:
            try:
                try:
                    import pipeline_trace
                except ImportError:
                    from orchestrator import pipeline_trace
                pipeline_trace.write_step(
                    trace_dir, "step3-direct-response", {
                            "gear": contract.gear,
                        "raw_response": response,
                        "endpoint": (
                            endpoint.get("name")
                            if isinstance(endpoint, dict) else str(endpoint)
                        ),
                    })
            except Exception:
                pass
    return _validate_framework_pipeline_result(
        response, context_pkg, declared_gear=contract.gear,
    )


def _build_context_pkg(handoff_packet: str, milestone: Milestone,
                       contract: ResolvedMilestoneContract,
                       trace_dir: Optional[str] = None,
                       parent_trace_ref: Optional[str] = None,
                       framework_id: Optional[str] = None,
                       selected_mode: Optional[str] = None,
                       project_model_locks: Optional[dict] = None,
                       input_context: Optional[dict] = None) -> dict:
    """Build a Framework-native context package, with no hidden mode."""
    if (
        milestone.id != contract.milestone_id
        or milestone.gear != contract.gear
    ):
        raise FrameworkPreflightError(
            "Framework milestone execution does not match its admitted contract"
        )
    method_contract = [
        {
            "id": method.id,
            "name": method.name,
            "body": method.body,
            "legacy": method.legacy,
        }
        for method in contract.methods
    ]
    pkg = {
        "cleaned_prompt": handoff_packet,
        "raw_prompt": handoff_packet,
        "natural_language_prompt": handoff_packet,
        "operational_notation": handoff_packet,
        "mode": "framework-milestone",
        "mode_name": f"{framework_id or 'framework'}:{contract.milestone_id}",
        "mode_text": "",
        "gear": contract.gear,
        "triage_tier": 1,
        "conversation_rag": "",
        "concept_rag": "",
        "framework_execution": True,
        "milestone_id": contract.milestone_id,
        "framework_milestone_contract": {
            "framework_id": framework_id or "",
            "milestone_id": contract.milestone_id,
            "milestone_name": contract.name,
            "methods": method_contract,
            "output_specification": contract.output_format,
            "verification_criterion": contract.verification_criterion,
            "gear": contract.gear,
            "gear4_purpose": contract.gear4_purpose,
        },
    }
    if trace_dir:
        pkg["trace_dir"] = trace_dir
    if parent_trace_ref:
        pkg["parent_trace_ref"] = parent_trace_ref
    if framework_id:
        pkg["framework_id"] = framework_id
    if selected_mode:
        pkg["framework_mode"] = selected_mode
    if project_model_locks:
        pkg["model_profile_locks"] = copy.deepcopy(project_model_locks)
    if isinstance(input_context, dict):
        reserved = {
            "cleaned_prompt",
            "raw_prompt",
            "natural_language_prompt",
            "operational_notation",
            "mode",
            "mode_name",
            "mode_text",
            "gear",
            "triage_tier",
            "conversation_rag",
            "concept_rag",
            "framework_execution",
            "milestone_id",
            "framework_milestone_contract",
            "trace_dir",
            "parent_trace_ref",
            "framework_id",
            "framework_mode",
            "persona_resolution",
            "optional_context_units",
            "context_source_inventory",
            "framework_execution_state",
            "framework_convergence",
            "execution_review",
        }
        collisions = sorted(
            key
            for key, value in input_context.items()
            if (
                value is not None
                and isinstance(key, str)
                and (key in reserved or key.startswith("_"))
            )
        )
        if collisions:
            raise FrameworkPreflightError(
                "Framework input context cannot replace reserved execution "
                f"field(s): {', '.join(collisions)}"
            )
        for key, value in input_context.items():
            if value is not None:
                if key == "model_profile_locks":
                    if key not in pkg or value != pkg[key]:
                        raise FrameworkPreflightError(
                            "Framework input context changed authenticated "
                            "Model Profile locks"
                        )
                    continue
                pkg[key] = copy.deepcopy(value)
        contributor_bundle = input_context.get("contributor_bundle")
        if isinstance(contributor_bundle, dict):
            units = contributor_bundle.get("units")
            if isinstance(units, list):
                # Gear context assembly consumes this exact lane.  Preserve
                # every explicitly selected contributor unit and its source
                # inventory; never summarize them into substitute bullets.
                pkg["optional_context_units"] = copy.deepcopy(units)
            sources = contributor_bundle.get("sources")
            if isinstance(sources, list):
                pkg["context_source_inventory"] = {
                    "sources": copy.deepcopy(sources),
                    "global_retrieved_units": 0,
                    "global_excluded_units": 0,
                }
    return pkg


def _validate_framework_pipeline_result(
    response,
    context_pkg: dict,
    *,
    declared_gear: int,
) -> str:
    """Admit only a material candidate with truthful terminal quality state."""
    if not isinstance(response, str):
        raise FrameworkPipelineError(
            "Framework Gear pipeline returned the wrong type; expected text",
        )
    try:
        from boot import _step_output_health
    except ImportError:
        from orchestrator.boot import _step_output_health
    healthy, reason = _step_output_health(
        response, "framework-deliverable", min_chars=30,
    )
    if not healthy:
        raise FrameworkPipelineError(
            f"Framework Gear pipeline returned no material deliverable: {reason}",
            candidate=response,
        )
    if response.lstrip().startswith("## Deliverable withheld"):
        raise FrameworkPipelineError(
            "Framework final criterion did not release the candidate",
            candidate=response,
        )

    effective_gear = context_pkg.get("_trace_effective_gear", declared_gear)
    if effective_gear != declared_gear:
        raise FrameworkPipelineError(
            f"Framework Gear {declared_gear} degraded to Gear {effective_gear}; "
            "the declared execution contract was not completed",
            candidate=response,
            terminal_state="degraded",
        )
    strict_state = context_pkg.get("framework_execution_state")
    if isinstance(strict_state, dict) and not strict_state.get("success", False):
        raise FrameworkPipelineError(
            str(strict_state.get("reason") or "Framework Gear pipeline degraded"),
            candidate=response,
            terminal_state=str(strict_state.get("terminal_state") or "failed"),
        )
    if declared_gear in (3, 4):
        review = context_pkg.get("execution_review")
        if not isinstance(review, dict):
            raise FrameworkPipelineError(
                "Framework final verification criterion was unavailable",
                candidate=response,
                terminal_state="degraded",
            )
        verdict = str(review.get("verdict") or "").upper()
        status = str(review.get("status") or "")
        if verdict != "PASS" or "withheld" in status:
            raise FrameworkPipelineError(
                "Framework final verification criterion did not pass "
                f"(verdict={verdict or 'unavailable'}, status={status or 'unavailable'})",
                candidate=response,
                terminal_state=("degraded" if verdict in {"", "BROKEN"} else "failed"),
            )
    return response.strip()


def _start_child_trace(parent_trace_dir: Optional[str],
                       handoff_packet: str,
                       framework: Framework,
                       milestone: Milestone,
                       parent_trace_ref: Optional[str],
                       selected_mode: Optional[str],
                       gear: int,
                       conversation_tag: str,
                       trace_context: Optional[dict]) -> Optional[str]:
    if not parent_trace_dir:
        return None
    try:
        try:
            import pipeline_trace
        except ImportError:
            from orchestrator import pipeline_trace
        parent_manifest = pipeline_trace.read_manifest(parent_trace_dir) or {}
        framework_name = getattr(framework, "name", str(framework))
        milestone_id = getattr(milestone, "id", str(milestone))
        if not hasattr(milestone, "id"):
            milestone = type("MilestoneRef", (), {
                "id": milestone_id, "name": "", "mode": selected_mode,
                "endpoint_produced": "", "verification_criterion": "",
                "drift_check_question": "", "output_format": "",
                "gear": gear, "layers_covered": [], "required_prior": [],
                "conditional_layers": None})()
        if not hasattr(framework, "name"):
            framework = type("FrameworkRef", (), {"name": framework_name, "file_path": ""})()
        child_dir = pipeline_trace.start_trace(
            conversation_id=parent_manifest.get("conversation_id"),
            raw_input=handoff_packet,
            ambiguity_mode="assume",
            stealth=(conversation_tag == "stealth"),
            conversation_tag=conversation_tag,
        )
        child_ref = pipeline_trace.trace_ref_for_dir(child_dir)
        if child_ref:
            pipeline_trace.append_child_trace_ref(parent_trace_dir, child_ref)
            if trace_context is not None:
                refs = trace_context.setdefault("child_trace_refs", [])
                if child_ref not in refs:
                    refs.append(child_ref)
        snapshot = None
        try:
            try:
                import trace_debug as _tdbg
            except ImportError:
                from orchestrator import trace_debug as _tdbg
            snapshot = _tdbg.framework_contract_snapshot(
                framework, milestone, selected_mode=selected_mode)
        except Exception:
            snapshot = None
        fields = dict(
            trace_kind="framework-milestone",
            mode=selected_mode or "all",
            gear=gear,
            parent_trace_ref=parent_trace_ref,
            framework_id=framework_name,
            milestone_id=milestone_id,
        )
        if snapshot:
            fields["contract_snapshot"] = snapshot
        pipeline_trace.update_manifest_fields(child_dir, **fields)
        return child_dir
    except Exception:
        return None


def _run_child_attempt(child_trace_dir: Optional[str],
                       parent_trace_ref: Optional[str],
                       handoff_packet: str,
                       milestone: Milestone,
                       contract: ResolvedMilestoneContract,
                       config: dict,
                       config_name: Optional[str],
                       framework_id: str,
                       selected_mode: Optional[str],
                       project_model_locks: Optional[dict] = None,
                       stealth: bool = False,
                       persona_resolution: Optional[dict] = None,
                       style_context: Optional[dict] = None,
                       input_context: Optional[dict] = None,
                       images: Optional[list] = None) -> str:
    trace_token, tool_token = _bind_trace_context(
        child_trace_dir, stealth=stealth, surface="framework")
    try:
        return _run_through_gear_pipeline(
            handoff_packet, milestone, contract, config, config_name=config_name,
            trace_dir=child_trace_dir, parent_trace_ref=parent_trace_ref,
            framework_id=framework_id, selected_mode=selected_mode,
            project_model_locks=project_model_locks,
            persona_resolution=persona_resolution,
            style_context=style_context,
            input_context=input_context,
            images=images)
    finally:
        _reset_trace_context(trace_token, tool_token)


def _bind_trace_context(trace_dir: Optional[str],
                        stealth: bool = False,
                        surface: str = "framework"):
    try:
        from boot import _TURN_TRACE_DIR_CV
        trace_token = _TURN_TRACE_DIR_CV.set(trace_dir)
    except Exception:
        trace_token = None
    tool_token = None
    try:
        try:
            import tool_events as _te
        except ImportError:
            from orchestrator import tool_events as _te
        conv_id = None
        if trace_dir:
            conv_id = os.path.basename(os.path.dirname(trace_dir))
        tool_token = _te.set_turn_context(
            trace_dir=trace_dir, conversation_id=conv_id,
            stealth=stealth, surface=surface)
    except Exception:
        tool_token = None
    return trace_token, tool_token


def _reset_trace_context(trace_token, tool_token) -> None:
    try:
        if trace_token is not None:
            from boot import _TURN_TRACE_DIR_CV
            _TURN_TRACE_DIR_CV.reset(trace_token)
    except Exception:
        pass
    try:
        if tool_token is not None:
            try:
                import tool_events as _te
            except ImportError:
                from orchestrator import tool_events as _te
            _te.reset_turn_context(tool_token)
    except Exception:
        pass


def _finalize_child_trace(child_trace_dir: Optional[str],
                          status: str,
                          framework_id: str,
                          milestone_id: str,
                          selected_mode: Optional[str],
                          gear: int,
                          parent_trace_ref: Optional[str]) -> None:
    if not child_trace_dir:
        return
    try:
        try:
            import pipeline_trace
        except ImportError:
            from orchestrator import pipeline_trace
        pipeline_trace.finalize_manifest(
            child_trace_dir, kind="framework-milestone",
            status_hint=status, mode=selected_mode or "all", gear=gear,
            parent_trace_ref=parent_trace_ref,
            framework_id=framework_id, milestone_id=milestone_id)
    except Exception:
        pass


# ---------- Drift check ----------

def _run_drift_check(
    milestone: Milestone,
    deliverable: str,
    user_input: str,
    config: dict,
    config_name: Optional[str] = None,
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
    endpoint = get_slot_endpoint(
        config, DRIFT_CHECK_SLOT, config_name=config_name,
    ) or (get_active_endpoint(config) if config_name is None else None)
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

    if not isinstance(response, str) or not response.strip():
        return (
            "DRIFT_CHECK_SKIPPED",
            "Drift check returned no usable text verdict.",
        )

    return _parse_drift_response(response)


def _parse_drift_response(response: str) -> tuple[str, str]:
    """Extract STATUS and REASONING from the drift check response."""
    import re
    if not isinstance(response, str) or not response.strip():
        return ("DRIFT_CHECK_SKIPPED", "Drift check returned no usable verdict.")
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
    slash_form: Optional[str] = None,
) -> FrameworkExecutionResult:
    """Return a FrameworkExecutionResult that redirects the user to the
    matching slash command instead of running the gear pipeline.

    Mechanical modes (C-Instance / C-Validate / O-Render) are handled by
    runtime functions, not by model passes. Running them through /framework
    would produce a hallucinated artifact rather than actually creating a
    file. This redirect surfaces the canonical invocation so the user can
    re-issue the request via the slash command.
    """
    canonical_filename = os.path.basename(fw.file_path)
    slash_form = slash_form or EXACT_MECHANICAL_REDIRECTS.get(
        (canonical_filename, selected_mode)
    )
    if slash_form is None:
        raise FrameworkPreflightError(
            f"Framework preflight refused {canonical_filename}: "
            f"{selected_mode!r} is not a recognized mechanical contract"
        )
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


def resume_framework(
    execution_id: str,
    config: Optional[dict] = None,
    *,
    trace_dir: Optional[str] = None,
    trace_context: Optional[dict] = None,
) -> FrameworkExecutionResult:
    """Resume a preserved normal run at its first unfinished milestone.

    The current canonical Framework is preflighted again and must have the
    same contract digest as the failed run. Completed prefix milestones are
    loaded from scratch and are never re-executed.
    """
    scratch = ScratchSession.attach(execution_id)
    manifest = scratch.manifest()
    if manifest.get("conversation_tag") == "stealth":
        raise FrameworkPreflightError("Stealth Framework runs cannot be resumed")
    canonical = manifest.get("canonical_filename")
    original_input = manifest.get("original_input")
    effective_input = manifest.get("effective_input")
    selected_mode = manifest.get("selected_mode")
    stored_context = manifest.get("input_context")
    stored_identity_digest = manifest.get("resume_identity_digest")
    if not all(isinstance(value, str) for value in (
        canonical,
        original_input,
        effective_input,
        selected_mode,
        stored_identity_digest,
    )) or not isinstance(stored_context, dict):
        raise FrameworkPreflightError(
            "Framework resume refused because scratch lacks admitted run identity"
        )
    prepared = prepare_framework_execution(
        canonical,
        original_input,
        project_nexus=manifest.get("project_nexus"),
        one_run_profile=manifest.get("one_run_profile"),
        input_context=stored_context,
    )
    if prepared.effective_input != effective_input:
        raise FrameworkPreflightError(
            "Framework resume refused because the admitted effective input changed"
        )
    expected_exact_mode = manifest.get("exact_mode")
    if expected_exact_mode is not None and not isinstance(expected_exact_mode, str):
        raise FrameworkPreflightError(
            "Framework resume refused because its exact mode identity is invalid"
        )
    if prepared.exact_mode != expected_exact_mode:
        raise FrameworkPreflightError(
            "Framework resume refused because its exact mode identity changed"
        )
    if (
        prepared.project_profile != manifest.get("project_profile")
        or prepared.project_nexus != manifest.get("project_nexus")
        or prepared.one_run_profile != manifest.get("one_run_profile")
    ):
        raise FrameworkPreflightError(
            "Framework resume refused because its project or profile binding changed"
        )
    if _thaw_value(prepared.input_context) != stored_context:
        raise FrameworkPreflightError(
            "Framework resume refused because its admitted input context changed"
        )
    if (
        _contract_digest(prepared) != manifest.get("contract_digest")
        or _resume_identity_digest(
            prepared,
            selected_mode=selected_mode,
            effective_input=effective_input,
        ) != stored_identity_digest
    ):
        raise FrameworkPreflightError(
            "Framework resume refused because the admitted identity, contract, "
            "prerequisites, or context changed"
        )
    stored_style_context = {
        key: stored_context[key]
        for key in ("style_id", "style_register", "style_deltas")
        if key in stored_context
    }
    return execute_framework(
        canonical,
        original_input,
        config=config,
        execution_id=execution_id,
        project_nexus=manifest.get("project_nexus"),
        config_name=manifest.get("one_run_profile"),
        trace_dir=trace_dir,
        conversation_tag=str(manifest.get("conversation_tag") or ""),
        trace_context=trace_context,
        style_context=stored_style_context,
        input_context=stored_context,
        images=None,
        prepared=prepared,
        conversation_id=manifest.get("conversation_id"),
        _resume=True,
        _resume_selected_mode=selected_mode,
        _resume_mode_reasoning=str(
            manifest.get("mode_reasoning")
            or "stored admitted Framework mode selection"
        ),
    )


def select_mode(
    fw: Framework,
    user_input: str,
    config: dict,
    *,
    allowed_modes: Optional[tuple[str, ...] | list[str]] = None,
    config_name: Optional[str] = None,
) -> tuple[str, str, str]:
    """Pick the operating mode for a multi-mode framework.

    Selection priority:
      1. Explicit prefix — first whitespace-separated token of user_input
         matches one of the framework's declared modes (case-insensitive).
         The token is consumed; remaining text becomes the effective input.
      2. LLM-based routing classifier — small-model call with the M0 routing
         function text and a one-line catalog of modes. Skipped when no
         endpoint is available.
      3. Default to the first declared mode.

    Returns (mode, reasoning, effective_input). For single-mode frameworks
    or frameworks with no declared modes, returns ("all", reason, user_input).
    """
    if not fw.is_multi_mode or not fw.modes:
        return ("all", "single-mode framework", user_input)

    candidates = tuple(allowed_modes) if allowed_modes is not None else tuple(fw.modes)
    if not candidates:
        raise FrameworkPreflightError(
            f"Framework preflight refused {fw.name}: no model-executed mode is eligible"
        )
    unknown = [mode for mode in candidates if mode not in fw.modes]
    if unknown:
        raise FrameworkPreflightError(
            f"Framework preflight refused {fw.name}: unknown prepared mode(s): "
            + ", ".join(unknown)
        )

    # 1. Explicit prefix
    first, remaining = _consume_first_token(user_input)
    if first is not None:
        for mode_name in candidates:
            if first.lower() == mode_name.lower():
                return (
                    mode_name,
                    f"explicit prefix: first token matched mode {mode_name!r}",
                    remaining,
                )

    if len(candidates) == 1:
        only = candidates[0]
        return (
            only,
            f"only prepared model-executed mode {only!r} is eligible",
            user_input,
        )

    # 2. LLM-based routing classifier.  Mode names elsewhere in prose are
    # content, not identity; only the exact first token is authoritative.
    selected = _llm_select_mode(
        fw, user_input, config, allowed_modes=candidates,
        config_name=config_name,
    )
    if selected:
        mode, reasoning = selected
        return (mode, reasoning, user_input)

    # 3. Default to first declared mode
    first_mode = candidates[0]
    return (
        first_mode,
        f"no mode signal detected; defaulting to first declared mode "
        f"{first_mode!r}",
        user_input,
    )


def _llm_select_mode(
    fw: Framework,
    user_input: str,
    config: dict,
    *,
    allowed_modes: Optional[tuple[str, ...] | list[str]] = None,
    config_name: Optional[str] = None,
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
        get_slot_endpoint(config, MODE_SELECT_SLOT, config_name=config_name)
        or (get_active_endpoint(config) if config_name is None else None)
    )
    if endpoint is None:
        return None

    valid_modes = list(allowed_modes) if allowed_modes is not None else list(fw.modes)
    catalog = _build_mode_catalog(fw, allowed_modes=valid_modes)

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

    return _parse_mode_response(response, valid_modes)


def _build_mode_catalog(
    fw: Framework,
    *,
    allowed_modes: Optional[tuple[str, ...] | list[str]] = None,
) -> str:
    """Construct a short catalog string for the routing classifier prompt."""
    lines: list[str] = []
    if fw.m0_routing and fw.m0_routing.function:
        lines.append(f"Routing function: {fw.m0_routing.function}")
        lines.append("")
    modes = allowed_modes if allowed_modes is not None else fw.modes
    for mode_name in modes:
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
_FRAMEWORK_RESUME_INTENT_RE = re.compile(
    r"\A\s*/framework\s+--resume(?=\s|\Z)",
)
_FRAMEWORK_RESUME_COMMAND_RE = re.compile(
    r"\A\s*/framework\s+--resume\s+"
    r"(?P<execution_id>[A-Za-z0-9][A-Za-z0-9._-]{0,127})\s*\Z",
)


def is_framework_resume_command(user_input: str) -> bool:
    """Recognize the reserved typed resume form before generic parsing."""
    return bool(_FRAMEWORK_RESUME_INTENT_RE.match(user_input or ""))


def _parse_framework_resume_command(user_input: str) -> Optional[str]:
    if not is_framework_resume_command(user_input):
        return None
    match = _FRAMEWORK_RESUME_COMMAND_RE.match(user_input or "")
    if match is None:
        raise ValueError(
            "resume syntax is `/framework --resume <execution-id>` with no "
            "additional query or options"
        )
    return match.group("execution_id")


def is_framework_command(user_input: str) -> bool:
    """Check if user_input starts with the /framework slash command."""
    return is_framework_command_syntax(user_input)


def parse_framework_command(user_input: str) -> tuple[str, str, Optional[str]]:
    """Parse '/framework <name> [--config <ConfigName>] [<query>]' into
    (framework_filename, query, config_name).

    framework_filename is resolved through the curated user-invocable
    framework registry, which also handles aliases such as ``cff`` and rejects
    pipeline-internal specs. Raises ValueError if the framework name is missing
    or not user-invocable.

    An empty query is allowed and returned as "". The caller decides how to
    handle it: ``run_framework_command`` treats empty as an error (it expects
    a one-shot invocation), while ``framework_elicitation.start_elicitation``
    treats empty as the trigger for an interactive multi-turn session.

    Optional ``--config <ConfigName>`` flag (install Chunk 3) routes this
    invocation through the named configuration from config/configurations/.
    Position-agnostic — accepted anywhere in the body after the framework
    name. When absent, returns config_name=None and the executor falls
    through to the framework's declared default in framework-routing.json,
    then to the Router's context-derived default.

    Multi-mode dispatch: the executor inspects only the query's first token
    for an exact declared mode identity. To force a specific
    mode, prefix the query with the mode name — e.g.
    ``/framework problem-evolution PE-Init walk through the new project``
    runs PE-Init regardless of context. Without an explicit token, the
    executor's ``select_mode`` falls through to LLM-based routing, then to
    the first declared mode.
    """
    try:
        return parse_framework_command_bytes(user_input)
    except FrameworkPreflightError as exc:
        raise ValueError(str(exc)) from exc


def framework_command_has_query(user_input: str) -> bool:
    """Return True iff /framework <name> was invoked with a non-empty query.

    Used by the chat handler to choose between one-shot dispatch
    (``run_framework_command``) and interactive elicitation
    (``framework_elicitation.start_elicitation``).
    """
    if is_framework_resume_command(user_input):
        return True
    try:
        _, query, _ = parse_framework_command(user_input)
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
        completed = [milestone for milestone in result.milestones if milestone.completed]
        parts = [
            f"[Framework: {result.framework_name}{mode_suffix} | "
            f"Execution: {result.execution_id} | "
            f"Terminal state: {result.terminal_state}]",
            "",
            (
                f"Execution stopped at milestone {result.failed_milestone_id or 'unknown'}: "
                f"{result.failure_reason or 'no failure reason was recorded'}."
            ),
        ]
        if completed:
            parts.extend([
                "",
                "## Completed milestone deliverables",
            ])
            for milestone in completed:
                parts.extend([
                    "",
                    f"### {milestone.milestone_id} — {milestone.name}",
                    "",
                    milestone.deliverable,
                ])
        terminal_results = [
            milestone for milestone in result.milestones if not milestone.completed
        ]
        for milestone in terminal_results:
            parts.extend([
                "",
                f"## Boundary intervention — {milestone.milestone_id}",
                "",
                f"{milestone.drift_status}: {milestone.drift_reasoning}",
            ])
        if result.resume_available and result.recovery_path:
            parts.extend([
                "",
                (
                    f"Resume is available for execution `{result.execution_id}`. "
                    "Use `/framework --resume "
                    f"{result.execution_id}` to continue at the first unfinished "
                    "milestone without repeating the completed work."
                ),
                f"Recovery scratch: {result.recovery_path}",
            ])
        else:
            parts.extend([
                "",
                "No scratch or resume state was retained for this Stealth execution.",
            ])
        return "\n".join(parts)

    drift_warnings = []
    for ms in result.milestones:
        if ms.drift_status != "IN_SCOPE":
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


def run_framework_command(user_input: str, config: dict,
                          *,
                          trace_dir: Optional[str] = None,
                          conversation_tag: str = "",
                          trace_context: Optional[dict] = None,
                          project_nexus: Optional[str] = None,
                          one_run_profile: Optional[str] = None,
                           style_context: Optional[dict] = None,
                           input_context: Optional[dict] = None,
                           images: Optional[list] = None,
                           prepared: Optional[PreparedFramework] = None) -> str:
    """Top-level: parse a slash command + execute + format. Used by boot.py
    and server.py as the entry point for /framework slash-command invocations.

    Returns a formatted user-facing string. Errors are caught and surfaced
    in the returned string rather than raising, so the chat UI always
    receives a renderable response.
    """
    try:
        resume_execution_id = _parse_framework_resume_command(user_input)
    except ValueError as exc:
        if trace_context is not None:
            trace_context["status"] = "error"
        return f"[Framework command error: {exc}]"
    if resume_execution_id is not None:
        try:
            _parent_trace_token, _parent_tool_token = _bind_trace_context(
                trace_dir, stealth=False, surface="framework",
            )
            try:
                result = resume_framework(
                    resume_execution_id,
                    config=config,
                    trace_dir=trace_dir,
                    trace_context=trace_context,
                )
            finally:
                _reset_trace_context(_parent_trace_token, _parent_tool_token)
        except FileNotFoundError as exc:
            if trace_context is not None:
                trace_context["status"] = "error"
            return f"[Framework resume state not found: {exc}]"
        except FrameworkPreflightError as exc:
            if trace_context is not None:
                trace_context["status"] = "refused"
            return f"[Framework preflight refusal: {exc}]"
        except FrameworkParseError as exc:
            if trace_context is not None:
                trace_context["status"] = "error"
            return f"[Framework parse error: {exc}]"
        except Exception as exc:
            if trace_context is not None:
                trace_context["status"] = "error"
            return f"[Unexpected error during framework resume: {exc}]"
        if trace_context is not None:
            trace_context["framework_id"] = result.framework_name
            trace_context.setdefault(
                "status", "completed" if result.success else "error",
            )
        return format_execution_result(result)

    try:
        framework_name, framework_query, command_profile = parse_framework_command(user_input)
    except ValueError as exc:
        if trace_context is not None:
            trace_context["status"] = "error"
        return f"[Framework command error: {exc}]"
    if trace_context is not None:
        trace_context["framework_id"] = framework_name

    if command_profile and one_run_profile and command_profile != one_run_profile:
        if trace_context is not None:
            trace_context["status"] = "error"
        return (
            "[Framework command error: the command and input toolbar specify "
            "different one-run Model Profiles.]"
        )
    effective_one_run_profile = command_profile or one_run_profile

    if not framework_query.strip():
        if trace_context is not None:
            trace_context["status"] = "error"
        return (
            f"[Framework {framework_name} invoked without a query. For one-shot "
            f"execution, supply a query: `/framework {framework_name} <your input>`. "
            f"For interactive elicitation, the chat handler should route empty-query "
            f"invocations through framework_elicitation.start_elicitation rather than "
            f"this entry point.]"
        )

    try:
        if prepared is None:
            prepared = prepare_framework_execution(
                framework_name,
                framework_query,
                project_nexus=project_nexus,
                one_run_profile=effective_one_run_profile,
                input_context=input_context,
            )
        else:
            prepared = reuse_prepared_framework(
                prepared,
                framework_name,
                framework_query,
                project_nexus=project_nexus,
                one_run_profile=effective_one_run_profile,
                input_context=input_context,
            )
        project_nexus = prepared.project_nexus
        input_context = prepared_input_context(prepared, input_context)
    except FrameworkPreflightError as exc:
        if trace_context is not None:
            trace_context["status"] = "refused"
        return f"[Framework preflight refusal: {exc}]"

    try:
        _parent_trace_token, _parent_tool_token = _bind_trace_context(
            trace_dir, stealth=(conversation_tag == "stealth"),
            surface="framework")
        try:
            result = execute_framework(
                framework_name, framework_query, config,
                project_nexus=project_nexus,
                config_name=effective_one_run_profile, trace_dir=trace_dir,
                conversation_tag=conversation_tag,
                trace_context=trace_context,
                style_context=style_context,
                input_context=input_context,
                images=images,
                prepared=prepared)
        finally:
            _reset_trace_context(_parent_trace_token, _parent_tool_token)
    except FileNotFoundError as exc:
        if trace_context is not None:
            trace_context["status"] = "error"
        return f"[Framework file not found: {exc}]"
    except FrameworkPreflightError as exc:
        if trace_context is not None:
            trace_context["status"] = "refused"
        return f"[Framework preflight refusal: {exc}]"
    except FrameworkParseError as exc:
        if trace_context is not None:
            trace_context["status"] = "error"
        return f"[Framework parse error: {exc}]"
    except NotImplementedError as exc:
        if trace_context is not None:
            trace_context["status"] = "error"
        return f"[Framework execution not yet supported: {exc}]"
    except Exception as exc:
        if trace_context is not None:
            trace_context["status"] = "error"
        return f"[Unexpected error during framework execution: {exc}]"
    if trace_context is not None:
        trace_context.setdefault("status", "completed" if result.success else "error")

    return format_execution_result(result)


# ---------- CLI smoke test ----------

if __name__ == "__main__":
    """Run a parser-only dry-run to verify the executor can build handoff
    packets without actually calling models."""
    target = sys.argv[1] if len(sys.argv) > 1 else "deep-research-protocol.md"

    user_input = "What does AI mean for the future of human cognition?"
    prepared = prepare_framework_execution(target, user_input)
    fw = prepared.framework
    print(f"Framework: {fw.name}")
    print(f"  multi-mode: {fw.is_multi_mode}")
    if fw.is_multi_mode:
        print("  (executor MVP supports single-mode only — would skip)")
        sys.exit(0)

    milestones = fw.milestones_by_mode["all"]
    print(f"  milestones: {len(milestones)}")

    # Simulate a scratch session and build a handoff packet for each milestone
    sess = ScratchSession.create(fw.name)
    for ms in milestones:
        # Fake prior milestone outputs for handoff packet preview
        for prior in ms.required_prior:
            if not sess.has_milestone(prior):
                sess.write_milestone(prior, f"<simulated content for {prior}>")
        packet = _build_handoff_packet(
            fw, ms, prepared.contract_for("all", ms.id), sess, user_input,
        )
        print(f"\n--- Handoff packet for {ms.id} ({ms.name}) ---")
        print(packet[:1500] + ("..." if len(packet) > 1500 else ""))

    sess.cleanup()
    print(f"\n[Smoke test complete. Cleaned up scratch.]")
