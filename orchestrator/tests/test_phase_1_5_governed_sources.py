"""Phase 1.5 topology, directive, and generating-source regressions."""
from __future__ import annotations

import hashlib
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
            "success_condition": "provider returns the expected signal",
            "failure_condition": "provider disproves the assumption",
            "ambiguous_route": "stop and refine the probe",
            "attempt": 1,
            "max_attempts": 1,
            "authority_conditions": runtime_fixtures.CONDITION,
            "stop_conditions": ["authority_changed", "unsafe_environment"],
        }
        if mutation:
            contract.update(
                {
                    "reversible": True,
                    "idempotency_key": "probe-availability-1",
                    "recovery_route": "restore the isolated pre-state",
                }
            )
        return contract

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
        requests = []
        result = discovery.execute_controlled_probe(
            self.runtime,
            "run-probe",
            self.contract(capability),
            capability,
            lambda request: requests.append(request)
            or {"outcome": "confirmed", "evidence": "inspection signal present"},
        )
        self.assertEqual(result["status"], "executed")
        self.assertEqual(result["outcome"], "confirmed")
        self.assertEqual(requests[0]["effect_class"], "inspection")
        self.assertIsNone(result["receipt_artifact_id"])
        evidence = self.runtime.load_artifact(
            "run-probe", result["evidence_artifact_id"]
        )
        self.assertEqual(evidence["role"], "evidence")
        observed = result["observed_record"]["event"]["details"]
        self.assertEqual(observed["capability_id"], capability["capability_id"])
        self.assertEqual(
            observed["capability_identity_digest"], capability["identity_digest"]
        )

    def test_unauthorized_mutation_never_calls_executor(self):
        capability = self.capability(effect_class="mutation")
        contract = self.contract(capability)
        contract["selector"] = "scope:undeclared"
        executor = mock.Mock()
        with self.assertRaisesRegex(gpr.AuthorityDeniedError, "outside external"):
            discovery.execute_controlled_probe(
                self.runtime, "run-probe", contract, capability, executor
            )
        executor.assert_not_called()
        self.assertFalse(
            any(
                record["event"]["event_type"] == "controlled_probe_planned"
                for record in self.runtime.load_records("run-probe")
            )
        )

    def test_mutation_probe_requires_exact_receipt_before_action_is_accepted(self):
        capability = self.capability(effect_class="mutation")
        with self.assertRaisesRegex(
            discovery.CapabilityDiscoveryError, "requires an external-effect receipt"
        ):
            discovery.execute_controlled_probe(
                self.runtime,
                "run-probe",
                self.contract(capability),
                capability,
                lambda _request: {
                    "outcome": "confirmed",
                    "evidence": "mutation appeared to work",
                },
            )
        events = [
            record["event"]["event_type"]
            for record in self.runtime.load_records("run-probe")
        ]
        self.assertIn("controlled_probe_failed", events)
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
        result = discovery.execute_controlled_probe(
            self.runtime,
            "run-probe",
            self.contract(capability),
            capability,
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
        self.assertIn("controlled_probe_observed", events)

    def test_active_stop_condition_withholds_probe_without_execution(self):
        capability = self.capability(effect_class="inspection")
        executor = mock.Mock()
        result = discovery.execute_controlled_probe(
            self.runtime,
            "run-probe",
            self.contract(capability),
            capability,
            executor,
            active_stop_conditions=["unsafe_environment"],
        )
        self.assertEqual(result["status"], "withheld")
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
