"""Focused behavioral proof for the Process Formalization v3 foundation.

The tests use the real paired canonicals and strict preflight. Model-profile
resolution is deterministic and any mode-classifier/provider path is forbidden.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from types import MappingProxyType

import pytest


HERE = Path(__file__).resolve().parent
ORCH = HERE.parent
if str(ORCH) not in sys.path:
    sys.path.insert(0, str(ORCH))

import framework_preflight as preflight  # noqa: E402
import milestone_executor as executor  # noqa: E402


ORA_ROOT = Path(os.environ["ORA_HOME"])
VAULT_ROOT = Path(os.environ["ORA_VAULT"])
PFF_VAULT = VAULT_ROOT / "Projects" / "Ora" / "Framework — Process Formalization.md"
PFF_ORA = ORA_ROOT / "frameworks" / "book" / "process-formalization.md"
REGISTRY_VAULT = VAULT_ROOT / "Projects" / "Ora" / "Registry — Framework Registry.md"
REGISTRY_ORA = ORA_ROOT / "frameworks" / "framework-registry.md"

EXPECTED_METHODS = {
    "F-Design": (
        ("M1", ("design_basis",), (), 4, "both"),
        ("M2", ("design_canonical",), ("M1",), 4, "both"),
    ),
    "F-Convert": (
        ("M1", ("convert_map",), (), 4, "both"),
        ("M2", ("convert_canonical",), ("M1",), 4, "both"),
    ),
    "F-Render": (
        ("M1", ("render_derive",), (), 3, None),
    ),
    "F-Audit": (
        ("M1", ("audit_contract",), (), 4, "independent corroboration"),
    ),
}


def _vault_body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    boundary = text.find("\n---\n", 4)
    assert boundary >= 0
    body = text[boundary + len("\n---\n"):]
    if body.startswith("\n"):
        body = body[1:]
    return body


def _deterministic_profile(**_kwargs):
    selected = MappingProxyType({
        "source": "global",
        "name": "pff-foundation-test",
        "runtime_name": "pff-foundation-test",
    })
    return MappingProxyType({
        "selected": selected,
        "chain": (selected,),
    })


@pytest.fixture
def prepared_modes(monkeypatch):
    provider_calls = []

    def forbidden_provider_call(*_args, **_kwargs):
        provider_calls.append(True)
        raise AssertionError("strict PFF preflight must not call a provider")

    monkeypatch.setattr(
        preflight,
        "_resolve_effective_model_profile",
        _deterministic_profile,
    )
    monkeypatch.setattr(
        executor,
        "_llm_select_mode",
        forbidden_provider_call,
    )

    prepared = {
        mode: preflight.prepare_framework_execution(
            "process-formalization.md",
            f"{mode} Preserve THIS authoritative request.",
        )
        for mode in EXPECTED_METHODS
    }
    assert provider_calls == []
    return prepared


def test_pff_and_registry_pairs_have_exact_normalized_body_parity():
    assert _vault_body(PFF_VAULT) == PFF_ORA.read_text(encoding="utf-8")
    assert _vault_body(REGISTRY_VAULT) == REGISTRY_ORA.read_text(encoding="utf-8")


def test_all_four_modes_pass_strict_preflight_without_provider_calls(
    prepared_modes,
):
    assert set(prepared_modes) == set(EXPECTED_METHODS)

    for mode, prepared in prepared_modes.items():
        assert prepared.canonical_filename == "process-formalization.md"
        assert prepared.exact_mode == mode
        assert prepared.effective_input == "Preserve THIS authoritative request."
        assert prepared.mechanical_redirect is None

        contracts = prepared.framework.milestones_by_mode[mode]
        expected = EXPECTED_METHODS[mode]
        assert len(contracts) == len(expected)

        for contract, (
            milestone_id,
            method_ids,
            prior_ids,
            gear,
            gear4_purpose,
        ) in zip(contracts, expected, strict=True):
            assert contract.milestone_id == milestone_id
            assert tuple(method.id for method in contract.methods) == method_ids
            assert contract.required_prior == prior_ids
            assert contract.external_prerequisites == ()
            assert contract.verification_criterion
            assert contract.gear == gear
            assert contract.gear4_purpose == gear4_purpose
            assert contract.output_format
            assert contract.drift_check_question
            assert all(method.legacy is False for method in contract.methods)


def test_workload_coherent_shape_and_strict_declarations_are_complete(
    prepared_modes,
):
    design = prepared_modes["F-Design"].framework.milestones_by_mode["F-Design"]
    convert = prepared_modes["F-Convert"].framework.milestones_by_mode["F-Convert"]
    render = prepared_modes["F-Render"].framework.milestones_by_mode["F-Render"]
    audit = prepared_modes["F-Audit"].framework.milestones_by_mode["F-Audit"]

    assert [item.milestone_id for item in design] == ["M1", "M2"]
    assert [item.milestone_id for item in convert] == ["M1", "M2"]
    assert [item.milestone_id for item in render] == ["M1"]
    assert [item.milestone_id for item in audit] == ["M1"]

    assert re.search(r"working[- ]load", design[0].endpoint_produced.casefold())
    assert "canonical" in design[1].endpoint_produced.casefold()
    assert "conversion basis" in convert[0].endpoint_produced.casefold()
    assert "converted" in convert[1].endpoint_produced.casefold()
    assert "deterministic" in render[0].endpoint_produced.casefold()
    assert "non-mutating" in audit[0].endpoint_produced.casefold()

    all_contracts = list(prepared_modes["F-Design"].contracts.values())
    used_method_ids = [
        method.id
        for contract in all_contracts
        for method in contract.methods
    ]
    assert sorted(used_method_ids) == sorted({
        "design_basis",
        "design_canonical",
        "convert_map",
        "convert_canonical",
        "render_derive",
        "audit_contract",
    })
    assert len(used_method_ids) == len(set(used_method_ids))


def test_pff_has_left_legacy_allow_list_and_cannot_downgrade():
    assert "process-formalization.md" not in preflight.LEGACY_LAYER_FRAMEWORKS

    canonical = PFF_ORA.read_text(encoding="utf-8")
    assert re.search(r"^### METHOD design_basis:", canonical, re.MULTILINE)
    assert re.search(r"^## LAYER ", canonical, re.MULTILINE) is None

    downgraded = re.sub(
        r"^### METHOD ([A-Za-z0-9_.-]+):",
        r"## LAYER \1:",
        canonical,
        flags=re.MULTILINE,
    ).replace("- **Methods:**", "- **Layers covered:**")
    executable, _fenced = preflight._mask_fences(downgraded)

    with pytest.raises(
        preflight.FrameworkPreflightError,
        match="legacy LAYER declarations are not allowed",
    ):
        preflight._extract_declarations(
            executable,
            "process-formalization.md",
        )


class _PriorScratch:
    def __init__(self, values=None):
        self.values = values or {}

    def read_all_prior(self, identities):
        return {
            identity: self.values[identity]
            for identity in identities
            if identity in self.values
        }


def _packet(prepared, mode, milestone_id, values=None):
    contract = prepared.contract_for(mode, milestone_id)
    return executor._build_handoff_packet(
        prepared.framework,
        contract,
        contract,
        _PriorScratch(values),
        "Preserve THIS authoritative request.",
    )


def test_runtime_consumes_truthful_authoring_and_admission_seams(
    prepared_modes,
):
    design_packet = _packet(
        prepared_modes["F-Design"],
        "F-Design",
        "M2",
        {"M1": "Resolved design basis with contributor source A."},
    )
    assert "Preserve THIS authoritative request." in design_packet
    assert "Resolved design basis with contributor source A." in design_packet
    assert "one authored dual-use canonical" in design_packet
    assert "exact body-identical Vault/Ora mirrors" in design_packet
    assert "deterministic derived Skill/runtime views only" in design_packet
    assert "private and inactive until implementation, behavioral proof" in design_packet
    assert "Never assign ADMITTED_ACTIVE" in design_packet
    assert "bounded Programming handoff" in design_packet
    assert "runner.py counterfactual" in design_packet
    assert "complete per-milestone override" in design_packet
    assert (
        "required unavailable lanes refuse or yield incomplete"
        in design_packet.casefold()
    )

    render_packet = _packet(
        prepared_modes["F-Render"],
        "F-Render",
        "M1",
    )
    assert "implemented registered deterministic transformer or exporter" in render_packet
    assert "never substitutes its own rewrite" in render_packet
    assert "return INCOMPLETE" in render_packet
    assert "Do not register, install, activate, publish, or trust" in render_packet

    audit_packet = _packet(
        prepared_modes["F-Audit"],
        "F-Audit",
        "M1",
    )
    assert "read-only review" in audit_packet
    assert "does not modify or activate anything" in audit_packet
    assert "Every applicable check has PASS, FLAG, FAIL, or NOT APPLICABLE" in audit_packet


def test_mode_context_overrides_and_incomplete_handoffs_are_explicit(
    prepared_modes,
):
    canonical = prepared_modes["F-Design"].contract_text
    context_section = canonical.split("## Context-Lane Contract", 1)[1].split(
        "## Capability, Code, and Health Contract", 1,
    )[0]

    default_declarations = re.findall(
        r"^(F-(?:Design|Convert|Render|Audit)) default lanes are (.+)$",
        context_section,
        re.MULTILINE,
    )
    assert sorted(mode for mode, _declaration in default_declarations) == sorted(
        EXPECTED_METHODS,
    )
    defaults = dict(default_declarations)
    assert "admitted source canonical required from the caller or an implemented owned lookup" in defaults["F-Render"]
    assert "conversation-context, vault-semantic, and web-external unavailable unless" in defaults["F-Render"]
    assert "complete framework and supplied evidence required from the caller" in defaults["F-Audit"]

    override_declarations = re.findall(
        r"^(F-(?:Design|Convert|Render|Audit)) (M\d+) completely overrides "
        r"(?:the|its mode) default with (.+)$",
        context_section,
        re.MULTILINE,
    )
    expected_overrides = sorted(
        (mode, milestone[0])
        for mode, milestones in EXPECTED_METHODS.items()
        for milestone in milestones
    )
    assert sorted(
        (mode, milestone_id)
        for mode, milestone_id, _declaration in override_declarations
    ) == expected_overrides
    context_lanes = (
        "authoritative-user-input",
        "explicit-contributors",
        "conversation-context",
        "vault-semantic",
        "project-status-files",
        "web-external",
        "deterministic-capability-results",
        "same-run-prior-deliverables",
    )
    for _mode, _milestone_id, declaration in override_declarations:
        assert all(lane in declaration for lane in context_lanes)

    assert "A required lane that the current caller cannot supply yields REFUSED or INCOMPLETE" in canonical
    assert "An optional unavailable lane yields a visible limitation and continues" in canonical
    assert "Tool and capability permission is declared separately" in canonical
    assert "PFF may report the first three states. PFF alone never grants ADMITTED_ACTIVE." in canonical
