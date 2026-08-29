"""Behavioral proof for truthful Framework runtime execution.

The batch is deliberately hermetic: admitted contracts are immutable fakes,
model calls are deterministic, and every scratch root is test-managed.
"""
from __future__ import annotations

import json
import hashlib
import os
import sys
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

import pytest


HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = os.path.dirname(HERE)
if ORCH not in sys.path:
    sys.path.insert(0, ORCH)

import boot  # noqa: E402
import framework_preflight as preflight  # noqa: E402
import milestone_executor as executor  # noqa: E402
import oversight_events  # noqa: E402
import persona  # noqa: E402
import pipeline_trace  # noqa: E402
import scratch  # noqa: E402
import triggers  # noqa: E402
from orchestrator import conversation_closeout as closeout  # noqa: E402


MATERIAL = (
    "This is a material Framework deliverable with enough specific content "
    "to pass the runtime's nonempty and diagnostic checks."
)
CONTRADICTORY_QUALITY_SCAFFOLD = (
    "OLDER UNIVERSAL RULE: exhausted FAIL or BROKEN review ships the candidate."
)
FRAMEWORK_RELEASE_OVERRIDE = (
    "FRAMEWORK-ONLY TERMINAL RELEASE OVERRIDE — CONTROLLING"
)


def _profile() -> MappingProxyType:
    return MappingProxyType({
        "selected": MappingProxyType({
            "name": "test-profile",
            "runtime_name": "test-profile",
        }),
        "chain": (),
    })


def _prepared(
    *,
    gears=(2,),
    purpose="both",
    mode="all",
    original_input="Investigate the supplied evidence truthfully.",
    effective_input=None,
    exact_mode=None,
    project_nexus=None,
    project_profile=None,
    input_context=None,
) -> preflight.PreparedFramework:
    contracts = []
    for index, gear in enumerate(gears, start=1):
        milestone_id = f"M{index}"
        contracts.append(preflight.ResolvedMilestoneContract(
            mode=mode,
            milestone_id=milestone_id,
            name=f"Milestone {index}",
            endpoint_produced=f"A material result for milestone {index}.",
            methods=(preflight.ResolvedMethod(
                id=f"method-{index}",
                name=f"Resolved method {index}",
                body=(
                    f"Apply resolved method {index} exactly, preserving the "
                    "user's evidence and explicit qualifications."
                ),
            ),),
            required_prior=((f"M{index - 1}",) if index > 1 else ()),
            external_prerequisites=(),
            verification_criterion=(
                f"Criterion {index}: every required fact is present and the "
                "declared output contains no unsupported conclusion."
            ),
            gear=gear,
            gear4_purpose=(purpose if gear == 4 else None),
            output_format=f"Markdown deliverable format {index}.",
            drift_check_question="Does this remain within the user's request?",
            conditional_layers=None,
            declared_model_profile="test-profile",
            model_profile_resolution=_profile(),
        ))
    by_mode = MappingProxyType({mode: tuple(contracts)})
    framework = preflight.PreparedFrameworkContract(
        name="Truthful Runtime Test Framework",
        file_path="/quarantined/truthful-runtime.md",
        raw_markdown="# Truthful Runtime Test Framework",
        is_multi_mode=(mode != "all"),
        modes=((mode,) if mode != "all" else ()),
        m0_routing=None,
        milestones_by_mode=by_mode,
    )
    contract_map = MappingProxyType({
        (mode, contract.milestone_id): contract for contract in contracts
    })
    return preflight.PreparedFramework(
        canonical_filename="truthful-runtime.md",
        framework=framework,
        contract_text="\n".join(
            contract.verification_criterion for contract in contracts
        ),
        contracts=contract_map,
        original_input=original_input,
        exact_mode=exact_mode,
        effective_input=(
            original_input if effective_input is None else effective_input
        ),
        mode_reasoning=(
            f"explicit prefix: first token matched mode {mode!r}"
            if exact_mode else "single-mode Framework"
        ),
        mechanical_redirect=None,
        project_nexus=project_nexus,
        project_profile=project_profile,
        one_run_profile="test-profile",
        selector_profile_resolution=_profile(),
        input_context=MappingProxyType(dict(input_context or {})),
    )


def _accepted(
    session: scratch.ScratchSession,
    milestone: preflight.ResolvedMilestoneContract,
    body: str,
) -> executor.MilestoneResult:
    metadata = {
        "name": milestone.name,
        "drift_status": "IN_SCOPE",
        "drift_reasoning": "The accepted output remains in scope.",
        "attempts": 1,
        "deliverable_digest": "sha256:" + hashlib.sha256(
            body.encode("utf-8")
        ).hexdigest(),
    }
    path = session.write_milestone(
        milestone.id, body, result_metadata=metadata,
    )
    return executor.MilestoneResult(
        milestone_id=milestone.id,
        name=milestone.name,
        deliverable=body,
        drift_status="IN_SCOPE",
        drift_reasoning=metadata["drift_reasoning"],
        attempts=1,
        completed=True,
        deliverable_path=path,
    )


def _with_contract_change(
    prepared: preflight.PreparedFramework,
    milestone_id="M1",
    **changes,
) -> preflight.PreparedFramework:
    mode = next(iter(prepared.framework.milestones_by_mode))
    contracts = tuple(prepared.framework.milestones_by_mode[mode])
    changed_contracts = tuple(
        replace(contract, **changes) if contract.milestone_id == milestone_id else contract
        for contract in contracts
    )
    framework = replace(
        prepared.framework,
        milestones_by_mode=MappingProxyType({mode: changed_contracts}),
    )
    contract_map = MappingProxyType({
        (mode, contract.milestone_id): contract for contract in changed_contracts
    })
    return replace(prepared, framework=framework, contracts=contract_map)


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    scratch_root = tmp_path / "scratch"
    monkeypatch.setattr(scratch._rp, "SCRATCH_DIR_STR", str(scratch_root))
    monkeypatch.setattr(executor._rp, "SCRATCH_DIR_STR", str(scratch_root))
    monkeypatch.setattr(executor._rp, "SCRATCH_DIR", scratch_root)
    monkeypatch.setattr(executor, "MAX_RETRIES", 1)
    monkeypatch.setattr(
        executor, "reuse_prepared_framework",
        lambda prepared, *_args, **_kwargs: prepared,
    )
    monkeypatch.setattr(
        executor, "prepared_input_context",
        lambda prepared, supplied=None: {
            **dict(supplied or {}),
            **executor._thaw_value(prepared.input_context),
        },
    )
    monkeypatch.setattr(
        executor, "_authenticated_project_visual_locks", lambda _nexus: None,
    )
    monkeypatch.setattr(
        executor, "_maybe_persist_self_mindspec", lambda *_args: None,
    )
    monkeypatch.setattr(persona, "resolve_persona", lambda **_kwargs: None)
    events = []
    monkeypatch.setattr(oversight_events, "emit", lambda event: events.append(event))
    return {"scratch_root": scratch_root, "events": events}


@pytest.mark.parametrize("boundary", ["DRIFT_DETECTED", "DRIFT_CHECK_SKIPPED"])
def test_drift_boundary_stops_dependents_and_preserves_completed_output(
    boundary, isolated_runtime, monkeypatch,
):
    prepared = _prepared(gears=(2, 2, 2))
    calls = []
    child_terminals = []

    def child_attempt(_trace, _parent, _handoff, milestone, *_args, **_kwargs):
        calls.append(milestone.id)
        return f"{MATERIAL} Candidate from {milestone.id}."

    def drift_check(milestone, *_args, **_kwargs):
        if milestone.id == "M2":
            return boundary, "The boundary could not truthfully pass."
        return "IN_SCOPE", "The output remains within scope."

    monkeypatch.setattr(executor, "_run_child_attempt", child_attempt)
    monkeypatch.setattr(executor, "_run_drift_check", drift_check)
    monkeypatch.setattr(
        executor,
        "_finalize_child_trace",
        lambda _trace, status, _framework, milestone_id, *_args: (
            child_terminals.append((milestone_id, status))
        ),
    )

    result = executor.execute_framework(
        prepared.canonical_filename,
        prepared.original_input,
        config={},
        prepared=prepared,
        execution_id=f"drift-{boundary.lower()}",
        conversation_id="conversation-drift",
    )

    assert result.success is False
    assert result.terminal_state == boundary.lower()
    assert result.failed_milestone_id == "M2"
    assert calls == ["M1", "M2"]
    assert child_terminals == [("M1", "completed"), ("M2", "error")]
    assert [item.completed for item in result.milestones] == [True, False]
    recovery = Path(result.recovery_path)
    assert (recovery / "milestone-M1.md").is_file()
    assert not (recovery / "milestone-M2.md").exists()
    assert (recovery / "milestone-M2-unaccepted.md").is_file()
    assert not (recovery / "milestone-M3.md").exists()

    visible = executor.format_execution_result(result)
    assert MATERIAL in visible
    assert boundary in visible
    assert f"/framework --resume {result.execution_id}" in visible
    assert "resume_framework" not in visible
    completed_events = [
        event for event in isolated_runtime["events"]
        if event["event_type"] == "MilestoneComplete"
    ]
    assert [event["milestone_id"] for event in completed_events] == ["M1"]
    terminal = isolated_runtime["events"][-1]
    assert terminal["success"] is False
    assert terminal["terminal_state"] == boundary.lower()
    assert Path(terminal["recovery_path"]).is_dir()


def test_trigger_does_not_complete_a_terminal_framework_failure(monkeypatch):
    prepared = _prepared()
    failed = executor.FrameworkExecutionResult(
        framework_name=prepared.framework.name,
        execution_id="trigger-failed",
        user_input=prepared.original_input,
        milestones=[],
        final_output="",
        success=False,
        failure_reason="DRIFT_CHECK_SKIPPED",
        terminal_state="drift_check_skipped",
    )
    visual_calls = []
    finalized = []
    monkeypatch.setattr(executor, "execute_framework", lambda *_a, **_k: failed)
    monkeypatch.setattr(pipeline_trace, "start_trace", lambda *_a, **_k: "/trace")
    monkeypatch.setattr(
        pipeline_trace, "finalize_manifest",
        lambda *args, **kwargs: finalized.append((args, kwargs)),
    )
    monkeypatch.setattr(boot, "load_routing_config", lambda: {})
    monkeypatch.setattr(
        boot, "_run_visual_hook",
        lambda *_a, **_k: visual_calls.append(True),
    )

    with pytest.raises(triggers.TriggerConflict, match="DRIFT_CHECK_SKIPPED"):
        triggers._execute_action(
            {
                "kind": "framework",
                "input": prepared.original_input,
                "project_nexus": None,
            },
            {"framework": prepared.canonical_filename, "trigger_id": "T-1"},
            prepared=prepared,
        )

    assert visual_calls == []
    assert finalized and finalized[0][1]["status_hint"] == "error"


def test_exact_resume_command_reaches_resume_without_generic_framework_parsing(
    monkeypatch,
):
    command = "/framework --resume execution-123"
    result = executor.FrameworkExecutionResult(
        framework_name="Truthful Runtime Test Framework",
        execution_id="execution-123",
        user_input="stored admitted input",
        milestones=[],
        final_output="Resumed Framework result.",
        success=True,
        resumed=True,
    )
    calls = []

    def resume(execution_id, **kwargs):
        calls.append((execution_id, kwargs))
        return result

    monkeypatch.setattr(executor, "resume_framework", resume)
    monkeypatch.setattr(
        executor,
        "parse_framework_command",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("resume must not enter generic Framework parsing")
        ),
    )
    monkeypatch.setattr(
        executor, "_bind_trace_context", lambda *_a, **_k: (None, None),
    )
    monkeypatch.setattr(executor, "_reset_trace_context", lambda *_a, **_k: None)

    assert executor.framework_command_has_query(command) is True
    assert boot.framework_dispatch_input(command) == ""
    assert boot._preflight_cli_framework_turn(command, [], None, None) is None
    rendered = executor.run_framework_command(
        command,
        {"runtime": "config"},
        input_context={"poison": "must not reach resume"},
        style_context={"style_id": "replacement"},
        images=["replacement-image"],
        prepared=object(),
    )

    assert rendered.endswith("Resumed Framework result.")
    assert calls == [(
        "execution-123",
        {
            "config": {"runtime": "config"},
            "trace_dir": None,
            "trace_context": None,
        },
    )]


def test_direct_resume_forces_framework_routing_on_cli_and_server(monkeypatch):
    command = "/framework --resume execution-123"
    wrapped = f"/direct {command}"

    resume_dispatches = [
        boot.effective_framework_dispatch(raw)
        for raw in (command, wrapped)
    ]
    for dispatch, raw in zip(resume_dispatches, (command, wrapped)):
        assert dispatch.effective_input == command
        assert dispatch.raw_input == raw
        assert dispatch.use_pipeline is True

    ordinary_direct = boot.effective_framework_dispatch(
        "/direct Explain this as an ordinary Dialogue."
    )
    assert ordinary_direct.effective_input == (
        "Explain this as an ordinary Dialogue."
    )
    assert ordinary_direct.use_pipeline is False

    # Import the server before patching the CLI's function binding so its
    # module-level shared imports retain their production identities.
    from server import app as server_app

    cli_calls = []

    def cli_pipeline(user_input, _history=None, _output_target="screen", **kwargs):
        cli_calls.append((user_input, kwargs.get("raw_user_input")))
        return "Framework pipeline"

    monkeypatch.setattr(boot, "run_pipeline", cli_pipeline)
    for dispatch in resume_dispatches:
        assert boot.run_agentic_loop(
            dispatch.effective_input,
            [],
            use_pipeline=dispatch.use_pipeline,
            raw_user_input=dispatch.raw_input,
        ) == "Framework pipeline"
    assert cli_calls == [(command, command), (command, wrapped)]

    server_calls = []

    def server_pipeline(user_input, _history, **kwargs):
        server_calls.append((
            "framework",
            user_input,
            kwargs.get("raw_user_input"),
        ))
        yield "Framework pipeline"

    def server_dialogue(user_input, _history, **_kwargs):
        server_calls.append(("dialogue", user_input, None))
        yield "Ordinary Dialogue"

    monkeypatch.setattr(server_app, "_pipeline_stream", server_pipeline)
    monkeypatch.setattr(
        server_app, "_traced_direct_entry_stream", server_dialogue,
    )
    monkeypatch.setattr(
        server_app, "_effective_conversation_tag", lambda *_args: "",
    )

    for index, raw in enumerate((command, wrapped), start=1):
        server_resume_dispatch = server_app.effective_framework_dispatch(raw)
        assert list(server_app.agentic_loop_stream(
            server_resume_dispatch.effective_input,
            [],
            use_pipeline=server_resume_dispatch.use_pipeline,
            panel_id=f"framework-resume-routing-{index}",
            raw_user_input=server_resume_dispatch.raw_input,
        )) == ["Framework pipeline"]
    assert list(server_app.agentic_loop_stream(
        ordinary_direct.effective_input,
        [],
        use_pipeline=ordinary_direct.use_pipeline,
        panel_id="ordinary-direct-routing",
    )) == ["Ordinary Dialogue"]
    assert server_calls == [
        ("framework", command, command),
        ("framework", command, wrapped),
        ("dialogue", "Explain this as an ordinary Dialogue.", None),
    ]


@pytest.mark.parametrize(
    "command",
    [
        "/framework --resume",
        "/framework --resume execution-123 extra",
        "/framework --resume execution-123 --config alternate",
    ],
)
def test_malformed_resume_command_reports_the_exact_usable_syntax(command):
    assert executor.framework_command_has_query(command) is True
    visible = executor.run_framework_command(command, {})
    assert "/framework --resume <execution-id>" in visible


def test_resume_api_does_not_accept_replacement_input_context():
    with pytest.raises(TypeError, match="input_context"):
        executor.resume_framework(
            "execution-123",
            config={},
            input_context={"replacement": True},
        )


def test_normal_failure_exposes_real_resume_without_repeating_completed_work(
    isolated_runtime, monkeypatch,
):
    prepared = _prepared(gears=(2, 2))
    first_calls = []

    def first_run(_fw, milestone, _contract, session, *_args, **_kwargs):
        first_calls.append(milestone.id)
        if milestone.id == "M1":
            return _accepted(session, milestone, f"{MATERIAL} Completed M1.")
        raise RuntimeError("provider transport failed outside milestone error")

    monkeypatch.setattr(executor, "_run_milestone", first_run)
    failed = executor.execute_framework(
        prepared.canonical_filename,
        prepared.original_input,
        config={},
        prepared=prepared,
        execution_id="resume-real-operation",
        conversation_id="conversation-resume",
    )

    assert failed.success is False
    assert failed.resume_available is True
    assert first_calls == ["M1", "M2"]
    assert Path(failed.recovery_path).is_dir()
    assert "Completed M1" in executor.format_execution_result(failed)
    manifest = scratch.ScratchSession.attach(failed.execution_id).manifest()
    assert manifest["canonical_filename"] == prepared.canonical_filename
    assert manifest["original_input"] == prepared.original_input
    assert manifest["effective_input"] == prepared.effective_input
    assert manifest["selected_mode"] == "all"
    assert manifest["project_profile"] == prepared.project_profile
    assert manifest["input_context"] == {}
    assert manifest["resume_identity_digest"].startswith("sha256:")

    resumed_calls = []

    def resumed_run(_fw, milestone, _contract, session, *_args, **_kwargs):
        resumed_calls.append(milestone.id)
        return _accepted(session, milestone, f"{MATERIAL} Completed M2 on resume.")

    monkeypatch.setattr(executor, "prepare_framework_execution", lambda *_a, **_k: prepared)
    monkeypatch.setattr(executor, "_run_milestone", resumed_run)
    isolated_runtime["events"].clear()
    resumed = executor.resume_framework(failed.execution_id, config={})

    assert resumed.success is True
    assert resumed.resumed is True
    assert resumed_calls == ["M2"]
    assert [item.milestone_id for item in resumed.milestones] == ["M1", "M2"]
    assert resumed.final_output.endswith("Completed M2 on resume.")
    assert not Path(failed.recovery_path).exists()
    assert [
        event["milestone_id"] for event in isolated_runtime["events"]
        if event["event_type"] == "MilestoneComplete"
    ] == ["M2"]


def test_resume_repreflights_original_bytes_without_reconsuming_explicit_mode(
    monkeypatch,
):
    original = "Focused Investigate the evidence without changing its wording."
    effective = "Investigate the evidence without changing its wording."
    admitted_context = {
        "style_id": "stored-style",
        "user_context": {"instruction": "retain exact citations"},
    }
    prepared = _prepared(
        gears=(2, 2),
        mode="Focused",
        original_input=original,
        effective_input=effective,
        exact_mode="Focused",
        project_nexus="Projects/Truthful Runtime",
        project_profile="project-profile",
        input_context=admitted_context,
    )

    def first_run(
        _fw, milestone, _contract, session, user_input, _config, **_kwargs,
    ):
        assert user_input == effective
        if milestone.id == "M1":
            return _accepted(session, milestone, f"{MATERIAL} Explicit M1.")
        raise RuntimeError("pause this admitted run")

    monkeypatch.setattr(executor, "_run_milestone", first_run)
    failed = executor.execute_framework(
        prepared.canonical_filename,
        original,
        config={},
        prepared=prepared,
        execution_id="resume-explicit-mode",
        conversation_id="conversation-explicit",
    )
    assert failed.success is False

    preflight_calls = []

    def reprepare(framework_ref, user_input, **kwargs):
        preflight_calls.append((framework_ref, user_input, kwargs))
        return prepared

    resumed_calls = []

    def resumed_run(
        _fw, milestone, _contract, session, user_input, _config, **kwargs,
    ):
        resumed_calls.append((
            milestone.id,
            user_input,
            kwargs["input_context"],
            kwargs["style_context"],
        ))
        return _accepted(session, milestone, f"{MATERIAL} Explicit M2 resumed.")

    monkeypatch.setattr(executor, "prepare_framework_execution", reprepare)
    monkeypatch.setattr(executor, "_run_milestone", resumed_run)
    resumed = executor.resume_framework(failed.execution_id, config={})

    assert resumed.success is True
    assert preflight_calls == [(
        prepared.canonical_filename,
        original,
        {
            "project_nexus": prepared.project_nexus,
            "one_run_profile": prepared.one_run_profile,
            "input_context": admitted_context,
        },
    )]
    assert "requested_mode" not in preflight_calls[0][2]
    assert resumed_calls == [(
        "M2",
        effective,
        admitted_context,
        {"style_id": "stored-style"},
    )]


def test_resume_refuses_structured_contract_drift_hidden_from_raw_text(monkeypatch):
    prepared = _prepared(gears=(2, 2))

    def first_run(_fw, milestone, _contract, session, *_args, **_kwargs):
        if milestone.id == "M1":
            return _accepted(session, milestone, f"{MATERIAL} Bound M1.")
        raise RuntimeError("preserve for resume identity proof")

    monkeypatch.setattr(executor, "_run_milestone", first_run)
    failed = executor.execute_framework(
        prepared.canonical_filename,
        prepared.original_input,
        config={},
        prepared=prepared,
        execution_id="resume-structured-drift",
    )
    assert failed.success is False

    changed_method = replace(
        prepared.contract_for("all", "M1").methods[0],
        body="Changed resolved method body that raw Markdown digest does not see.",
    )
    changed = _with_contract_change(prepared, methods=(changed_method,))
    assert executor._contract_digest(changed) == executor._contract_digest(prepared)
    assert executor._resume_identity_digest(
        changed, selected_mode="all", effective_input=changed.effective_input,
    ) != executor._resume_identity_digest(
        prepared, selected_mode="all", effective_input=prepared.effective_input,
    )
    monkeypatch.setattr(
        executor, "prepare_framework_execution", lambda *_a, **_k: changed,
    )
    monkeypatch.setattr(
        executor,
        "_run_milestone",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("drifted resume must not continue")
        ),
    )

    with pytest.raises(preflight.FrameworkPreflightError, match="identity, contract"):
        executor.resume_framework(failed.execution_id, config={})


def test_resume_refuses_tampered_completed_milestone(monkeypatch):
    prepared = _prepared(gears=(2, 2))

    def first_run(_fw, milestone, _contract, session, *_args, **_kwargs):
        if milestone.id == "M1":
            return _accepted(session, milestone, f"{MATERIAL} Untampered M1.")
        raise RuntimeError("preserve for completed-output proof")

    monkeypatch.setattr(executor, "_run_milestone", first_run)
    failed = executor.execute_framework(
        prepared.canonical_filename,
        prepared.original_input,
        config={},
        prepared=prepared,
        execution_id="resume-tampered-output",
    )
    assert failed.success is False
    session = scratch.ScratchSession.attach(failed.execution_id)
    Path(session.milestone_path("M1")).write_text(
        f"{MATERIAL} Tampered after acceptance.", encoding="utf-8",
    )

    monkeypatch.setattr(
        executor, "prepare_framework_execution", lambda *_a, **_k: prepared,
    )
    resumed_calls = []
    monkeypatch.setattr(
        executor,
        "_run_milestone",
        lambda *_a, **_k: resumed_calls.append(True),
    )
    resumed = executor.resume_framework(failed.execution_id, config={})

    assert resumed.success is False
    assert "completed milestone M1 changed" in resumed.failure_reason
    assert resumed_calls == []


def test_normal_success_emits_existing_handoffs_before_scratch_cleanup(
    isolated_runtime, monkeypatch,
):
    prepared = _prepared()
    observed = []

    def run(_fw, milestone, _contract, session, *_args, **_kwargs):
        return _accepted(session, milestone, f"{MATERIAL} Normal success.")

    def emit(event):
        location = event.get("deliverable_location") or event.get("final_output_location")
        if location:
            assert location["kind"] == "ephemeral_framework_handoff"
            assert Path(location["path"]).is_file()
        observed.append(event)

    monkeypatch.setattr(executor, "_run_milestone", run)
    monkeypatch.setattr(oversight_events, "emit", emit)
    result = executor.execute_framework(
        prepared.canonical_filename,
        prepared.original_input,
        config={},
        prepared=prepared,
        execution_id="normal-success",
        conversation_id="conversation-normal",
    )

    assert result.success is True
    assert observed[-1]["success"] is True
    assert not (isolated_runtime["scratch_root"] / result.execution_id).exists()


@pytest.mark.parametrize("outcome", ["success", "failure", "base-exception"])
def test_stealth_deletes_scratch_on_every_terminal_path(
    outcome, isolated_runtime, monkeypatch,
):
    prepared = _prepared()
    execution_id = f"stealth-{outcome}"
    observed_manifests = []

    def run(_fw, milestone, _contract, session, *_args, **_kwargs):
        if outcome == "success":
            return _accepted(session, milestone, f"{MATERIAL} Stealth success.")
        if outcome == "failure":
            raise RuntimeError("unfavored exception class")
        raise KeyboardInterrupt("abrupt execution interruption")

    def emit(event):
        handoff = event.get("ephemeral_handoff")
        if handoff:
            manifest_path = Path(handoff["path"])
            assert manifest_path.is_file()
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            observed_manifests.append(manifest)
        if event["event_type"] == "FrameworkComplete" and not event["success"]:
            assert event["recovery_path"] is None

    monkeypatch.setattr(executor, "_run_milestone", run)
    monkeypatch.setattr(oversight_events, "emit", emit)
    call = lambda: executor.execute_framework(
        prepared.canonical_filename,
        prepared.original_input,
        config={},
        prepared=prepared,
        execution_id=execution_id,
        conversation_tag="stealth",
        conversation_id="conversation-stealth",
    )

    if outcome == "base-exception":
        with pytest.raises(KeyboardInterrupt):
            call()
    else:
        result = call()
        assert result.success is (outcome == "success")
        if outcome == "failure":
            assert result.resume_available is False
            assert result.recovery_path is None

    assert observed_manifests
    assert observed_manifests[0]["conversation_id"] == "conversation-stealth"
    assert observed_manifests[0]["conversation_tag"] == "stealth"
    assert not (isolated_runtime["scratch_root"] / execution_id).exists()


@pytest.mark.parametrize("failing_write", ["candidate", "manifest", "event"])
def test_stealth_cleanup_surrounds_terminal_failure_writes(
    failing_write, isolated_runtime, monkeypatch,
):
    prepared = _prepared()
    execution_id = f"stealth-terminal-write-{failing_write}"

    if failing_write == "candidate":
        monkeypatch.setattr(
            executor,
            "_run_milestone",
            lambda *_a, **_k: (_ for _ in ()).throw(
                executor.MilestoneExecutionError(
                    "terminal candidate withheld",
                    milestone_id="M1",
                    candidate=MATERIAL,
                )
            ),
        )
        monkeypatch.setattr(
            scratch.ScratchSession,
            "write_unaccepted_candidate",
            lambda *_a, **_k: (_ for _ in ()).throw(
                RuntimeError("candidate write failed")
            ),
        )
    else:
        monkeypatch.setattr(
            executor,
            "_run_milestone",
            lambda *_a, **_k: (_ for _ in ()).throw(
                RuntimeError("milestone execution failed")
            ),
        )
    if failing_write == "manifest":
        monkeypatch.setattr(
            scratch.ScratchSession,
            "mark_failed",
            lambda *_a, **_k: (_ for _ in ()).throw(
                RuntimeError("manifest write failed")
            ),
        )
    if failing_write == "event":
        monkeypatch.setattr(
            oversight_events,
            "emit",
            lambda *_a, **_k: (_ for _ in ()).throw(
                RuntimeError("terminal event write failed")
            ),
        )

    call = lambda: executor.execute_framework(
        prepared.canonical_filename,
        prepared.original_input,
        config={},
        prepared=prepared,
        execution_id=execution_id,
        conversation_tag="stealth",
        conversation_id="conversation-stealth-write",
    )
    if failing_write == "event":
        result = call()
        assert result.success is False
        assert "event delivery also failed" in result.failure_reason
    else:
        with pytest.raises(RuntimeError, match=f"{failing_write} write failed"):
            call()

    assert not (isolated_runtime["scratch_root"] / execution_id).exists()


def test_stealth_cleanup_error_is_surfaced_without_claiming_deletion(
    isolated_runtime, monkeypatch,
):
    prepared = _prepared()
    execution_id = "stealth-cleanup-error"
    monkeypatch.setattr(
        executor,
        "_run_milestone",
        lambda _fw, milestone, _contract, session, *_a, **_k: _accepted(
            session, milestone, f"{MATERIAL} Cleanup error proof.",
        ),
    )
    monkeypatch.setattr(
        scratch.ScratchSession,
        "cleanup",
        lambda *_a, **_k: (_ for _ in ()).throw(
            RuntimeError("Stealth cleanup failed visibly")
        ),
    )

    with pytest.raises(RuntimeError, match="Stealth cleanup failed visibly"):
        executor.execute_framework(
            prepared.canonical_filename,
            prepared.original_input,
            config={},
            prepared=prepared,
            execution_id=execution_id,
            conversation_tag="stealth",
            conversation_id="conversation-stealth-cleanup-error",
        )
    assert (isolated_runtime["scratch_root"] / execution_id).is_dir()


def test_stealth_refusal_creates_no_scratch(isolated_runtime, monkeypatch):
    monkeypatch.setattr(
        executor,
        "prepare_framework_execution",
        lambda *_a, **_k: (_ for _ in ()).throw(
            preflight.FrameworkPreflightError("admission refused")
        ),
    )
    with pytest.raises(preflight.FrameworkPreflightError, match="admission refused"):
        executor.execute_framework(
            "refused.md",
            "unsafe input",
            config={},
            execution_id="stealth-refused",
            conversation_tag="stealth",
            conversation_id="conversation-stealth",
        )
    assert not isolated_runtime["scratch_root"].exists()


def test_closeout_backstop_removes_only_owned_stealth_framework_scratch(
    isolated_runtime,
):
    owned = scratch.ScratchSession.create(
        "Owned",
        execution_id="orphaned-stealth",
        conversation_id="conversation-closeout",
        conversation_tag="stealth",
    )
    normal = scratch.ScratchSession.create(
        "Normal",
        execution_id="retained-normal",
        conversation_id="conversation-closeout",
        conversation_tag="",
    )
    other = scratch.ScratchSession.create(
        "Other",
        execution_id="other-stealth",
        conversation_id="other-conversation",
        conversation_tag="stealth",
    )
    owned.write_unaccepted_candidate("M1", MATERIAL)

    deleted = {}
    errors = []
    closeout._purge_framework_scratch_backstop(
        "conversation-closeout", deleted, errors,
    )

    assert errors == []
    assert deleted["framework_scratch_execution_ids"] == ["orphaned-stealth"]
    assert not Path(owned.folder).exists()
    assert Path(normal.folder).is_dir()
    assert Path(other.folder).is_dir()


def _framework_context(
    contract: preflight.ResolvedMilestoneContract,
) -> dict:
    context = executor._build_context_pkg(
        "Resolved Framework handoff",
        contract,
        contract,
        framework_id="truthful-runtime",
        selected_mode="all",
    )
    context["mode_text"] = "SYNTHESIS_MODE_SENTINEL_MUST_NOT_APPEAR"
    return context


def test_framework_context_preserves_admitted_lanes_without_contract_overwrite():
    contract = _prepared(gears=(4,)).contract_for("all", "M1")
    locks = {"visual_model": "locked-project-model"}
    admitted = {
        "user_context": {"preference": "preserve my citations"},
        "project_nexus": "Projects/Truthful Runtime",
        "model_profile_project_nexus": "Projects/Truthful Runtime",
        "project_profile": "project-profile",
        "style_id": "admitted-style",
        "style_register": "written",
        "model_profile_locks": locks,
        "contributor_bundle": {
            "units": [
                {"id": "user-note", "content": "Do not lose this evidence."},
                {"id": "project-note", "content": "Preserve this project fact."},
            ],
            "sources": [
                {"id": "user-note", "kind": "user"},
                {"id": "project-note", "kind": "project"},
            ],
        },
    }

    context = executor._build_context_pkg(
        "Authoritative admitted handoff",
        contract,
        contract,
        framework_id="truthful-runtime",
        selected_mode="all",
        project_model_locks=locks,
        input_context=admitted,
    )

    assert context["framework_execution"] is True
    assert context["cleaned_prompt"] == "Authoritative admitted handoff"
    assert context["gear"] == contract.gear
    assert context["framework_milestone_contract"]["methods"][0]["body"] == (
        contract.methods[0].body
    )
    assert context["framework_milestone_contract"]["verification_criterion"] == (
        contract.verification_criterion
    )
    assert context["user_context"] == admitted["user_context"]
    assert context["project_nexus"] == admitted["project_nexus"]
    assert context["model_profile_project_nexus"] == admitted[
        "model_profile_project_nexus"
    ]
    assert context["project_profile"] == admitted["project_profile"]
    assert context["style_id"] == "admitted-style"
    assert context["model_profile_locks"] == locks
    assert context["optional_context_units"] == admitted["contributor_bundle"][
        "units"
    ]
    assert context["context_source_inventory"]["sources"] == admitted[
        "contributor_bundle"
    ]["sources"]


@pytest.mark.parametrize(
    "reserved_key, poison",
    [
        ("framework_execution", False),
        ("framework_milestone_contract", {"methods": [], "gear": 2}),
        ("gear", 2),
        ("cleaned_prompt", "replacement prompt"),
        ("framework_mode", "replacement mode"),
        ("milestone_id", "replacement milestone"),
        ("execution_review", {"verdict": "PASS"}),
        ("optional_context_units", [{"content": "replacement contributor"}]),
        ("_trace_effective_gear", 2),
    ],
)
def test_framework_context_rejects_reserved_runtime_poisoning(
    reserved_key, poison,
):
    contract = _prepared(gears=(4,)).contract_for("all", "M1")
    with pytest.raises(preflight.FrameworkPreflightError, match="reserved execution"):
        executor._build_context_pkg(
            "Authoritative admitted handoff",
            contract,
            contract,
            framework_id="truthful-runtime",
            selected_mode="all",
            input_context={reserved_key: poison},
        )


def test_framework_context_rejects_unauthenticated_profile_lock_replacement():
    contract = _prepared(gears=(4,)).contract_for("all", "M1")
    with pytest.raises(preflight.FrameworkPreflightError, match="authenticated"):
        executor._build_context_pkg(
            "Authoritative admitted handoff",
            contract,
            contract,
            framework_id="truthful-runtime",
            selected_mode="all",
            project_model_locks={"visual_model": "authenticated"},
            input_context={"model_profile_locks": {"visual_model": "poison"}},
        )


def _isolate_prompt_inputs(monkeypatch):
    monkeypatch.setattr(
        boot,
        "load_boot_md",
        lambda **_kwargs: "# Ora\n\nFollow the admitted contract truthfully.",
    )
    monkeypatch.setattr(boot, "_compose_output_style", lambda _context: "")
    monkeypatch.setattr(
        boot,
        "load_mode",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Framework execution must not load a Dialogue mode")
        ),
    )


def test_every_framework_role_uses_the_resolved_contract_and_gear4_purpose(
    monkeypatch,
):
    contract = _prepared(gears=(4,)).contract_for("all", "M1")
    context = _framework_context(contract)
    _isolate_prompt_inputs(monkeypatch)

    roles = [
        ("analyst", "depth"),
        ("analyst", "breadth"),
        ("evaluator", "depth"),
        ("reviser", "depth"),
        ("verifier", "breadth"),
        ("consolidator", "breadth"),
        ("formatter", "depth"),
    ]
    prompts = [
        boot.build_system_prompt_for_gear(context, slot=slot, step=step)
        for step, slot in roles
    ]

    for prompt in prompts:
        assert contract.methods[0].body in prompt
        assert contract.output_format in prompt
        assert contract.verification_criterion in prompt
        assert "EXACT GEAR: 4" in prompt
        assert "GEAR 4 SECOND-LANE PURPOSE: both" in prompt
        assert "later convergence is not independent proof" in prompt
        assert "SYNTHESIS_MODE_SENTINEL_MUST_NOT_APPEAR" not in prompt
        assert "SUPPLEMENTAL RAG PROTOCOL" not in prompt
    assert "analyst — depth lane" in prompts[0]
    assert "analyst — breadth lane" in prompts[1]


def test_framework_gears_refuse_missing_lanes_instead_of_falling_back(
    monkeypatch,
):
    _isolate_prompt_inputs(monkeypatch)
    real_run_gear3 = boot.run_gear3
    gear4_contract = _prepared(gears=(4,)).contract_for("all", "M1")
    gear4_context = _framework_context(gear4_contract)
    fallback_calls = []
    monkeypatch.setattr(
        boot, "resolve_gear4_endpoints",
        lambda *_a, **_k: (None, {"name": "breadth"}, False),
    )
    monkeypatch.setattr(
        boot, "run_gear3", lambda *_a, **_k: fallback_calls.append(True),
    )
    with pytest.raises(boot.FrameworkExecutionFailure) as gear4_error:
        boot.run_gear4(gear4_context, {})
    assert gear4_error.value.terminal_state == "degraded"
    assert fallback_calls == []

    gear3_contract = _prepared(gears=(3,)).contract_for("all", "M1")
    gear3_context = _framework_context(gear3_contract)
    monkeypatch.setattr(
        boot,
        "get_analysis_slot_endpoint",
        lambda _config, slot, *_a, **_k: (
            {"name": "depth"} if slot == "depth" else None
        ),
    )
    monkeypatch.setattr(boot, "_prepare_image_routing", lambda *_a, **_k: None)
    monkeypatch.setattr(
        boot,
        "_call_with_retry",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("single-analyst fallback must not execute")
        ),
    )
    with pytest.raises(boot.FrameworkExecutionFailure) as gear3_error:
        real_run_gear3(gear3_context, {})
    assert gear3_error.value.terminal_state == "degraded"


@pytest.mark.parametrize(
    "response",
    [
        None,
        "",
        "I need more context before I can provide the requested result.",
        "[Error calling OpenRouter API: transport unavailable and request failed]",
    ],
)
def test_pipeline_boundary_rejects_wrong_empty_refusal_and_diagnostic_results(
    response, monkeypatch,
):
    _isolate_prompt_inputs(monkeypatch)
    contract = _prepared(gears=(2,)).contract_for("all", "M1")
    monkeypatch.setattr(
        boot,
        "resolve_single_pass_endpoint",
        lambda *_a, **_k: ({"name": "single-pass"}, "breadth"),
    )
    monkeypatch.setattr(
        boot, "run_single_pass_with_tools", lambda *_a, **_k: response,
    )
    with pytest.raises(executor.FrameworkPipelineError):
        executor._run_through_gear_pipeline(
            "Resolved handoff",
            contract,
            contract,
            {},
            framework_id="truthful-runtime",
            selected_mode="all",
        )


@pytest.mark.parametrize("verdict", [None, "FAIL", "BROKEN"])
def test_pipeline_boundary_requires_a_real_final_criterion_pass(
    verdict, monkeypatch,
):
    _isolate_prompt_inputs(monkeypatch)
    contract = _prepared(gears=(3,)).contract_for("all", "M1")

    def incomplete_gear3(context, *_args, **_kwargs):
        if verdict is not None:
            context["execution_review"] = {
                "verdict": verdict,
                "scope": "text_review",
                "status": (
                    "review-unavailable-withheld"
                    if verdict == "BROKEN" else "failed-withheld"
                ),
            }
        return f"{MATERIAL} Candidate lacking a passing final criterion."

    monkeypatch.setattr(boot, "run_gear3", incomplete_gear3)
    with pytest.raises(executor.FrameworkPipelineError):
        executor._run_through_gear_pipeline(
            "Resolved handoff",
            contract,
            contract,
            {},
            framework_id="truthful-runtime",
            selected_mode="all",
        )


def _patch_analytical_side_effects(monkeypatch):
    _isolate_prompt_inputs(monkeypatch)
    real_load_framework = boot.load_framework

    def load_framework(name):
        if name == "f-quality-gate.md":
            return CONTRADICTORY_QUALITY_SCAFFOLD
        return real_load_framework(name)

    monkeypatch.setattr(boot, "load_framework", load_framework)
    monkeypatch.setattr(boot, "PIPELINE_TRACE_AVAILABLE", False)
    monkeypatch.setattr(boot, "_prepare_image_routing", lambda *_a, **_k: None)
    monkeypatch.setattr(
        boot,
        "_capture_visual_candidates",
        lambda text, *_a, **_k: text,
    )
    monkeypatch.setattr(
        boot, "_append_visual_type_preflight", lambda text, *_a, **_k: text,
    )
    monkeypatch.setattr(
        boot,
        "_run_claim_verification_preflight",
        lambda *_a, **_k: (
            "", [], {"status": "not_needed", "reason": "none"}, [],
        ),
    )
    monkeypatch.setattr(
        boot,
        "_run_unflagged_claim_scan",
        lambda *_a, **_k: ("", {"status": "not_needed"}, []),
    )
    monkeypatch.setattr(boot, "_env_flag", lambda *_a, **_k: False)
    monkeypatch.setattr(boot, "vision_capable_for_endpoint", lambda *_a: True)


def test_gear3_is_one_authoritative_sequential_lane(monkeypatch):
    _patch_analytical_side_effects(monkeypatch)
    contract = _prepared(gears=(3,)).contract_for("all", "M1")
    context = _framework_context(contract)
    depth = {"name": "depth"}
    breadth = {"name": "breadth"}
    order = []
    quality_prompts = []
    monkeypatch.setattr(
        boot,
        "get_analysis_slot_endpoint",
        lambda _config, slot, *_a, **_k: depth if slot == "depth" else breadth,
    )
    monkeypatch.setattr(
        boot,
        "get_slot_endpoint",
        lambda _config, _slot, **_kwargs: breadth,
    )

    def supplement(_messages, _endpoint, role, *_args, **_kwargs):
        order.append(role)
        if role == "analyst":
            return f"## Analysis\n\n{MATERIAL} Gear 3 analyst.", True, "ok"
        if role == "evaluator":
            return f"## Evaluation\n\n{MATERIAL} Gear 3 evaluation.", True, "ok"
        if role == "reviser":
            return (
                f"## ADDRESSED\n\nAll findings.\n\n## REVISED DRAFT\n\n"
                f"{MATERIAL} Gear 3 revised result.\n\n## CHANGELOG\n\nReviewed."
            ), True, "ok"
        if role == "verifier":
            return "VERDICT: PASS\n\nAll milestone checks pass with evidence.", True, "ok"
        raise AssertionError(role)

    def retry(messages, _endpoint, role, *_args, **_kwargs):
        order.append(role)
        assert role == "quality-gate"
        quality_prompts.append(messages[0]["content"])
        return "VERDICT: PASS\n\nThe final criterion passes with evidence.", True, "ok"

    monkeypatch.setattr(boot, "_call_with_supplement", supplement)
    monkeypatch.setattr(boot, "_call_with_retry", retry)
    monkeypatch.setattr(boot, "CLAIM_VERIFICATION_AVAILABLE", True)
    monkeypatch.setattr(
        boot,
        "extract_revised_draft_section",
        lambda _text: f"{MATERIAL} Gear 3 revised result.",
    )

    result = boot.run_gear3(context, {})

    assert result.endswith("Gear 3 revised result.")
    assert order == ["analyst", "evaluator", "reviser", "verifier", "quality-gate"]
    assert quality_prompts
    for prompt in quality_prompts:
        assert CONTRADICTORY_QUALITY_SCAFFOLD in prompt
        assert FRAMEWORK_RELEASE_OVERRIDE in prompt
        override_start = prompt.index(
            f"=== {FRAMEWORK_RELEASE_OVERRIDE} ==="
        )
        assert prompt.rfind(CONTRADICTORY_QUALITY_SCAFFOLD) < override_start
        controlling_tail = prompt[override_start:]
        assert "Only a real final `VERDICT: PASS`" in controlling_tail
        assert "`VERDICT: FAIL`" in controlling_tail
        assert "`VERDICT: BROKEN`" in controlling_tail
        assert contract.verification_criterion in controlling_tail
        assert contract.output_format in controlling_tail
    assert context["execution_review"]["verdict"] == "PASS"
    assert context["framework_execution_state"]["success"] is True


def test_gear4_keeps_original_and_post_review_convergence_truth(monkeypatch):
    _patch_analytical_side_effects(monkeypatch)
    contract = _prepared(gears=(4,)).contract_for("all", "M1")
    context = _framework_context(contract)
    depth = {"name": "depth"}
    breadth = {"name": "breadth"}
    endpoints = {
        "consolidation": {"name": "consolidator"},
        "formatter": {"name": "formatter"},
        "verification": {"name": "criterion-judge"},
    }
    calls = []
    monkeypatch.setattr(
        boot, "resolve_gear4_endpoints",
        lambda *_a, **_k: (depth, breadth, True),
    )
    monkeypatch.setattr(
        boot,
        "get_slot_endpoint",
        lambda _config, slot, **_kwargs: endpoints.get(slot),
    )

    originals = {
        "depth": f"## Depth original\n\n{MATERIAL} DEPTH-ORIGINAL-CLAIM.",
        "breadth": f"## Breadth original\n\n{MATERIAL} BREADTH-ORIGINAL-CLAIM.",
    }
    revisions = {
        "depth": (
            "## ADDRESSED\n\nReviewed.\n\n## REVISED DRAFT\n\n"
            f"{MATERIAL} DEPTH-REVISED-CLAIM.\n\n## CHANGELOG\n\nChanged."
        ),
        "breadth": (
            "## ADDRESSED\n\nReviewed.\n\n## REVISED DRAFT\n\n"
            f"{MATERIAL} BREADTH-REVISED-CLAIM.\n\n## CHANGELOG\n\nChanged."
        ),
    }

    def supplement(messages, endpoint, role, *_args, **_kwargs):
        calls.append((role, endpoint["name"], messages[0]["content"], messages[-1]["content"]))
        endpoint_name = endpoint["name"]
        if role == "analyst":
            return originals[endpoint_name], True, "ok"
        if role == "evaluator":
            return f"## Evaluation\n\n{MATERIAL} Cross-review from {endpoint_name}.", True, "ok"
        if role == "reviser":
            return revisions[endpoint_name], True, "ok"
        if role == "verifier":
            return "VERDICT: PASS\n\nOriginal and revised claims satisfy the criterion.", True, "ok"
        if role == "consolidator":
            return (
                "## Corroboration and convergence\n\nInitial independent "
                "agreement remains separate from post-review convergence and "
                "material disagreement.\n\n## Consolidated result\n\n" + MATERIAL
            ), True, "ok"
        raise AssertionError(role)

    def retry(messages, endpoint, role, *_args, **_kwargs):
        calls.append((role, endpoint["name"], messages[0]["content"], messages[-1]["content"]))
        if role == "formatter":
            return f"## Final result\n\n{MATERIAL} User-facing Gear 4 result.", True, "ok"
        if role == "quality-gate":
            return "VERDICT: PASS\n\nThe controlling Framework criterion passes.", True, "ok"
        raise AssertionError(role)

    monkeypatch.setattr(boot, "_call_with_supplement", supplement)
    monkeypatch.setattr(boot, "_call_with_retry", retry)

    result = boot.run_gear4(context, {})

    assert result.endswith("User-facing Gear 4 result.")
    analyst_calls = [call for call in calls if call[0] == "analyst"]
    assert {call[1] for call in analyst_calls} == {"depth", "breadth"}
    verifier_users = [call[3] for call in calls if call[0] == "verifier"]
    assert len(verifier_users) == 2
    for user_prompt in verifier_users:
        assert "DEPTH-ORIGINAL-CLAIM" in user_prompt
        assert "BREADTH-ORIGINAL-CLAIM" in user_prompt
        assert "DEPTH-REVISED-CLAIM" in user_prompt
        assert "BREADTH-REVISED-CLAIM" in user_prompt
        assert "INITIAL INDEPENDENT ANALYST DRAFTS" in user_prompt
        assert "POST-CROSS-REVIEW DRAFTS" in user_prompt
    for role in ("consolidator", "formatter", "quality-gate"):
        user_prompt = next(call[3] for call in calls if call[0] == role)
        assert "INITIAL INDEPENDENT ANALYST DRAFTS" in user_prompt
        assert "POST-CROSS-REVIEW DRAFTS" in user_prompt
    for _role, _endpoint, system_prompt, _user_prompt in calls:
        assert "GEAR 4 SECOND-LANE PURPOSE: both" in system_prompt
        assert contract.verification_criterion in system_prompt
    quality_prompts = [
        call[2] for call in calls if call[0] == "quality-gate"
    ]
    assert quality_prompts
    for prompt in quality_prompts:
        assert CONTRADICTORY_QUALITY_SCAFFOLD in prompt
        assert FRAMEWORK_RELEASE_OVERRIDE in prompt
        override_start = prompt.index(
            f"=== {FRAMEWORK_RELEASE_OVERRIDE} ==="
        )
        assert prompt.rfind(CONTRADICTORY_QUALITY_SCAFFOLD) < override_start
        controlling_tail = prompt[override_start:]
        assert "Only a real final `VERDICT: PASS`" in controlling_tail
        assert "`VERDICT: FAIL`" in controlling_tail
        assert "`VERDICT: BROKEN`" in controlling_tail
        assert contract.verification_criterion in controlling_tail
        assert contract.output_format in controlling_tail

    convergence = context["framework_convergence"]
    assert convergence["initial_independent_drafts"] == originals
    assert convergence["post_cross_review_drafts"] == revisions
    assert context["execution_review"]["verdict"] == "PASS"
    assert context["framework_execution_state"]["success"] is True
