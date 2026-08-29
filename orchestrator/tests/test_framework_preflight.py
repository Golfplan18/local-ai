"""Behavioral proof for the shared actionable Framework preflight.

This intentionally concentrates the changed contract and every actionable
route in one quarantined batch.  No live provider or persistent Ora data path
is used.
"""
from __future__ import annotations

import builtins
import io
import json
import os
import sys
import types
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import mock

import pytest


HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = os.path.dirname(HERE)
if ORCH not in sys.path:
    sys.path.insert(0, ORCH)

import framework_elicitation as elicitation  # noqa: E402
import framework_input_gap as input_gap  # noqa: E402
import framework_preflight as preflight  # noqa: E402
import milestone_executor as executor  # noqa: E402
import triggers  # noqa: E402


VALID_FRAMEWORK = """# Conforming Test Framework

## MILESTONES DELIVERED

### Milestone 1: Grounded plan
- **Endpoint produced:** A grounded plan.
- **Verification criterion:** The plan names the user's exact objective.
- **Methods:** gather
- **Required prior milestones:** None
- **External prerequisites:** None
- **Gear:** 3
- **Output format:** Markdown plan.
- **Drift check question:** Does the plan preserve the request?

### Milestone 2: Reviewed result
- **Endpoint produced:** A reviewed result.
- **Verification criterion:** The result uses the plan and every supplied source.
- **Methods:** synthesize
- **Required prior milestones:** M1
- **External prerequisites:** None
- **Gear:** 4
- **Gear 4 purpose:** both
- **Output format:** Markdown result.
- **Drift check question:** Does the result preserve the request?

## EXECUTION METHODS

### METHOD gather: Gather authoritative inputs
Use the user's messages verbatim as the authority for the plan.

### METHOD synthesize: Synthesize without substitution
Use the resolved prior deliverable and every explicit contributor source.
"""


@pytest.fixture
def framework_repo(tmp_path, monkeypatch):
    registry: dict[str, str] = {}
    monkeypatch.setattr(preflight._parser, "FRAMEWORKS_DIR", str(tmp_path))

    def install(filename: str, text: str) -> str:
        canonical = filename if filename.endswith(".md") else filename + ".md"
        (tmp_path / canonical).write_text(text, encoding="utf-8")
        stem = canonical[:-3]
        registry[stem.casefold()] = canonical
        registry[canonical.casefold()] = canonical
        return canonical

    def resolve(value: str) -> str:
        key = Path(str(value or "").strip()).name.casefold()
        if key in registry:
            return registry[key]
        if key.endswith(".md") and key[:-3] in registry:
            return registry[key[:-3]]
        raise ValueError(f"{value} is not registered as a user-invocable framework")

    monkeypatch.setattr(preflight, "resolve_user_invocable_framework", resolve)
    monkeypatch.setattr(executor, "resolve_user_invocable_framework", resolve)
    return install


@pytest.fixture(autouse=True)
def isolated_approval_auth(tmp_path, monkeypatch):
    import tool_events

    key_path = tmp_path / "approval-state" / "approval.auth.key"
    monkeypatch.setattr(
        tool_events, "_approval_key_path", lambda: str(key_path),
    )


@pytest.fixture(autouse=True)
def isolated_model_profile_resolution(monkeypatch):
    """Keep the behavioral batch off installed profiles and providers."""
    import model_profiles

    def resolve(**kwargs):
        chain = []
        for source, key in (
            ("global", "global_profile"),
            ("process", "process_profile"),
            ("step", "step_profile"),
            ("one_run", "one_run_profile"),
        ):
            value = kwargs.get(key)
            if isinstance(value, str) and value:
                chain.append({
                    "source": source,
                    "name": value,
                    "runtime_name": value,
                })
        if not chain:
            chain.append({
                "source": "global",
                "name": "test-global",
                "runtime_name": "test-global",
            })
        return {"selected": dict(chain[-1]), "chain": chain}

    monkeypatch.setattr(model_profiles, "resolve_effective_profile", resolve)


def _valid(framework_repo, filename: str = "conforming.md") -> str:
    return framework_repo(filename, VALID_FRAMEWORK)


class _Scratch:
    execution_id = "quarantined-execution"
    session_dir = Path("/quarantined/no-write")

    def __init__(self):
        self.values: dict[str, str] = {}
        self.completed = False
        self.cleaned = False

    def read_all_prior(self, ids):
        return {identity: self.values[identity] for identity in ids if identity in self.values}

    def write_milestone(self, identity, value):
        self.values[identity] = value

    def mark_complete(self):
        self.completed = True

    def cleanup(self):
        self.cleaned = True

    def mark_failed(self, **_kwargs):
        raise AssertionError("valid proof must not fail scratch")


def test_conforming_direct_execution_resolves_everything_and_preserves_inputs(
    framework_repo, monkeypatch,
):
    filename = _valid(framework_repo)
    scratch = _Scratch()
    handoffs: list[str] = []
    contracts = []
    emitted = []

    def run_milestone(fw, milestone, contract, session, user_input, _config, **_kwargs):
        packet = executor._build_handoff_packet(
            fw, milestone, contract, session, user_input,
        )
        handoffs.append(packet)
        contracts.append(contract)
        deliverable = f"deliverable-{milestone.id}"
        session.write_milestone(milestone.id, deliverable)
        return executor.MilestoneResult(
            milestone.id, milestone.name, deliverable,
            "IN_SCOPE", "resolved", 1,
        )

    fake_boot = types.SimpleNamespace(load_routing_config=lambda: {})
    fake_persona = types.SimpleNamespace(resolve_persona=lambda **_kwargs: None)
    fake_events = types.SimpleNamespace(emit=lambda event: emitted.append(event))
    with mock.patch.dict(sys.modules, {
        "boot": fake_boot,
        "persona": fake_persona,
        "oversight_events": fake_events,
    }), mock.patch.object(executor.ScratchSession, "create", return_value=scratch), \
         mock.patch.object(executor, "_run_milestone", side_effect=run_milestone), \
         mock.patch.object(executor, "_resolve_milestone_model_profile", return_value={
             "selected": {"runtime_name": None},
         }), mock.patch.object(executor, "_authenticated_project_visual_locks", return_value=None), \
         mock.patch.object(executor, "_lookup_framework_default_configuration", return_value=None):
        result = executor.execute_framework(
            filename,
            "Keep THIS wording exactly.",
            config={},
            input_context={
                "contributor_bundle": {
                    "sources": [{"id": "source-a"}, {"id": "source-b"}],
                    "units": [
                        {"source_id": "source-a", "content": "alpha"},
                        {"source_id": "source-b", "content": "beta"},
                    ],
                },
            },
        )

    assert result.success is True
    assert result.final_output == "deliverable-M2"
    assert scratch.completed and scratch.cleaned
    assert len(contracts) == 2
    assert [method.id for method in contracts[0].methods] == ["gather"]
    assert contracts[1].required_prior == ("M1",)
    assert contracts[1].gear4_purpose == "both"
    assert "Keep THIS wording exactly." in handoffs[0]
    assert "Use the user's messages verbatim" in handoffs[0]
    assert "deliverable-M1" in handoffs[1]
    assert "<missing>" not in "\n".join(handoffs)
    assert "(none parsed)" not in "\n".join(handoffs)
    assert [event["event_type"] for event in emitted] == [
        "FrameworkStarted", "MilestoneComplete", "MilestoneComplete", "FrameworkComplete",
    ]

    context_pkg = executor._build_context_pkg(
        handoffs[-1],
        preflight._parser.parse_framework_text(VALID_FRAMEWORK).all_milestones()[-1],
        input_context={
            "contributor_bundle": {
                "sources": [{"id": "source-a"}, {"id": "source-b"}],
                "units": [
                    {"source_id": "source-a", "content": "alpha"},
                    {"source_id": "source-b", "content": "beta"},
                ],
            },
        },
    )
    assert [unit["source_id"] for unit in context_pkg["optional_context_units"]] == [
        "source-a", "source-b",
    ]
    inventory = context_pkg["context_source_inventory"]
    assert isinstance(inventory, dict)
    assert [source["id"] for source in inventory["sources"]] == [
        "source-a", "source-b",
    ]
    assert inventory["global_retrieved_units"] == 0
    assert inventory["global_excluded_units"] == 0


def test_contributors_reach_gear2_and_adversarial_dispatch_context(monkeypatch):
    import boot

    bundle = {
        "sources": [{"id": "source-a"}, {"id": "source-b"}],
        "units": [
            {"id": "unit-a", "source_id": "source-a", "content": "alpha"},
            {"id": "unit-b", "source_id": "source-b", "content": "beta"},
        ],
    }
    captured = {}

    monkeypatch.setattr(boot, "load_mode", lambda _mode: "mode text")
    monkeypatch.setattr(
        boot,
        "resolve_single_pass_endpoint",
        lambda *_args, **_kwargs: ({"id": "fast"}, "gear2_rag_lookup"),
    )
    monkeypatch.setattr(
        boot, "build_system_prompt_for_gear", lambda *_args, **_kwargs: "system",
    )

    def physical_call(_messages, _endpoint, **_kwargs):
        state = boot._OPTIONAL_CONTEXT_CV.get()
        captured[2] = {
            "units": [dict(unit) for unit in state["units"]],
            "inventory": dict(state["inventory"]),
        }
        return "gear-2"

    def adversarial(gear):
        def run(context_pkg, *_args, **_kwargs):
            captured[gear] = context_pkg
            return f"gear-{gear}"
        return run

    monkeypatch.setattr(boot, "_run_model_with_tools", physical_call)
    monkeypatch.setattr(boot, "run_gear3", adversarial(3))
    monkeypatch.setattr(boot, "run_gear4", adversarial(4))

    for gear in (2, 3, 4):
        output = executor._run_through_gear_pipeline(
            "handoff",
            types.SimpleNamespace(id=f"M{gear}", gear=gear),
            {},
            input_context={"contributor_bundle": bundle},
        )
        assert output == f"gear-{gear}"

    assert [unit["source_id"] for unit in captured[2]["units"]] == [
        "source-a", "source-b",
    ]
    assert [row["id"] for row in captured[2]["inventory"]["sources"]] == [
        "source-a", "source-b",
    ]
    for gear in (3, 4):
        assert [
            row["id"]
            for row in captured[gear]["context_source_inventory"]["sources"]
        ] == ["source-a", "source-b"]


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (
            lambda text: text + "\n### METHOD gather: Duplicate\nDo something else.\n",
            "duplicate declaration",
        ),
        (
            lambda text: text.replace(
                "### METHOD gather: Gather authoritative inputs\n"
                "Use the user's messages verbatim as the authority for the plan.\n",
                "```markdown\n### METHOD gather: Fenced fake\n"
                "This example is not executable.\n```\n",
            ),
            "fenced example",
        ),
        (
            lambda text: text.replace("- **Methods:** gather", "- **Methods:** missing"),
            "unresolved method",
        ),
        (
            lambda text: text.replace("- **Gear:** 3", "- **Gear:** Gear 3"),
            "exact model-executed Gear value",
        ),
        (
            lambda text: text.replace("- **Required prior milestones:** M1", "- **Required prior milestones:** M9"),
            "unresolved earlier prior",
        ),
        (
            lambda text: text.replace("- **External prerequisites:** None", "- **External prerequisites:** source.db", 1),
            "unresolved external prerequisite",
        ),
        (
            lambda text: text.replace("- **Gear 4 purpose:** both\n", ""),
            "Gear 4 purpose",
        ),
        (
            lambda text: text.replace(
                "The plan names the user's exact objective.", "[criterion]",
            ),
            "verification criterion",
        ),
    ],
)
def test_partial_duplicate_and_fenced_contracts_refuse_as_one_boundary(
    framework_repo, mutate, expected,
):
    filename = framework_repo("invalid.md", mutate(VALID_FRAMEWORK))
    with pytest.raises(preflight.FrameworkPreflightError, match=expected):
        preflight.prepare_framework_execution(filename, "authoritative request")


def test_external_prerequisites_resolve_only_from_caller_owned_values(framework_repo):
    text = VALID_FRAMEWORK.replace(
        "- **External prerequisites:** None",
        "- **External prerequisites:** source.db",
        1,
    )
    filename = framework_repo("external.md", text)
    caller_context = {
        "framework_prerequisites": {
            "source.db": {"ready": True, "flags": ["admitted"]},
        },
        "nested": {"values": ["original"]},
    }
    prepared = preflight.prepare_framework_execution(
        filename,
        "authoritative request",
        input_context=caller_context,
    )
    contract = prepared.contract_for("all", "M1")
    caller_context["framework_prerequisites"]["source.db"]["flags"].append(
        "mutated"
    )
    caller_context["nested"]["values"].append("mutated")

    prerequisite = contract.external_prerequisites[0][1]
    assert prerequisite["flags"] == ("admitted",)
    assert prepared.input_context["nested"]["values"] == ("original",)
    assert not isinstance(prepared.framework, preflight._parser.Framework)
    with pytest.raises(FrozenInstanceError):
        contract.gear = 2
    with pytest.raises(TypeError):
        prerequisite["ready"] = False
    with pytest.raises(TypeError):
        prepared.input_context["nested"]["values"] = ("changed",)

    execution_copy = preflight.prepared_input_context(prepared)
    execution_copy["nested"]["values"].append("execution-only")
    assert prepared.input_context["nested"]["values"] == ("original",)


def test_command_boundary_preserves_multiline_markdown_and_original_bytes(
    framework_repo, monkeypatch,
):
    filename = _valid(framework_repo)
    query = (
        "First line  stays\n"
        "```python\nvalue  =  {'a':  1}\n```\n"
        "| left |  right |\n| --- | --- |\n"
        "Trailing spaces stay  \n"
    )
    command = f"/framework\t{filename}\n{query}"

    parsed_filename, parsed_query, profile = executor.parse_framework_command(
        command,
    )
    prepared = preflight.preflight_framework_command(command)

    assert parsed_filename == filename
    assert executor.is_framework_command(command)
    assert parsed_query == query
    assert profile is None
    assert prepared.original_input == query
    assert prepared.effective_input == query

    import boot

    monkeypatch.setattr(boot, "_is_known_style_id", lambda value: value == "known")
    wrapped_commands = [
        f"/direct /framework {filename} {query}",
        f"/save result.md /framework {filename} {query}",
        f"/saveboth result.md /framework {filename} {query}",
        f"/style known /framework {filename} {query}",
        f"/risk high /framework {filename} {query}",
        f"/risk high /direct /framework {filename} {query}",
        f"/risk high /save result.md /framework {filename} {query}",
        f"/risk high /style known /framework {filename} {query}",
    ]
    for wrapped in wrapped_commands:
        effective = boot.framework_dispatch_input(wrapped)
        assert effective == f"/framework {filename} {query}"
        assert preflight.preflight_framework_command(effective).original_input == query
    unknown_style = f"/style unknown /framework {filename} {query}"
    assert boot.framework_dispatch_input(unknown_style) == unknown_style
    dispatch = boot.effective_framework_dispatch(
        f"/risk high /style known /saveboth result.md /framework {filename} {query}"
    )
    assert dispatch.raw_input.startswith("/risk high")
    assert dispatch.effective_input == f"/framework {filename} {query}"
    assert dispatch.risk_override == "high-risk"
    assert dispatch.style_id == "known"
    assert dispatch.output_target == "both:result.md"


def test_effective_model_profiles_are_admitted_once_and_inline_profile_survives_elicitation(
    framework_repo, monkeypatch,
):
    import model_profiles

    filename = framework_repo(
        "profiled.md",
        VALID_FRAMEWORK.replace(
            "- **Gear:** 3\n",
            "- **Gear:** 3\n- **Model Profile:** step-profile\n",
            1,
        ),
    )
    calls = []

    def resolve(**kwargs):
        calls.append(dict(kwargs))
        winner = (
            kwargs.get("one_run_profile")
            or kwargs.get("step_profile")
            or kwargs.get("process_profile")
            or "test-global"
        )
        chain = [{
            "source": "resolved",
            "name": winner,
            "runtime_name": winner,
        }]
        return {"selected": dict(chain[-1]), "chain": chain}

    monkeypatch.setattr(model_profiles, "resolve_effective_profile", resolve)
    prepared = preflight.preflight_framework_command(
        f"/framework {filename} --config inline-profile exact query"
    )

    assert prepared.one_run_profile == "inline-profile"
    assert prepared.selector_profile_resolution["selected"]["runtime_name"] == "inline-profile"
    assert all(
        contract.model_profile_resolution["selected"]["runtime_name"]
        == "inline-profile"
        for contract in prepared.contracts.values()
    )
    assert any(call.get("step_profile") == "step-profile" for call in calls)
    assert all(call.get("one_run_profile") == "inline-profile" for call in calls)

    captured = {}
    monkeypatch.setattr(
        elicitation,
        "_run_elicitation_turn",
        lambda *args, **kwargs: captured.update(kwargs) or "started",
    )
    assert elicitation.start_elicitation(
        filename,
        [],
        {},
        initial_user_message="exact query",
        conversation_id="conv-profile",
        prepared=prepared,
    ) == "started"
    assert captured["one_run_profile"] == "inline-profile"

    monkeypatch.setattr(
        model_profiles,
        "resolve_effective_profile",
        mock.Mock(side_effect=AssertionError("profile re-resolved after admission")),
    )
    scratch = _Scratch()

    def run_milestone(_fw, milestone, _contract, session, *_args, **_kwargs):
        deliverable = f"profiled-{milestone.id}"
        session.write_milestone(milestone.id, deliverable)
        return executor.MilestoneResult(
            milestone.id, milestone.name, deliverable,
            "IN_SCOPE", "captured profile", 1,
        )

    with mock.patch.dict(sys.modules, {
        "boot": types.SimpleNamespace(load_routing_config=lambda: {}),
        "persona": types.SimpleNamespace(resolve_persona=lambda **_kwargs: None),
        "oversight_events": types.SimpleNamespace(emit=lambda _event: None),
    }), mock.patch.object(executor.ScratchSession, "create", return_value=scratch), \
         mock.patch.object(executor, "_run_milestone", side_effect=run_milestone), \
         mock.patch.object(executor, "_authenticated_project_visual_locks", return_value=None):
        result = executor.execute_framework(
            filename,
            "exact query",
            config={},
            config_name="inline-profile",
            prepared=prepared,
        )
    assert result.success is True
    assert result.final_output == "profiled-M2"

    scratch_create = mock.Mock(side_effect=AssertionError("scratch reached"))
    with mock.patch.object(executor.ScratchSession, "create", scratch_create):
        with pytest.raises(
            preflight.FrameworkPreflightError,
            match="Model Profile chain could not be resolved",
        ):
            executor.execute_framework(
                filename,
                "new request",
                config={},
                config_name="unresolvable-profile",
            )
    scratch_create.assert_not_called()


def test_direct_refusal_occurs_before_scratch_model_or_events(framework_repo):
    filename = framework_repo(
        "invalid-direct.md",
        VALID_FRAMEWORK.replace("- **Gear 4 purpose:** both\n", ""),
    )
    scratch_create = mock.Mock(side_effect=AssertionError("scratch reached"))
    model_path = mock.Mock(side_effect=AssertionError("model reached"))
    emitted = []
    fake_events = types.SimpleNamespace(emit=lambda event: emitted.append(event))
    with mock.patch.object(executor.ScratchSession, "create", scratch_create), \
         mock.patch.object(executor, "_run_through_gear_pipeline", model_path), \
         mock.patch.dict(sys.modules, {"oversight_events": fake_events}):
        with pytest.raises(preflight.FrameworkPreflightError):
            executor.execute_framework(filename, "do it", config={})
    scratch_create.assert_not_called()
    model_path.assert_not_called()
    assert emitted == []

    output = executor.run_framework_command(
        f"/framework {filename[:-3]} do it",
        config={},
    )
    assert "Framework preflight refusal" in output


def test_exact_registered_mechanical_pairs_redirect_without_model_or_scratch():
    model_path = mock.Mock(side_effect=AssertionError("model reached"))
    scratch_create = mock.Mock(side_effect=AssertionError("scratch reached"))
    with mock.patch.object(executor, "_run_through_gear_pipeline", model_path), \
         mock.patch.object(executor.ScratchSession, "create", scratch_create):
        instance = executor.execute_framework(
            "cff", "C-Instance 2026-Q3", config={},
        )
        validate = executor.execute_framework(
            "corpus-formalization", "C-Validate corpus.md", config={},
        )
        render = executor.execute_framework(
            "off", "O-Render report", config={},
        )
    assert "/instance" in instance.final_output
    assert "/validate" in validate.final_output
    assert "/render" in render.final_output
    assert all(item.execution_id == "no-execution" for item in (instance, validate, render))
    model_path.assert_not_called()
    scratch_create.assert_not_called()
    assert ("output-formalization.md", "C-Validate") not in preflight.MECHANICAL_REDIRECTS


def test_mixed_mechanical_modes_never_enter_selector_or_fallback(
    framework_repo, monkeypatch,
):
    filename = framework_repo(
        "corpus-formalization.md",
        """# Mixed mechanical and model Framework

## MILESTONES DELIVERED

### Milestones for Mode C-Instance
#### Milestone 1: Deterministic instance
- **Endpoint produced:** An instance command.
- **Verification criterion:** The exact deterministic command is returned.
- **Gear:** 1
- **Output format:** Slash command.

### Milestones for Mode C-Design
#### Milestone 1: Model design
- **Endpoint produced:** A design.
- **Verification criterion:** The design answers the request.
- **Methods:** design
- **Required prior milestones:** None
- **External prerequisites:** None
- **Gear:** 2
- **Output format:** Markdown.

## EXECUTION METHODS

### METHOD design: Design the corpus
Produce the requested corpus design from the authoritative input.
""",
    )
    selector = mock.Mock(side_effect=AssertionError("selector model reached"))
    scratch = mock.Mock(side_effect=AssertionError("model mode reached scratch"))
    summarizer = mock.Mock(side_effect=AssertionError("elicitation model reached"))
    monkeypatch.setattr(executor, "_llm_select_mode", selector)
    monkeypatch.setattr(executor.ScratchSession, "create", scratch)
    monkeypatch.setattr(elicitation, "_ask_summarizer", summarizer)
    monkeypatch.setattr(
        executor, "_lookup_framework_default_configuration", lambda _name: None,
    )
    monkeypatch.setattr(
        executor, "_authenticated_project_visual_locks", lambda _nexus: None,
    )

    mechanical = executor.execute_framework(
        filename, "C-Instance source.md", config={},
    )
    assert "/instance" in mechanical.final_output

    with mock.patch.dict(sys.modules, {
        "boot": types.SimpleNamespace(load_routing_config=lambda: {}),
        "persona": types.SimpleNamespace(resolve_persona=lambda **_kwargs: None),
    }):
        with pytest.raises(AssertionError, match="model mode reached scratch"):
            executor.execute_framework(filename, "choose for me", config={})
        with pytest.raises(AssertionError, match="elicitation model reached"):
            elicitation.start_elicitation(
                filename, [], {}, initial_user_message="choose for me",
                conversation_id="conv-mixed",
            )

    selector.assert_not_called()


def test_model_executed_gear1_refuses_before_model_or_scratch(
    framework_repo, monkeypatch,
):
    filename = framework_repo(
        "model-gear-one.md",
        VALID_FRAMEWORK.replace("- **Gear:** 3", "- **Gear:** 1", 1),
    )
    model_path = mock.Mock(side_effect=AssertionError("model reached"))
    scratch_create = mock.Mock(side_effect=AssertionError("scratch reached"))
    monkeypatch.setattr(executor, "_run_through_gear_pipeline", model_path)
    monkeypatch.setattr(executor.ScratchSession, "create", scratch_create)

    with pytest.raises(preflight.FrameworkPreflightError, match="model-executed Gear"):
        executor.execute_framework(filename, "run", config={})

    model_path.assert_not_called()
    scratch_create.assert_not_called()


def test_mode_identity_is_first_token_or_classifier_not_substring():
    fw = preflight._parser.parse_framework_text("""# Modes
## MILESTONES DELIVERED
### Milestones for Mode Alpha
#### Milestone 1: A
- **Endpoint produced:** A.
- **Verification criterion:** A.
- **Layers covered:** 1
- **Required prior milestones:** None
- **Gear:** 4
- **Output format:** A.
### Milestones for Mode Beta
#### Milestone 1: B
- **Endpoint produced:** B.
- **Verification criterion:** B.
- **Layers covered:** 1
- **Required prior milestones:** None
- **Gear:** 4
- **Output format:** B.
## LAYER 1: Work
Do the work.
""", path="modes.md")
    with mock.patch.object(
        executor, "_llm_select_mode", return_value=("Alpha", "classified"),
    ) as classifier:
        mode, _, effective = executor.select_mode(
            fw, "Please compare the word Beta in this prose", {},
        )
    assert mode == "Alpha"
    assert effective == "Please compare the word Beta in this prose"
    classifier.assert_called_once()


@pytest.mark.parametrize(
    "mode_section, expected",
    [
        (
            """### Milestones for Mode Alpha

### Milestones for Mode Beta
#### Milestone 1: Beta result
- **Endpoint produced:** Beta result.
- **Verification criterion:** Beta succeeds.
- **Methods:** work
- **Required prior milestones:** None
- **External prerequisites:** None
- **Gear:** 2
- **Output format:** Markdown.
""",
            "have no milestones: Alpha",
        ),
        (
            """### Milestones for Mode Alpha
#### Milestone 1: Alpha result
- **Endpoint produced:** Alpha result.
- **Verification criterion:** Alpha succeeds.
- **Methods:** work
- **Required prior milestones:** None
- **External prerequisites:** None
- **Gear:** 2
- **Output format:** Markdown.

### Milestones for Mode alpha
#### Milestone 1: Duplicate result
- **Endpoint produced:** Duplicate result.
- **Verification criterion:** Duplicate succeeds.
- **Methods:** work
- **Required prior milestones:** None
- **External prerequisites:** None
- **Gear:** 2
- **Output format:** Markdown.
""",
            "unique ignoring case",
        ),
    ],
)
def test_malformed_multi_mode_refuses_before_selector_spend(
    framework_repo, monkeypatch, mode_section, expected,
):
    filename = framework_repo(
        "bad-modes.md",
        """# Bad Modes

## MILESTONES DELIVERED

""" + mode_section + """
## EXECUTION METHODS

### METHOD work: Work
Produce the exact declared result.
""",
    )
    selector = mock.Mock(side_effect=AssertionError("selector reached"))
    monkeypatch.setattr(executor, "_llm_select_mode", selector)

    with pytest.raises(preflight.FrameworkPreflightError, match=expected):
        executor.execute_framework(filename, "choose a mode", config={})

    selector.assert_not_called()


def test_allowlisted_legacy_numeric_layer_resolves_exactly(framework_repo):
    filename = framework_repo(
        "conversation-processing.md",
        """# Legacy Numeric Layer

## MILESTONES DELIVERED

### Milestone 1: Result
- **Endpoint produced:** Result.
- **Verification criterion:** Result is complete.
- **Layers covered:** 1
- **Required prior milestones:** None
- **External prerequisites:** None
- **Gear:** 2
- **Output format:** Markdown.

## LAYER 1: Exact numeric layer
Apply the exact numeric legacy layer instructions.
""",
    )
    prepared = preflight.prepare_framework_execution(filename, "run")
    methods = prepared.contract_for("all", "M1").methods
    assert [(method.id, method.legacy) for method in methods] == [("1", True)]
    assert "exact numeric legacy layer" in methods[0].body


def test_picker_analysis_and_server_launch_refuse_before_analysis_trace_or_effect(
    framework_repo, monkeypatch,
):
    filename = framework_repo(
        "invalid-picker.md",
        VALID_FRAMEWORK.replace("- **Methods:** gather", "- **Methods:** absent"),
    )
    parse_inputs = mock.Mock(side_effect=AssertionError("input analysis reached"))
    model = mock.Mock(side_effect=AssertionError("model reached"))
    monkeypatch.setattr(input_gap, "parse_framework_input_spec", parse_inputs)
    monkeypatch.setattr(input_gap, "call_model", model)
    with pytest.raises(preflight.FrameworkPreflightError):
        input_gap.analyze_framework_inputs(filename, "prompt")
    parse_inputs.assert_not_called()
    model.assert_not_called()

    import server.app as server_app

    implementation = mock.Mock(side_effect=AssertionError("server turn effect reached"))
    monkeypatch.setattr(server_app, "_pipeline_stream_impl", implementation)
    frames = list(server_app._pipeline_stream(
        "prompt", [], panel_id="conv-preflight",
        framework_selected=filename,
    ))
    assert any("Framework preflight refusal" in frame for frame in frames)
    typed_frames = list(server_app._pipeline_stream(
        f"/framework {filename[:-3]} prompt", [], panel_id="conv-preflight",
    ))
    assert any("Framework preflight refusal" in frame for frame in typed_frames)
    debug_frames = list(server_app._pipeline_stream(
        "debug the trace", [], panel_id="conv-preflight",
        extra_context={"trace_debug": {"trace_ref": "conv-preflight/turn"}},
    ))
    assert any("Framework preflight refusal" in frame for frame in debug_frames)
    implementation.assert_not_called()

    import boot

    start_trace = mock.Mock(side_effect=AssertionError("CLI trace reached"))
    monkeypatch.setattr(boot, "_framework_project_nexus", lambda: None)
    monkeypatch.setattr(boot.pipeline_trace, "start_trace", start_trace)
    cli_result = boot.run_pipeline(
        f"/framework {filename[:-3]} prompt",
        conversation_id="conv-cli-preflight",
    )
    assert "Framework preflight refusal" in cli_result
    risk_result = boot.run_pipeline(
        f"/risk high /framework {filename[:-3]} prompt",
        conversation_id="conv-cli-risk-preflight",
    )
    assert "Framework preflight refusal" in risk_result
    direct_raw = f"/direct /framework {filename[:-3]} prompt"
    direct_result = boot.run_agentic_loop(
        f"/framework {filename[:-3]} prompt",
        use_pipeline=False,
        raw_user_input=direct_raw,
    )
    assert "Framework preflight refusal" in direct_result
    start_trace.assert_not_called()

    valid = _valid(framework_repo, "cli-prepared.md")
    cli_context = {
        "contributor_bundle": {
            "sources": [{"id": "cli-source"}],
            "units": [{"source_id": "cli-source", "content": "exact"}],
        },
    }
    cli_captures = []

    def run_impl(*args, **kwargs):
        cli_captures.append((args, kwargs))
        return "captured"

    monkeypatch.setattr(boot, "_run_pipeline_impl", run_impl)
    exact_query = "first line\n```text\nkeep  spacing\n```\n"
    assert boot.run_pipeline(
        f"/framework {valid} {exact_query}",
        conversation_id="conv-cli-prepared",
        extra_context=cli_context,
    ) == "captured"
    cli_capture = cli_captures[-1][1]
    assert cli_capture["framework_prepared"].original_input == exact_query
    assert preflight.prepared_input_context(
        cli_capture["framework_prepared"],
    )["contributor_bundle"] == cli_context["contributor_bundle"]

    direct_raw = f"/direct /framework {valid} {exact_query}"
    clean_direct, use_pipeline, output_target, _style = boot.parse_user_command(
        direct_raw,
    )
    assert use_pipeline is False
    assert boot.run_agentic_loop(
        clean_direct,
        use_pipeline=use_pipeline,
        output_target=output_target,
        extra_context=cli_context,
        raw_user_input=direct_raw,
    ) == "captured"
    direct_args, direct_capture = cli_captures[-1]
    assert direct_args[0] == f"/framework {valid} {exact_query}"
    assert direct_capture["framework_prepared"].original_input == exact_query
    assert direct_capture["raw_user_input"] == direct_raw


def test_valid_picker_uses_composed_contract_and_authenticated_project(
    framework_repo, monkeypatch,
):
    filename = framework_repo(
        "picker-valid.md",
        VALID_FRAMEWORK + "\n\n## INPUT CONTRACT\nBASE CONTRACT REQUIREMENT\n",
    )
    real_loader = preflight._load_bound_text

    def load_composed(canonical_filename, project_nexus):
        text, path, profile = real_loader(canonical_filename, project_nexus)
        return text.replace(
            "BASE CONTRACT REQUIREMENT", "COMPOSED CONTRACT REQUIREMENT",
        ), path, profile

    parse_calls = []
    real_parse = input_gap.parse_framework_input_spec

    def parse_prepared(framework_id, **kwargs):
        parse_calls.append((framework_id, kwargs.get("spec_text")))
        return real_parse(framework_id, **kwargs)

    model_messages = []
    monkeypatch.setattr(preflight, "_load_bound_text", load_composed)
    monkeypatch.setattr(input_gap, "parse_framework_input_spec", parse_prepared)
    monkeypatch.setattr(
        input_gap, "get_slot_endpoint", lambda *_args, **_kwargs: {"id": "classifier"},
    )
    monkeypatch.setattr(
        input_gap,
        "call_model",
        lambda messages, _endpoint: model_messages.extend(messages) or (
            '{"requirements":[{"name":"contract","description":"ready",'
            '"why_needed":"required","required":true,"status":"provided",'
            '"evidence":"prompt"}]}'
        ),
    )

    report = input_gap.analyze_framework_inputs(
        filename, "the prompt", config={},
    )
    assert report["source"] == "llm"
    assert report["framework_id"] == "picker-valid"
    assert parse_calls[0][0] == "picker-valid"
    assert "COMPOSED CONTRACT REQUIREMENT" in parse_calls[0][1]
    assert "BASE CONTRACT REQUIREMENT" not in parse_calls[0][1]
    assert "COMPOSED CONTRACT REQUIREMENT" in model_messages[-1]["content"]

    import server.app as server_app

    captured = {}
    monkeypatch.setattr(
        server_app, "_resolve_selected_framework", lambda _value: "picker-valid",
    )
    monkeypatch.setattr(
        server_app,
        "_apply_project_model_locks",
        lambda context: dict(context, model_profile_project_nexus="project-a"),
    )
    monkeypatch.setattr(
        server_app,
        "_framework_project_nexus",
        lambda context: context.get("model_profile_project_nexus"),
    )

    def analyze_on_server(**kwargs):
        captured.update(kwargs)
        return {"requirements": [], "confidence": "high", "source": "none"}

    monkeypatch.setattr(input_gap, "analyze_framework_inputs", analyze_on_server)
    response = server_app.app.test_client().post(
        "/api/framework/analyze-inputs",
        json={"framework_id": "picker-valid", "prompt": "the prompt"},
    )
    assert response.status_code == 200
    assert captured["project_nexus"] == "project-a"
    assert captured["input_context"]["model_profile_project_nexus"] == "project-a"


def test_project_framework_composition_refuses_malformed_duplicate_or_unreadable(
    tmp_path,
):
    import framework_config
    import project_registry

    manifest = tmp_path / "ora.project.json"
    valid_entry = {
        "framework": "conforming",
        "profile_name": "default",
        "config": {},
    }
    with pytest.raises(project_registry.ManifestError, match="requires 'framework'"):
        project_registry._parse_framework_configurations(
            [valid_entry, {"profile_name": "broken"}], manifest, tmp_path,
        )
    with pytest.raises(project_registry.ManifestError, match="duplicate"):
        project_registry._parse_framework_configurations(
            [valid_entry, dict(valid_entry)], manifest, tmp_path,
        )

    (tmp_path / "one.md").write_text("one", encoding="utf-8")
    (tmp_path / "two.md").write_text("two", encoding="utf-8")
    duplicate_overlay = dict(valid_entry, overlays=[
        {"extension_point": "project_rules", "file": "one.md"},
        {"extension_point": "project_rules", "file": "two.md"},
    ])
    with pytest.raises(project_registry.ManifestError, match="duplicate overlay"):
        project_registry._parse_framework_configurations(
            [duplicate_overlay], manifest, tmp_path,
        )

    project_root = tmp_path / "project"
    project_root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    escaping = dict(valid_entry, overlays=[{
        "extension_point": "project_rules",
        "file": "../outside.md",
    }])
    with pytest.raises(project_registry.ManifestError, match="outside the project root"):
        project_registry._parse_framework_configurations(
            [escaping], manifest, project_root,
        )
    (project_root / "linked.md").symlink_to(outside)
    symlink_escape = dict(valid_entry, overlays=[{
        "extension_point": "project_rules",
        "file": "linked.md",
    }])
    with pytest.raises(project_registry.ManifestError, match="outside the project root"):
        project_registry._parse_framework_configurations(
            [symlink_escape], manifest, project_root,
        )

    overlay = types.SimpleNamespace(
        extension_point="project_rules",
        file="missing-overlay.md",
    )
    profile = types.SimpleNamespace(overlays=[overlay])
    project = types.SimpleNamespace(
        root=tmp_path,
        find_framework_configuration=lambda *_args: profile,
    )
    with pytest.raises(
        framework_config.FrameworkConfigError,
        match="overlay_unreadable",
    ):
        framework_config._load_overlay_files(
            project, "conforming", "default",
        )

    with pytest.raises(framework_config.FrameworkConfigError, match="duplicate_extension_marker"):
        framework_config.splice_extension_overlays(
            "<!-- ora-project-extension: rules -->\n"
            "<!-- ora-project-extension: rules -->",
            {"rules": "overlay"},
        )
    with pytest.raises(framework_config.FrameworkConfigError, match="unmatched_overlay"):
        framework_config.splice_extension_overlays(
            "No extension marker here.",
            {"rules": "overlay"},
        )

    configurable_spec = """# Configurable
## CONFIGURATION INTERFACE
- **`name`** (string, default: `default`) — Name.
- **`search_paths`** (list of strings, default: `[]`) — Paths.

Configured name: ${config.name}
"""

    def bound_project(config):
        entry = types.SimpleNamespace(config=config, overlays=[])
        return types.SimpleNamespace(
            nexus="project-a",
            root=tmp_path,
            find_framework_configuration=lambda *_args: entry,
        )

    with pytest.raises(framework_config.FrameworkConfigError, match="undeclared_config_key"):
        framework_config.compose_framework_spec(
            "conforming",
            project_nexus="project-a",
            profile_name="default",
            spec_text=configurable_spec,
            project=bound_project({"unknown": "value"}),
        )
    with pytest.raises(framework_config.FrameworkConfigError, match="config_type_mismatch"):
        framework_config.compose_framework_spec(
            "conforming",
            project_nexus="project-a",
            profile_name="default",
            spec_text=configurable_spec,
            project=bound_project({"search_paths": "not-a-list"}),
        )


def test_http_first_boundary_uses_project_before_pending_or_multipart_files(
    framework_repo, monkeypatch,
):
    invalid = framework_repo(
        "project-invalid.md",
        VALID_FRAMEWORK.replace("- **Gear 4 purpose:** both\n", ""),
    )
    import server.app as server_app
    import boot

    real_loader = preflight._load_bound_text
    projects = []

    def load_for_project(canonical_filename, project_nexus):
        projects.append(project_nexus)
        return real_loader(canonical_filename, None)

    pending = mock.Mock(side_effect=AssertionError("pending record reached"))
    submission = mock.Mock(side_effect=AssertionError("submission identity reached"))
    attachments = mock.Mock(side_effect=AssertionError("attachment processing reached"))
    upload = mock.Mock(side_effect=AssertionError("multipart upload reached"))
    invoke = mock.Mock(side_effect=AssertionError("pipeline/direct dispatch reached"))
    monkeypatch.setattr(preflight, "_load_bound_text", load_for_project)
    monkeypatch.setattr(
        server_app,
        "_resolve_selected_framework",
        lambda value: Path(str(value)).stem if value else "",
    )
    monkeypatch.setattr(
        server_app,
        "_apply_project_model_locks",
        lambda context: dict(context, model_profile_project_nexus="project-a"),
    )
    monkeypatch.setattr(
        server_app,
        "_framework_project_nexus",
        lambda context: context.get("model_profile_project_nexus"),
    )
    monkeypatch.setattr(
        server_app, "_conversation_lifecycle_lock",
        lambda _conversation_id: server_app.nullcontext(),
    )
    monkeypatch.setattr(server_app, "_is_conversation_deleted", lambda _id: False)
    monkeypatch.setattr(server_app, "_is_conversation_closed", lambda _id: False)
    monkeypatch.setattr(server_app, "_assert_no_casefold_session_collision", lambda _id: None)
    monkeypatch.setattr(server_app, "_effective_conversation_tag", lambda _id, tag: tag)
    monkeypatch.setattr(
        server_app,
        "_authoritative_dialogue_history",
        lambda _id, _history: ([], {
            "source": "test", "envelope_exists": False,
            "local_message_count": 0, "local_turn_count": 0,
            "first_user_input": "",
        }),
    )
    monkeypatch.setattr(
        server_app, "build_contributor_bundle", lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(server_app, "_log_pending_submission", pending)
    monkeypatch.setattr(server_app, "_new_submission_id", submission)
    monkeypatch.setattr(server_app, "_process_attachments", attachments)
    monkeypatch.setattr(server_app, "_save_multipart_image", upload)
    monkeypatch.setattr(server_app, "_invoke_pipeline", invoke)
    monkeypatch.setattr(boot, "_is_known_style_id", lambda value: value == "known")

    client = server_app.app.test_client()
    chat_response = client.post(
        "/chat",
        json={
            "message": "run",
            "conversation_id": "conv-project-refusal",
            "framework_selected": invalid[:-3],
        },
    )
    multipart_response = client.post(
        "/chat/multipart",
        data={
            "message": "run",
            "conversation_id": "conv-project-refusal",
            "framework_selected": invalid[:-3],
        },
    )

    wrapped_responses = []
    wrapped_commands = [
        f"/risk high /framework {invalid[:-3]} run",
        f"/risk high /direct /framework {invalid[:-3]} run",
        f"/risk high /save result.md /framework {invalid[:-3]} run",
        f"/risk high /style known /framework {invalid[:-3]} run",
        f"/direct /framework {invalid[:-3]} run",
        f"/save result.md /framework {invalid[:-3]} run",
        f"/saveboth result.md /framework {invalid[:-3]} run",
        f"/style known /framework {invalid[:-3]} run",
    ]
    for index, command in enumerate(wrapped_commands):
        conversation_id = f"conv-wrapper-refusal-{index}"
        wrapped_responses.append(client.post(
            "/chat",
            json={"message": command, "conversation_id": conversation_id},
        ))
        wrapped_responses.append(client.post(
            "/chat/multipart",
            data={
                "message": command,
                "conversation_id": conversation_id,
                "image": (io.BytesIO(b"must not persist"), "blocked.png"),
            },
            content_type="multipart/form-data",
        ))

    assert chat_response.status_code == 409
    assert multipart_response.status_code == 409
    assert all(response.status_code == 409 for response in wrapped_responses)
    assert projects == ["project-a"] * (2 + len(wrapped_responses))
    pending.assert_not_called()
    submission.assert_not_called()
    attachments.assert_not_called()
    upload.assert_not_called()
    invoke.assert_not_called()


def test_multipart_reuses_admitted_snapshot_and_rolls_back_late_refusal(
    framework_repo, monkeypatch, tmp_path,
):
    filename = _valid(framework_repo, "changing-project-framework.md")
    import server.app as server_app

    real_loader = preflight._load_bound_text
    load_count = 0
    projects = []
    active_project_reads = 0

    def load_changing_contract(canonical_filename, project_nexus):
        nonlocal load_count
        load_count += 1
        projects.append(project_nexus)
        text, path, profile = real_loader(canonical_filename, None)
        if load_count == 1:
            return text, path, profile
        return text.replace("- **Gear 4 purpose:** both\n", ""), path, profile

    def active_project_context():
        nonlocal active_project_reads
        active_project_reads += 1
        if active_project_reads > 1:
            return "project-b", None
        return "project-a", None

    monkeypatch.setattr(preflight, "_load_bound_text", load_changing_contract)
    monkeypatch.setattr(
        server_app,
        "_resolve_selected_framework",
        lambda value: Path(str(value)).stem if value else "",
    )
    monkeypatch.setattr(
        server_app, "_active_project_model_context", active_project_context,
    )
    monkeypatch.setattr(
        server_app, "_conversation_lifecycle_lock",
        lambda _conversation_id: server_app.nullcontext(),
    )
    monkeypatch.setattr(server_app, "_is_conversation_deleted", lambda _id: False)
    monkeypatch.setattr(server_app, "_is_conversation_closed", lambda _id: False)
    monkeypatch.setattr(server_app, "_assert_no_casefold_session_collision", lambda _id: None)
    monkeypatch.setattr(server_app, "_effective_conversation_tag", lambda _id, tag: tag)
    monkeypatch.setattr(
        server_app,
        "_authoritative_dialogue_history",
        lambda _id, _history: ([], {
            "source": "test", "envelope_exists": False,
            "local_message_count": 0, "local_turn_count": 0,
            "first_user_input": "",
        }),
    )
    monkeypatch.setattr(
        server_app, "build_contributor_bundle", lambda *_args, **_kwargs: {},
    )
    pending_root = tmp_path / "pending"
    monkeypatch.setattr(server_app, "CONVERSATIONS_PENDING", str(pending_root))
    real_log_pending = server_app._log_pending_submission
    pending_payloads = []

    def log_pending(payload, **kwargs):
        pending_payloads.append(dict(payload))
        return real_log_pending(payload, **kwargs)

    monkeypatch.setattr(server_app, "_log_pending_submission", log_pending)
    upload_path = tmp_path / "uploaded.png"

    def save_upload(_conversation_id, _storage):
        upload_path.write_bytes(b"test image")
        return str(upload_path)

    monkeypatch.setattr(server_app, "_save_multipart_image", save_upload)
    captured = {}

    def refuse_after_admission(*args, **kwargs):
        captured["args"] = args
        captured.update(kwargs)
        return (
            '{"error":"Framework preflight refusal: downstream defense"}',
            409,
            {"X-Ora-Outcome": "framework_preflight_refusal"},
        )

    monkeypatch.setattr(server_app, "_invoke_pipeline", refuse_after_admission)

    exact_query = "run\n| left |  right |\n"
    raw_command = (
        f"/saveboth result.md /framework {filename[:-3]} {exact_query}"
    )
    response = server_app.app.test_client().post(
        "/chat/multipart",
        data={
            "message": raw_command,
            "conversation_id": "conv-changing-framework",
            "image": (io.BytesIO(b"test image"), "uploaded.png"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 409
    assert load_count == 1
    assert projects == ["project-a"]
    assert active_project_reads == 1
    assert captured["framework_prepared"].project_nexus == "project-a"
    assert "Gear 4 purpose" in captured["framework_prepared"].contract_text
    assert captured["framework_prepared"].original_input == exact_query
    assert captured["args"][0] == raw_command
    assert pending_payloads[0]["user_input"] == raw_command
    assert not upload_path.exists()
    assert list(pending_root.glob("*.json")) == []

    # The same words in an ordinary successful report are content, not a
    # rollback signal. Only the typed outcome header controls cleanup.
    monkeypatch.setattr(
        preflight,
        "_load_bound_text",
        lambda canonical_filename, _project_nexus: real_loader(
            canonical_filename, None,
        ),
    )
    monkeypatch.setattr(
        server_app,
        "_invoke_pipeline",
        lambda *_args, **_kwargs: (
            '{"status":"ok","report":"Framework preflight refusal: quoted phrase"}'
        ),
    )
    monkeypatch.setattr(
        server_app, "_new_submission_id", lambda: "legitimate-submission",
    )
    monkeypatch.setattr(
        server_app,
        "_log_pending_submission",
        lambda _payload, submission_id=None: (
            submission_id or "legitimate-submission"
        ),
    )
    legitimate = server_app.app.test_client().post(
        "/chat/multipart",
        data={
            "message": raw_command,
            "conversation_id": "conv-legitimate-phrase",
            "image": (io.BytesIO(b"test image"), "uploaded.png"),
        },
        content_type="multipart/form-data",
    )
    assert legitimate.status_code == 200
    assert upload_path.exists()
    prose_frame = json.loads(
        server_app._framework_terminal_sse(
            "Framework preflight refusal: quoted phrase", "completed",
        )[6:]
    )
    refusal_frame = json.loads(
        server_app._framework_terminal_sse("refused", "refused")[6:]
    )
    assert prose_frame["type"] == "response"
    assert refusal_frame["type"] == "framework_preflight_refusal"


def test_server_direct_wrapper_routes_admitted_framework_through_pipeline(
    framework_repo, monkeypatch,
):
    filename = _valid(framework_repo, "server-direct-wrapper.md")
    command = f"/framework {filename[:-3]} preserve  these bytes"
    prepared = preflight.preflight_framework_command(command)
    import server.app as server_app

    captured = {}

    def pipeline_stream(user_input, history, **kwargs):
        captured["user_input"] = user_input
        captured["history"] = history
        captured.update(kwargs)
        yield "pipeline-frame"

    direct_stream = mock.Mock(
        side_effect=AssertionError("direct model dispatch reached"),
    )
    monkeypatch.setattr(server_app, "_pipeline_stream", pipeline_stream)
    monkeypatch.setattr(
        server_app, "_traced_direct_entry_stream", direct_stream,
    )

    frames = list(server_app.agentic_loop_stream(
        command,
        [],
        use_pipeline=False,
        panel_id="conv-server-direct-wrapper",
        framework_prepared=prepared,
    ))

    assert frames == ["pipeline-frame"]
    assert captured["user_input"] == command
    assert captured["framework_prepared"] is prepared
    direct_stream.assert_not_called()


def test_http_first_boundary_accepts_project_bound_continuation(
    framework_repo, monkeypatch,
):
    filename = _valid(framework_repo, "project-continuation.md")
    import server.app as server_app

    marker = elicitation.elicitation_marker(
        filename,
        "all",
        project_nexus="project-a",
        conversation_id="conv-project-continuation",
        execution_context={"framework_start": 0},
    )
    history = [{
        "role": "assistant",
        "content": "What next?\n\n" + marker,
    }]
    real_loader = preflight._load_bound_text
    projects = []

    def load_for_project(canonical_filename, project_nexus):
        projects.append(project_nexus)
        return real_loader(canonical_filename, None)

    captured = {}
    monkeypatch.setattr(preflight, "_load_bound_text", load_for_project)
    monkeypatch.setattr(server_app, "_resolve_selected_framework", lambda value: "")
    monkeypatch.setattr(
        server_app,
        "_apply_project_model_locks",
        lambda context: dict(context, model_profile_project_nexus="project-a"),
    )
    monkeypatch.setattr(
        server_app,
        "_framework_project_nexus",
        lambda context: context.get("model_profile_project_nexus"),
    )
    monkeypatch.setattr(
        server_app, "_conversation_lifecycle_lock",
        lambda _conversation_id: server_app.nullcontext(),
    )
    monkeypatch.setattr(server_app, "_is_conversation_deleted", lambda _id: False)
    monkeypatch.setattr(server_app, "_is_conversation_closed", lambda _id: False)
    monkeypatch.setattr(server_app, "_assert_no_casefold_session_collision", lambda _id: None)
    monkeypatch.setattr(server_app, "_effective_conversation_tag", lambda _id, tag: tag)
    monkeypatch.setattr(
        server_app,
        "_authoritative_dialogue_history",
        lambda _id, _history: (history, {
            "source": "test", "envelope_exists": True,
            "local_message_count": 1, "local_turn_count": 0,
            "first_user_input": "",
        }),
    )
    contributor_bundle = {
        "sources": [{"id": "explicit-a"}, {"id": "explicit-b"}],
        "units": [
            {"source_id": "explicit-a", "content": "alpha"},
            {"source_id": "explicit-b", "content": "beta"},
        ],
    }
    monkeypatch.setattr(
        server_app,
        "build_contributor_bundle",
        lambda *_args, **_kwargs: contributor_bundle,
    )
    monkeypatch.setattr(server_app, "_log_pending_submission", lambda *_args, **_kwargs: "submission")
    monkeypatch.setattr(server_app, "_process_attachments", lambda _items: ([], None))

    def invoke(*args, **kwargs):
        captured["args"] = args
        captured.update(kwargs)
        return '{"status":"ok"}'

    monkeypatch.setattr(server_app, "_invoke_pipeline", invoke)
    response = server_app.app.test_client().post(
        "/chat",
        json={
            "message": "continue\n```text\nkeep  spacing\n```\n| a |  b |\n",
            "conversation_id": "conv-project-continuation",
        },
    )

    assert response.status_code == 200
    assert projects == ["project-a"]
    assert captured["extra_context"]["model_profile_project_nexus"] == "project-a"
    assert captured["framework_prepared"].original_input == captured["args"][0]
    assert preflight.prepared_input_context(
        captured["framework_prepared"],
    )["contributor_bundle"] == contributor_bundle


def test_picker_analysis_preserves_mechanical_redirect_without_classifier(monkeypatch):
    parse_inputs = mock.Mock(side_effect=AssertionError("input spec reached"))
    model = mock.Mock(side_effect=AssertionError("model reached"))
    monkeypatch.setattr(input_gap, "parse_framework_input_spec", parse_inputs)
    monkeypatch.setattr(input_gap, "call_model", model)
    report = input_gap.analyze_framework_inputs(
        "cff", "C-Validate corpus.md", config={},
    )
    assert report["source"] == "mechanical"
    assert report["mechanical_redirect"].startswith("/validate")
    parse_inputs.assert_not_called()
    model.assert_not_called()


class _Ledger:
    def __init__(self):
        self.claims = []

    def claim(self, **kwargs):
        self.claims.append(kwargs)
        return ({"status": "claimed"}, True)


def test_trigger_framework_refuses_before_claim_trace_or_action(framework_repo, monkeypatch):
    filename = framework_repo(
        "invalid-trigger.md",
        VALID_FRAMEWORK.replace("- **Gear:** 3", "- **Gear:** sometimes 3"),
    )
    action = {"kind": "framework", "framework": filename, "input": "run"}
    spec = {
        "trigger_id": "invalid-framework-trigger",
        "action": action,
    }
    record = {"status": "active", "spec": spec}
    ledger = _Ledger()
    service = triggers.TriggerService(
        ledger=ledger,
        executor=lambda work: work(),
    )
    monkeypatch.setattr(service, "_require", lambda _trigger_id: record)
    with pytest.raises(triggers.TriggerConflict, match="preflight"):
        service._fire(record, "manual", {})
    assert ledger.claims == []

    start_trace = mock.Mock(side_effect=AssertionError("trace reached"))
    import pipeline_trace
    monkeypatch.setattr(pipeline_trace, "start_trace", start_trace)
    with pytest.raises(triggers.TriggerConflict, match="preflight"):
        triggers._execute_action(
            action,
            {"framework": filename, "trigger_id": "invalid-framework-trigger"},
        )
    start_trace.assert_not_called()

    valid = _valid(framework_repo, "trigger-composed.md")
    real_loader = preflight._load_bound_text
    overlay = {"version": "approved"}

    def load_composed(canonical_filename, project_nexus):
        text, path, profile = real_loader(canonical_filename, project_nexus)
        return (
            text
            + "\n\n```markdown\n"
            + f"ignored composed example: {overlay['version']}\n"
            + "```\n",
            path,
            profile,
        )

    monkeypatch.setattr(preflight, "_load_bound_text", load_composed)
    valid_action = {
        "kind": "framework",
        "framework": valid,
        "input": "run\n```text\nkeep  spacing\n```\n| a |  b |\n",
    }
    original_trigger_input = valid_action["input"]
    valid_action = triggers._validate_action(valid_action)
    assert valid_action["input"] == original_trigger_input
    approved_binding, trigger_prepared = (
        triggers._resolve_framework_action_binding(valid_action)
    )
    assert trigger_prepared.original_input == valid_action["input"]
    overlay["version"] = "changed"
    changed_binding = triggers.resolve_action_binding(valid_action)
    assert approved_binding["command_digest"] != changed_binding["command_digest"]

    valid_spec = {
        "trigger_id": "composed-framework-trigger",
        "action": valid_action,
    }
    active = {
        "status": "active",
        "spec": valid_spec,
        "approved_spec_digest": triggers._digest(valid_spec),
        "approved_action_binding": approved_binding,
    }
    monkeypatch.setattr(service, "_require", lambda _trigger_id: active)
    with pytest.raises(triggers.TriggerConflict, match="action_definition_drifted"):
        service._fire(active, "manual", {})
    assert ledger.claims == []


def test_signed_continuation_is_conversation_bound_and_forgery_cannot_call_model(
    framework_repo, monkeypatch, tmp_path,
):
    import tool_events

    existing_key = tmp_path / "existing-auth" / "approval.auth.key"
    monkeypatch.setattr(
        tool_events, "_approval_key_path", lambda: str(existing_key),
    )
    filename = _valid(framework_repo, "elicitation.md")
    marker = elicitation.elicitation_marker(
        filename,
        "all",
        conversation_id="conv-auth",
    )
    history = [
        {"role": "user", "content": "My exact first answer."},
        {"role": "assistant", "content": "Next question?\n\n" + marker},
    ]
    # Simulate a fresh worker/restarted process with no process-local legacy
    # key. Authentication must come from Ora's existing durable server key.
    monkeypatch.delattr(
        builtins, "_ora_framework_elicitation_hmac_key", raising=False,
    )
    ctx = elicitation.is_continuation(history)
    assert ctx is not None and ctx.authenticated
    assert ctx.conversation_id == "conv-auth"

    import risk_gate
    gate_prompt = risk_gate.build_task_gate_prompt(
        "irreversible",
        "fingerprint",
        "queue-id",
        resume={
            "fw": filename,
            "mode": "all",
            "conversation_id": "conv-auth",
            "project_nexus": None,
            "one_run_profile": None,
            "execution_context": None,
        },
    )
    reattached = elicitation.is_continuation([
        {"role": "assistant", "content": gate_prompt},
    ])
    assert reattached is not None and reattached.authenticated
    assert reattached.conversation_id == "conv-auth"

    forged = marker.replace("/all/", "/forged/", 1)
    forged_ctx = elicitation.is_continuation([
        {"role": "assistant", "content": forged},
    ])
    assert forged_ctx is not None
    assert "authentication failed" in (forged_ctx.context_error or "")

    unsigned_ctx = elicitation.is_continuation([
        {"role": "assistant", "content": "<!-- ora-framework: elicitation/all/eliciting -->"},
    ])
    assert unsigned_ctx is not None
    assert "not authenticated" in (unsigned_ctx.context_error or "")

    missing_key = tmp_path / "must-not-be-created" / "approval.auth.key"
    monkeypatch.setattr(
        tool_events, "_approval_key_path", lambda: str(missing_key),
    )
    unavailable_ctx = elicitation.is_continuation([
        {"role": "assistant", "content": marker},
    ])
    assert unavailable_ctx is not None
    assert "authentication is unavailable" in (
        unavailable_ctx.context_error or ""
    )
    assert not missing_key.parent.exists()
    monkeypatch.setattr(
        tool_events, "_approval_key_path", lambda: str(existing_key),
    )

    summarizer = mock.Mock(side_effect=AssertionError("summarizer reached"))
    monkeypatch.setattr(elicitation, "_ask_summarizer", summarizer)
    rejected = elicitation.continue_elicitation(
        forged_ctx, history, {}, latest_user_text="continue",
        conversation_id="conv-auth", current_project_nexus=None,
    )
    assert "continuation rejected" in rejected.lower()
    mismatched = elicitation.continue_elicitation(
        ctx, history, {}, latest_user_text="continue",
        conversation_id="another-conversation", current_project_nexus=None,
    )
    assert "different conversation" in mismatched
    summarizer.assert_not_called()


def test_elicitation_start_and_continuation_preflight_before_summarizer(
    framework_repo, monkeypatch,
):
    invalid = framework_repo(
        "bad-elicit.md",
        VALID_FRAMEWORK.replace("- **Gear 4 purpose:** both\n", ""),
    )
    summarizer = mock.Mock(side_effect=AssertionError("summarizer reached"))
    monkeypatch.setattr(elicitation, "_ask_summarizer", summarizer)
    refused = elicitation.start_elicitation(
        invalid, [], {}, conversation_id="conv-elicit",
    )
    assert "preflight refusal" in refused.lower()
    summarizer.assert_not_called()

    valid = _valid(framework_repo, "good-elicit.md")
    summary = elicitation._SummaryState(
        elicited_bullets=["model summary"],
        pending_bullets=["one more"],
        action="ASK_NEXT",
        next_question="What is the exact constraint?",
    )
    summarizer_histories = []

    def summarize(*args, **_kwargs):
        summarizer_histories.append(list(args[3]))
        return summary

    monkeypatch.setattr(elicitation, "_ask_summarizer", summarize)
    prior_private_history = [{
        "role": "user",
        "content": "PRIVATE PRE-FRAMEWORK MATERIAL MUST NOT ENTER ELICITATION",
    }]
    started = elicitation.start_elicitation(
        valid, prior_private_history, {}, conversation_id="conv-elicit",
        input_context={
            "conversation_id": "conv-elicit",
            "contributor_bundle": {
                "sources": [{"id": "one"}, {"id": "two"}],
                "units": [{"source_id": "one"}, {"source_id": "two"}],
            },
        },
    )
    ctx = elicitation.is_continuation([
        {"role": "assistant", "content": started},
    ])
    assert ctx is not None and ctx.authenticated
    assert "contributor_bundle" not in str(ctx.execution_context)
    assert ctx.execution_context["framework_start"] == len(prior_private_history)
    assert summarizer_histories == [[]]

    captured = {}
    monkeypatch.setattr(
        elicitation,
        "_run_elicitation_turn",
        lambda *args, **kwargs: captured.update(kwargs) or "continued",
    )
    result = elicitation.continue_elicitation(
        ctx,
        [{"role": "assistant", "content": started}],
        {},
        latest_user_text="My next exact answer.",
        conversation_id="conv-elicit",
        current_project_nexus=None,
        input_context={
            "contributor_bundle": {
                "sources": [{"id": "one"}, {"id": "two"}],
                "units": [{"source_id": "one"}, {"source_id": "two"}],
            },
        },
    )
    assert result == "continued"
    assert [source["id"] for source in captured["input_context"]["contributor_bundle"]["sources"]] == [
        "one", "two",
    ]


def test_final_elicitation_uses_raw_user_messages_and_all_contributors(
    framework_repo, monkeypatch,
):
    filename = _valid(framework_repo, "deliverable.md")
    prepared = preflight.prepare_framework_execution(filename, "raw")
    fw = prepared.framework
    milestone = fw.all_milestones()[0]
    summary = elicitation._SummaryState(
        elicited_bullets=["MODEL-AUTHORED SUBSTITUTE BULLET"],
        pending_bullets=[],
        action="PRODUCE_DELIVERABLE",
        next_question="",
    )
    captured = {}
    fake_result = types.SimpleNamespace(success=True, final_output="done")

    def execute_framework(framework_name, user_input, **kwargs):
        captured["framework_name"] = framework_name
        captured["user_input"] = user_input
        captured["kwargs"] = kwargs
        return fake_result

    monkeypatch.setattr(executor, "execute_framework", execute_framework)
    monkeypatch.setattr(executor, "format_execution_result", lambda _result: "formatted")
    monkeypatch.setattr("risk_gate.assign_tier", lambda *_args, **_kwargs: {"risk_tier": "low-risk"})
    monkeypatch.setattr("risk_gate.evaluate_hold", lambda *_args, **_kwargs: (None, None))
    monkeypatch.setattr("risk_gate.now_ts", lambda: "now")
    monkeypatch.setattr("risk_gate.record_route_observed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("tool_events.set_turn_context", lambda **_kwargs: None)

    contributor_bundle = {
        "sources": [{"id": "source-a"}, {"id": "source-b"}],
        "units": [
            {"source_id": "source-a", "content": "alpha"},
            {"source_id": "source-b", "content": "beta"},
        ],
    }
    output = elicitation._produce_deliverable(
        fw,
        "all",
        milestone,
        summary,
        [{"role": "user", "content": "Keep THIS exact first message."}],
        "And this exact second message.",
        {},
        prepared=prepared,
        conversation_id="conv-deliverable",
        input_context={"contributor_bundle": contributor_bundle},
    )
    assert output == "formatted"
    assert "Keep THIS exact first message." in captured["user_input"]
    assert "And this exact second message." in captured["user_input"]
    assert "MODEL-AUTHORED SUBSTITUTE BULLET" not in captured["user_input"]
    assert captured["kwargs"]["input_context"]["contributor_bundle"] == contributor_bundle

    isolated = {}
    monkeypatch.setattr(
        elicitation,
        "_ask_summarizer",
        lambda *_args, **_kwargs: summary,
    )
    monkeypatch.setattr(
        elicitation,
        "_produce_deliverable",
        lambda _fw, _mode, _milestone, _summary, segment, latest, *_args, **_kwargs:
            isolated.update(segment=list(segment), latest=latest) or "isolated",
    )
    result = elicitation._run_elicitation_turn(
        fw,
        "all",
        milestone,
        [
            {"role": "user", "content": "PRIVATE BEFORE FRAMEWORK"},
            {"role": "assistant", "content": "Framework question"},
            {"role": "user", "content": "Framework answer one"},
        ],
        {},
        latest_user_text="Framework answer two",
        prepared=prepared,
        framework_start=1,
    )
    assert result == "isolated"
    assert [item["content"] for item in isolated["segment"]] == [
        "Framework question", "Framework answer one",
    ]
    assert isolated["latest"] == "Framework answer two"


def test_unregistered_direct_path_is_never_treated_as_framework_identity(framework_repo):
    _valid(framework_repo)
    with pytest.raises(preflight.FrameworkPreflightError, match="not registered"):
        preflight.prepare_framework_execution("/tmp/attacker-supplied.md", "run")
