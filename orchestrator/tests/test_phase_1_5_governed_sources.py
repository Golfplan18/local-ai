"""Phase 1.5 topology, directive, and generating-source regressions."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ORCH = Path(__file__).resolve().parents[1]
ROOT = ORCH.parent
if str(ORCH) not in sys.path:
    sys.path.insert(0, str(ORCH))

import oversight_actions as actions  # noqa: E402
import oversight_queue as queue  # noqa: E402
import oversight_router as router  # noqa: E402
import governed_process_runtime as gpr  # noqa: E402
import process_capability_discovery as discovery  # noqa: E402
from oversight_context import OversightContextBundle  # noqa: E402
from tests import test_governed_process_runtime as runtime_fixtures  # noqa: E402


VAULT = Path(
    os.environ.get("ORA_VAULT_PATH")
    or os.environ.get("ORA_VAULT")
    or (Path.home() / "Documents" / "vault")
).resolve()
VAULT_ORA = VAULT / "Projects" / "Ora"


def _body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        _head, _sep, text = text[4:].partition("\n---\n")
    return text.lstrip("\n").rstrip()


class TestGeneratingSourceTopology(unittest.TestCase):
    PAIRS = (
        ("Framework — Process Inference.md", "process-inference.md", "1.4"),
        ("Framework — Process Formalization.md", "process-formalization.md", "2.5"),
        ("Framework — Problem Evolution.md", "problem-evolution.md", "3.1"),
        ("Specification — F-Quality-Gate.md", "f-quality-gate.md", "2.0"),
    )

    def test_four_real_mirrors_have_exact_versioned_digest_parity(self):
        mappings = []
        for source_name, mirror_name, version in self.PAIRS:
            with self.subTest(source=source_name):
                source_body = _body(VAULT_ORA / source_name)
                mirror_body = _body(ROOT / "frameworks" / "book" / mirror_name)
                self.assertEqual(source_body, mirror_body)
                self.assertIn(f"Version {version}", source_body)
                mappings.append(
                    (
                        source_name,
                        version,
                        hashlib.sha256(source_body.encode("utf-8")).hexdigest(),
                    )
                )
        self.assertEqual(len({digest for _, _, digest in mappings}), 4)

    def test_direct_and_documentation_sources_do_not_gain_symmetry_mirrors(self):
        for name in (
            "process-coherence.md",
            "oversight-configuration.md",
            "meta-layer-architecture.md",
        ):
            self.assertFalse((ROOT / "frameworks" / "book" / name).exists())

    def test_process_coherence_resolves_the_direct_vault_source(self):
        expected = VAULT_ORA / "Framework — Process Coherence.md"
        self.assertEqual(Path(router.PROCESS_COHERENCE_PATH).resolve(), expected)
        self.assertTrue(expected.is_file())
        self.assertIn("Version 4.0", expected.read_text(encoding="utf-8"))

    def test_oversight_configuration_registry_resolves_direct_source(self):
        resolved = discovery.resolve_registered_vault_framework(
            ROOT / "frameworks" / "framework-registry.md",
            "Oversight Configuration",
            vault_root=VAULT,
            expected_version="2.0",
            required_source_tokens=(
                "OS-Setup",
                "OS-Modify",
                "OS-Verify",
                "PROCEED",
                "ACCEPT",
                "REDEFINE",
                "BLOCKED",
            ),
        )
        canonical = VAULT_ORA / "Framework — Oversight Configuration.md"
        self.assertEqual(Path(resolved["source_path"]), canonical)
        self.assertEqual(resolved["version"], "2.0")
        self.assertRegex(resolved["source_digest"], r"^sha256:[0-9a-f]{64}$")

    def test_direct_registry_resolution_fails_on_stale_metadata(self):
        registry = (ROOT / "frameworks" / "framework-registry.md").read_text(
            encoding="utf-8"
        )
        with tempfile.TemporaryDirectory() as tmp:
            stale = Path(tmp) / "registry.md"
            stale.write_text(
                discovery.markdown_registry_entry(
                    registry, "Oversight Configuration"
                ).replace("- **Version:** 2.0", "- **Version:** 1.0"),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                discovery.CapabilityDiscoveryError, "current version 2.0"
            ):
                discovery.resolve_registered_vault_framework(
                    stale,
                    "Oversight Configuration",
                    vault_root=VAULT,
                    expected_version="2.0",
                )

    def test_documentation_only_architecture_names_actual_runtime_surfaces(self):
        architecture = (VAULT_ORA / "Reference — Meta-Layer Architecture.md").read_text(
            encoding="utf-8"
        )
        for surface in (
            "process_contracts.py",
            "governed_process_runtime.py",
            "oversight_router.py",
            "oversight_actions.py",
            "boot.py",
        ):
            self.assertIn(surface, architecture)
            self.assertTrue((ORCH / surface).is_file())
        self.assertIn("documentation-only", architecture)


class TestGeneratingSourceSemantics(unittest.TestCase):
    def test_conditional_capability_routes_are_explicit(self):
        pif = _body(VAULT_ORA / "Framework — Process Inference.md")
        pff = _body(VAULT_ORA / "Framework — Process Formalization.md")
        pef = _body(VAULT_ORA / "Framework — Problem Evolution.md")
        self.assertIn("Direct operation is an action segment of that same PIF Process Run", pif)
        self.assertIn("PFF is required before the procedure is registered", pif)
        self.assertIn("exact versioned Process Definitions", pff)
        self.assertIn("seven directives", pff)
        self.assertIn("This framework is a contingent route", pef)
        self.assertIn("Known procedures and currently inferable complete solutions bypass PEF", pef)

    def test_quality_gate_is_observation_only_and_fail_closed(self):
        gate = _body(VAULT_ORA / "Specification — F-Quality-Gate.md")
        self.assertIn("Do not emit a Process Run directive", gate)
        self.assertIn("No observation releases a deliverable by itself", gate)
        self.assertIn("A corrected candidate is a new identity", gate)
        self.assertIn("withhold the candidate", gate)


class TestCapabilityDiscoveryAndControlledProbes(unittest.TestCase):
    READ = "scope:declared_inputs"
    WRITE = runtime_fixtures.OUTPUT
    EXTERNAL = runtime_fixtures.EXTERNAL

    @staticmethod
    def capability(*, effect_class: str = "inspection") -> dict:
        action = "inspect_environment" if effect_class == "inspection" else "probe_mutation"
        effect_type = "read_only" if effect_class == "inspection" else "local_reversible"
        return {
            "capability_id": f"tool:{action}",
            "category": "tool",
            "version": "1.0",
            "identity_digest": "sha256:" + hashlib.sha256(action.encode()).hexdigest(),
            "locator": f"runtime:{action}",
            "actions": [
                {
                    "action": action,
                    "effect_class": effect_class,
                    "effect_type": effect_type,
                }
            ],
        }

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = gpr.GovernedProcessRuntime(
            self.temp.name, now=lambda: runtime_fixtures.NOW
        )
        definition = runtime_fixtures.make_definition()
        run = runtime_fixtures.make_run("run-probe", definition)
        grant = run["contracts"]["authority"]["grants"][0]
        grant["actions"] = sorted(
            {
                *grant["actions"],
                "inspect_environment",
                "probe_mutation",
                "record_evidence",
            }
        )
        grant["effect_types"] = sorted(
            {*grant["effect_types"], "read_only", "local_reversible"}
        )
        grant["resource_selectors"] = sorted(
            {*grant["resource_selectors"], self.EXTERNAL}
        )
        run["contracts"]["artifact_scope"]["external_effect_selectors"] = [
            self.EXTERNAL
        ]
        self.runtime.create_run(definition, run)
        self.runtime.start_run("run-probe", reason="approved controlled probe")
        for condition_id in ("authority_changed", "unsafe_environment"):
            self.record_stop(condition_id, active=False, revision="initial")

    @staticmethod
    def exact_digest(value: object) -> str:
        body = json.dumps(value, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(body.encode()).hexdigest()

    def record_stop(self, condition_id: str, *, active: bool, revision: str):
        identity = self.exact_digest(
            {
                "condition_id": condition_id,
                "active": active,
                "revision": revision,
            }
        )
        return self.runtime.record_controlled_probe_stop_state(
            "run-probe",
            condition_id,
            active=active,
            state_identity_digest=identity,
            source=f"test:{revision}",
            node_id="verify",
        )

    @staticmethod
    def inspection_command(result: dict) -> discovery.ReadOnlyInspectionCommand:
        script = "import json; print(json.dumps(" + repr(result) + "))"
        return discovery.ReadOnlyInspectionCommand((sys.executable, "-c", script))

    def contract(self, capability: dict) -> dict:
        mutation = capability["actions"][0]["effect_class"] == "mutation"
        contract = {
            "probe_id": "availability",
            "assumption_id": "A1",
            "capability_id": capability["capability_id"],
            "action": capability["actions"][0]["action"],
            "selector": self.EXTERNAL if mutation else self.READ,
            "node_id": "verify",
            "segment_id": "probe-segment",
            "evidence_selector": self.WRITE,
            "evidence_requirement": "persist the exact observed signal",
            "success_condition": "provider returns the expected signal",
            "failure_condition": "provider disproves the assumption",
            "ambiguous_route": "stop and refine the probe",
            "max_attempts": 1,
            "authority_conditions": runtime_fixtures.CONDITION,
            "stop_conditions": ["authority_changed", "unsafe_environment"],
        }
        if mutation:
            contract.update(
                {
                    "reversible": True,
                    "idempotency_key": "probe-availability-1",
                    "pre_state_digest": self.exact_digest("isolated-before"),
                    "checkpoint_id": "probe:availability:checkpoint",
                    "recovery_route": "restore the isolated pre-state",
                    "recovery_identity_digest": self.exact_digest(
                        {"recovery_route": "restore the isolated pre-state"}
                    ),
                }
            )
        return contract

    def persist(self, capability: dict, contract: dict | None = None) -> dict:
        return discovery.persist_controlled_probe_contract(
            self.runtime,
            "run-probe",
            contract or self.contract(capability),
            capability,
        )

    def test_queries_tools_skills_frameworks_definitions_and_patterns(self):
        calls = []

        def provider(category):
            def query(objective):
                calls.append((category, objective))
                action = f"inspect_{category}"
                return [
                    {
                        "capability_id": f"{category}:{action}",
                        "category": category,
                        "version": "1.0",
                        "identity_digest": "sha256:"
                        + hashlib.sha256(action.encode()).hexdigest(),
                        "locator": f"test:{category}",
                        "actions": [
                            {
                                "action": action,
                                "effect_class": "inspection",
                                "effect_type": "read_only",
                            }
                        ],
                    }
                ]

            return query

        result = discovery.query_available_capabilities(
            "determine the viable transformation path",
            {category: provider(category) for category in discovery.CAPABILITY_CATEGORIES},
        )
        self.assertEqual(
            [category for category, _objective in calls],
            list(discovery.CAPABILITY_CATEGORIES),
        )
        self.assertEqual(len(result["capabilities"]), 5)
        self.assertTrue(
            all(
                status["status"] == "queried"
                for status in result["source_status"].values()
            )
        )
        persisted = discovery.record_capability_discovery(
            self.runtime, "run-probe", result
        )
        self.assertEqual(
            persisted["event"]["details"]["discovery_digest"],
            result["discovery_digest"],
        )

    def test_unavailable_and_failed_sources_remain_explicit(self):
        def failed(_objective):
            raise RuntimeError("registry offline")

        result = discovery.query_available_capabilities(
            "find a path", {"tool": failed}
        )
        self.assertEqual(result["source_status"]["tool"]["status"], "failed")
        self.assertEqual(
            result["source_status"]["skill"]["status"], "unavailable"
        )
        self.assertEqual(result["capabilities"], [])

    def test_action_routing_uses_declared_inspection_or_mutation_metadata(self):
        inspection = self.capability(effect_class="inspection")
        mutation = self.capability(effect_class="mutation")
        self.assertEqual(
            discovery.classify_capability_action(
                inspection, "inspect_environment"
            )["effect_class"],
            "inspection",
        )
        self.assertEqual(
            discovery.classify_capability_action(mutation, "probe_mutation")[
                "effect_class"
            ],
            "mutation",
        )
        with self.assertRaisesRegex(discovery.CapabilityDiscoveryError, "not declared"):
            discovery.classify_capability_action(inspection, "delete_everything")

    def test_inspection_probe_runs_with_read_authority_and_persists_evidence(self):
        capability = self.capability(effect_class="inspection")
        persisted = self.persist(capability)
        contract = persisted["contract"]
        self.assertEqual(contract["run_id"], "run-probe")
        self.assertEqual(
            contract["definition_ref"], self.runtime.load_run("run-probe")["definition_ref"]
        )
        self.assertRegex(persisted["contract_digest"], r"^sha256:[0-9a-f]{64}$")
        result = discovery.execute_controlled_probe(
            self.runtime,
            "run-probe",
            "availability",
            self.inspection_command(
                {"outcome": "confirmed", "evidence": "inspection signal present"}
            ),
        )
        self.assertEqual(result["status"], "executed")
        self.assertEqual(result["outcome"], "confirmed")
        self.assertIsNone(result["receipt_artifact_id"])
        evidence = self.runtime.load_artifact(
            "run-probe", result["evidence_artifact_id"]
        )
        self.assertEqual(evidence["role"], "evidence")
        observed = result["completed_record"]["event"]["details"]["details"]
        self.assertEqual(observed["capability_id"], capability["capability_id"])
        self.assertEqual(
            observed["capability_identity_digest"], capability["identity_digest"]
        )

    def test_unauthorized_mutation_never_calls_executor(self):
        capability = self.capability(effect_class="mutation")
        contract = self.contract(capability)
        contract["selector"] = "scope:undeclared"
        with self.assertRaisesRegex(gpr.AuthorityDeniedError, "outside external"):
            self.persist(capability, contract)
        self.assertFalse(
            any(
                record["event"]["event_type"] == "controlled_probe_contract_persisted"
                for record in self.runtime.load_records("run-probe")
            )
        )

    def test_mutation_probe_requires_exact_receipt_before_action_is_accepted(self):
        capability = self.capability(effect_class="mutation")
        with self.assertRaisesRegex(
            discovery.CapabilityDiscoveryError, "requires an external-effect receipt"
        ):
            self.persist(capability)
            discovery.execute_controlled_probe(
                self.runtime,
                "run-probe",
                "availability",
                lambda _request: {
                    "outcome": "confirmed",
                    "evidence": "mutation appeared to work",
                },
            )
        events = [
            record["event"]["event_type"]
            for record in self.runtime.load_records("run-probe")
        ]
        self.assertIn("controlled_probe_attempt_completed", events)
        self.assertIn("action_completed", events)
        action = next(
            record["event"]["details"]
            for record in self.runtime.load_records("run-probe")
            if record["event"]["event_type"] == "action_completed"
        )
        self.assertIsNone(action["receipt_artifact_id"])
        recovery = self.runtime.recovery_decision("run-probe")
        self.assertFalse(recovery["safe_to_resume"])
        self.assertIn("lacks a receipt", recovery["reason"])

    def test_authorized_mutation_binds_checkpoint_receipt_evidence_and_identity(self):
        capability = self.capability(effect_class="mutation")
        before = "sha256:" + hashlib.sha256(b"before").hexdigest()
        after = "sha256:" + hashlib.sha256(b"after").hexdigest()
        contract = self.contract(capability)
        contract["pre_state_digest"] = before
        self.persist(capability, contract)
        result = discovery.execute_controlled_probe(
            self.runtime,
            "run-probe",
            "availability",
            lambda request: {
                "outcome": "disconfirmed",
                "evidence": "the isolated mutation disproved A1",
                "receipt": {
                    "effect_id": "effect-1",
                    "pre_state_digest": before,
                    "post_state_digest": after,
                    "idempotency_key": request["idempotency_key"],
                },
            },
        )
        self.assertEqual(result["outcome"], "disconfirmed")
        receipt = self.runtime.load_artifact(
            "run-probe", result["receipt_artifact_id"]
        )
        self.assertEqual(receipt["role"], "external_effect_receipt")
        events = [
            record["event"]["event_type"]
            for record in self.runtime.load_records("run-probe")
        ]
        self.assertIn("checkpoint_created", events)
        self.assertIn("action_completed", events)
        self.assertIn("controlled_probe_attempt_completed", events)
        self.assertLess(
            events.index("controlled_probe_contract_persisted"),
            events.index("controlled_probe_attempt_started"),
        )
        self.assertLess(
            events.index("controlled_probe_attempt_started"),
            events.index("checkpoint_created"),
        )
        self.assertLess(
            events.index("checkpoint_created"),
            events.index("action_completed"),
        )

    def test_mutation_receipt_must_match_pre_state_persisted_before_execution(self):
        capability = self.capability(effect_class="mutation")
        contract = self.contract(capability)
        persisted_pre_state = contract["pre_state_digest"]
        different_pre_state = self.exact_digest("invented-after-execution")
        persisted = self.persist(capability, contract)
        self.assertEqual(
            persisted["contract"]["mutation_safety"]["pre_state_digest"],
            persisted_pre_state,
        )
        with self.assertRaisesRegex(
            discovery.CapabilityDiscoveryError, "persisted pre-state identity"
        ):
            discovery.execute_controlled_probe(
                self.runtime,
                "run-probe",
                "availability",
                lambda request: {
                    "outcome": "confirmed",
                    "evidence": "executor supplied a different pre-state afterward",
                    "receipt": {
                        "effect_id": "effect-wrong-pre-state",
                        "pre_state_digest": different_pre_state,
                        "post_state_digest": self.exact_digest("after"),
                        "idempotency_key": request["idempotency_key"],
                    },
                },
            )
        self.assertFalse(self.runtime.recovery_decision("run-probe")["safe_to_resume"])

    def test_persisted_attempt_ceiling_and_idempotency_prevent_caller_replay(self):
        capability = self.capability(effect_class="mutation")
        contract = self.contract(capability)
        self.persist(capability, contract)
        calls = []

        def mutate(request):
            calls.append(request)
            return {
                "outcome": "confirmed",
                "evidence": "one isolated effect",
                "receipt": {
                    "effect_id": "effect-once",
                    "pre_state_digest": request["pre_state_digest"],
                    "post_state_digest": self.exact_digest("after-once"),
                    "idempotency_key": request["idempotency_key"],
                },
            }

        discovery.execute_controlled_probe(
            self.runtime, "run-probe", "availability", mutate
        )
        replay = mock.Mock()
        with self.assertRaisesRegex(
            gpr.CorrectionDecisionRequired, "persisted Run state"
        ):
            discovery.execute_controlled_probe(
                self.runtime, "run-probe", "availability", replay
            )
        replay.assert_not_called()
        self.assertEqual(len(calls), 1)

        caller_rewritten = dict(contract)
        caller_rewritten["max_attempts"] = 2
        with self.assertRaisesRegex(
            discovery.CapabilityDiscoveryError, "requires max_attempts = 1"
        ):
            self.persist(capability, caller_rewritten)

        reused_key = dict(contract)
        reused_key["probe_id"] = "availability-replay"
        reused_key["checkpoint_id"] = "probe:availability-replay:checkpoint"
        with self.assertRaisesRegex(gpr.RunConflictError, "idempotency key"):
            self.persist(capability, reused_key)

    def test_arbitrary_inspection_callable_cannot_mutate_caller_state(self):
        capability = self.capability(effect_class="inspection")
        self.persist(capability)
        external_state = []

        def falsely_declared_inspection(_request):
            external_state.append("mutated")
            return {"outcome": "confirmed", "evidence": "should not be accepted"}

        with self.assertRaisesRegex(
            discovery.CapabilityDiscoveryError, "mechanically read-only"
        ):
            discovery.execute_controlled_probe(
                self.runtime,
                "run-probe",
                "availability",
                falsely_declared_inspection,
            )
        self.assertEqual(external_state, [])

    def test_read_only_inspection_sandbox_denies_filesystem_mutation(self):
        capability = self.capability(effect_class="inspection")
        self.persist(capability)
        marker = Path(self.temp.name) / "inspection-mutated"
        script = (
            "from pathlib import Path; import json,sys; "
            "Path(sys.argv[1]).write_text('mutated'); "
            "print(json.dumps({'outcome':'confirmed','evidence':'unsafe'}))"
        )
        boundary = discovery.ReadOnlyInspectionCommand(
            (sys.executable, "-c", script, str(marker))
        )
        with self.assertRaisesRegex(
            discovery.CapabilityDiscoveryError, "boundary refused or failed"
        ):
            discovery.execute_controlled_probe(
                self.runtime, "run-probe", "availability", boundary
            )
        self.assertFalse(marker.exists())

    def test_contract_persistence_fails_when_declared_stop_has_no_runtime_state(self):
        capability = self.capability(effect_class="inspection")
        contract = self.contract(capability)
        contract["stop_conditions"].append("unobserved_stop")
        with self.assertRaisesRegex(
            gpr.AuthorityDeniedError, "must be persisted before contract creation"
        ):
            self.persist(capability, contract)

    def test_generic_event_api_cannot_forge_controlled_probe_state(self):
        with self.assertRaisesRegex(gpr.AuthorityDeniedError, "reserved"):
            self.runtime.record_event(
                "run-probe",
                "controlled_probe_attempt_started",
                {"probe_id": "forged", "attempt": 99},
            )

    def test_active_stop_condition_withholds_probe_without_execution(self):
        capability = self.capability(effect_class="inspection")
        self.persist(capability)
        # The stop becomes active after contract persistence. Execution has no
        # caller-supplied stop argument and must fold the latest Run record.
        self.record_stop("unsafe_environment", active=True, revision="unsafe")
        executor = mock.Mock()
        result = discovery.execute_controlled_probe(
            self.runtime,
            "run-probe",
            "availability",
            executor,
        )
        self.assertEqual(result["status"], "withheld")
        self.assertEqual(
            result["stop_conditions"][0]["condition_id"], "unsafe_environment"
        )
        executor.assert_not_called()


class TestRegistrySemanticConsistency(unittest.TestCase):
    FRAMEWORK_ENTRIES = {
        "Problem Evolution": ("3.1", ("contingent route", "bypass")),
        "Process Formalization": ("2.5", ("Process Definition", "seven directives")),
        "Process Inference": ("1.4", ("capability queries", "controlled probes")),
        "Oversight Configuration": ("2.0", ("seven directives", "directly registered")),
        "Process Coherence": ("4.0", ("seven Process Run directives", "mechanical dispatch")),
    }
    OVERVIEW_ENTRIES = {
        "Framework — Oversight Configuration.md": ("2.0", ("seven directives", "direct vault source")),
        "Framework — Problem Evolution.md": ("3.1", ("contingent route", "bypass")),
        "Framework — Process Coherence.md": ("4.0", ("seven directives", "direct vault source")),
        "Framework — Process Formalization.md": ("2.5", ("Process Definition", "seven directives")),
        "Framework — Process Inference.md": ("1.4", ("capability queries", "controlled probes")),
        "Specification — F-Quality-Gate.md": ("2.0", ("observations", "ACCEPT")),
        "Reference — Meta-Layer Architecture.md": ("2.0", ("documentation-only", "runtime-first")),
    }

    def test_both_framework_registries_match_current_versions_and_semantics(self):
        paths = (
            VAULT_ORA / "Registry — Framework Registry.md",
            ROOT / "frameworks" / "framework-registry.md",
        )
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for heading, (version, semantics) in self.FRAMEWORK_ENTRIES.items():
                with self.subTest(path=path, heading=heading):
                    discovery.verify_registry_entry(
                        text,
                        heading,
                        version=version,
                        required_semantics=semantics,
                    )

    def test_ora_overview_registry_matches_all_seven_governed_sources(self):
        text = (
            VAULT_ORA / "Registry — Ora Overview and Document Registry.md"
        ).read_text(encoding="utf-8")
        for heading, (version, semantics) in self.OVERVIEW_ENTRIES.items():
            with self.subTest(heading=heading):
                discovery.verify_registry_entry(
                    text,
                    heading,
                    version=version,
                    required_semantics=semantics,
                )


class TestProcessCoherenceAdapter(unittest.TestCase):
    DIRECTIVES = (
        "PROCEED", "ACCEPT", "REVISE", "REPLAN", "REDEFINE", "ESCALATE", "BLOCKED",
    )

    def test_parser_accepts_exactly_the_seven_directives(self):
        for directive in self.DIRECTIVES:
            with self.subTest(directive=directive):
                parsed = router._parse_pc_verdict(f"reason\nDIRECTIVE: {directive}\n")
                self.assertEqual(parsed["directive"], directive)
        self.assertEqual(
            router._parse_pc_verdict("Supported directive: ACCEPT\n")["directive"],
            "ACCEPT",
        )
        for observation in ("PASS", "FAIL", "BROKEN"):
            with self.subTest(observation=observation):
                self.assertEqual(
                    router._parse_pc_verdict(f"VERDICT: {observation}\n")["directive"],
                    "UNKNOWN",
                )

    def test_legacy_redefinition_is_typed_ped_escalation(self):
        parsed = router._parse_pc_verdict("VERDICT: ESCALATE (redefinition)\n")
        self.assertEqual(parsed["directive"], "ESCALATE")
        self.assertEqual(parsed["authority_request_type"], "ped_redefinition")

    def test_generic_redefine_never_queues_and_typed_escalate_does(self):
        event = {
            "event_type": "FrameworkComplete",
            "definition_id": "definition.example",
            "definition_version": "2.0",
            "definition_digest": "sha256:abc",
        }
        bundle = OversightContextBundle(event=event, event_class="project-level")
        with (
            mock.patch.object(actions, "_append_decision_log_entry"),
            mock.patch.object(actions, "_append_actions_log"),
            mock.patch.object(queue, "add_entry") as add_entry,
        ):
            result = actions.apply_verdict(
                event, bundle, "PC-Milestone",
                {"directive": "REDEFINE", "reasoning": "definition defect"},
            )
            self.assertEqual(result["action"], "redefine")
            add_entry.assert_not_called()

            result = actions.apply_verdict(
                event, bundle, "PC-Milestone",
                {"directive": "ESCALATE", "reasoning": "needs permission"},
            )
            self.assertEqual(result["action"], "invalid_escalation")
            add_entry.assert_not_called()

            result = actions.apply_verdict(
                event, bundle, "PC-Milestone",
                {
                    "directive": "ESCALATE",
                    "authority_request_type": "definition_activation",
                    "reasoning": "activation is reserved",
                },
            )
            self.assertEqual(result["action"], "escalate")
            record = add_entry.call_args.args[0]
            self.assertEqual(record["authority_request_type"], "definition_activation")
            self.assertFalse(record["redefinition"])

    def test_revision_limit_stops_churn_without_inventing_escalation(self):
        event = {"event_type": "MilestoneClaimed", "milestone_id": "m1"}
        bundle = OversightContextBundle(event=event, event_class="project-level")
        counters = {}

        def mutate(_event, transform):
            nonlocal counters
            counters = transform(counters)

        with (
            mock.patch.object(actions, "_mutate_revise_counters", side_effect=mutate),
            mock.patch.object(actions, "_append_decision_log_entry"),
            mock.patch.object(actions, "_append_actions_log"),
            mock.patch.object(queue, "add_entry") as add_entry,
        ):
            results = [
                actions.apply_verdict(
                    event, bundle, "PC-Milestone",
                    {"directive": "REVISE", "reasoning": "same defect"},
                )
                for _ in range(actions.REVISE_LIMIT)
            ]
        self.assertEqual(results[-1]["action"], "revision_limit_reached")
        self.assertTrue(results[-1]["requires_failure_classification"])
        add_entry.assert_not_called()

    def test_legacy_queue_records_remain_typed_on_read(self):
        entry = queue._record_to_paused(
            {
                "queued_at": "2026-05-04T12:00:00+00:00",
                "event": {"event_type": "MilestoneClaimed"},
                "redefinition": True,
            },
            0,
        )
        self.assertEqual(entry.authority_request_type, "ped_redefinition")


if __name__ == "__main__":
    unittest.main()
