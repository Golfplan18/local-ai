"""Phase 1.5 topology, directive, and generating-source regressions."""
from __future__ import annotations

import hashlib
import os
import sys
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
from oversight_context import OversightContextBundle  # noqa: E402


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
        ("Framework — Process Inference.md", "process-inference.md", "1.3"),
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
        registry = (ROOT / "frameworks" / "framework-registry.md").read_text(
            encoding="utf-8"
        )
        canonical = VAULT_ORA / "Framework — Oversight Configuration.md"
        self.assertTrue(canonical.is_file())
        self.assertIn("~/Documents/vault/Projects/Ora/Framework — Oversight Configuration.md", registry)
        self.assertIn("- **Version:** 2.0", registry)
        self.assertIn("all seven", canonical.read_text(encoding="utf-8").lower())

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
