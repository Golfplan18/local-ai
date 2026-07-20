"""G1.1 Phase 3.4 — maintainer reference, live semantics, and mirror parity."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


ORCH = Path(__file__).resolve().parents[1]
ROOT = ORCH.parent
if str(ORCH) not in sys.path:
    sys.path.insert(0, str(ORCH))

import process_contracts as contracts  # noqa: E402
import process_definition_registry as definition_registry  # noqa: E402
import process_library_lifecycle as library  # noqa: E402
import process_management_interview as interview  # noqa: E402
import process_plan_approval as plan  # noqa: E402


VAULT = Path(
    os.environ.get("ORA_VAULT_PATH")
    or os.environ.get("ORA_VAULT")
    or (Path.home() / "Documents" / "vault")
).resolve()
VAULT_ORA = VAULT / "Projects" / "Ora"
CANONICAL = VAULT_ORA / "Reference — Ora Technical Documentation.md"
MIRROR = ROOT / "docs" / "technical-documentation.md"
DESIGN = VAULT_ORA / "Working — Programming Oversight Manager Design.md"
TRACKER = VAULT_ORA / "Working — Ora Setup and Refinement.md"
REGISTRY = VAULT_ORA / "Registry — Ora Overview and Document Registry.md"


def body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end < 0:
            raise AssertionError(f"unterminated frontmatter: {path}")
        text = text[end + 5 :]
    return text.lstrip("\n").rstrip()


def h3_section(text: str, heading: str) -> str:
    marker = f"### {heading}\n"
    start = text.index(marker)
    end = text.find("\n### ", start + len(marker))
    return text[start:] if end < 0 else text[start:end]


class TestPhase34MaintainerReference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical_raw = CANONICAL.read_text(encoding="utf-8")
        cls.canonical = body(CANONICAL)
        cls.mirror_raw = MIRROR.read_text(encoding="utf-8")
        cls.mirror = body(MIRROR)
        cls.design = DESIGN.read_text(encoding="utf-8")
        cls.tracker = TRACKER.read_text(encoding="utf-8")
        cls.registry = REGISTRY.read_text(encoding="utf-8")

    def test_vault_metadata_and_exact_body_mirror(self):
        for token in (
            "nexus:\n  - ora",
            "type: reference",
            "date created: 2026-07-04",
            "date modified: 2026-07-19",
        ):
            self.assertIn(token, self.canonical_raw)
        self.assertFalse(self.mirror_raw.startswith("---\n"))
        self.assertEqual(self.canonical, self.mirror)
        self.assertIn("5bcba5027dc64dad878cb79a37c845a2de492d1d", self.canonical)

    def test_documented_contract_catalog_matches_live_constants(self):
        for version in (
            contracts.CONTRACT_SCHEMA_VERSION,
            contracts.GRAPH_SCHEMA_VERSION,
            contracts.PACKAGE_SCHEMA_VERSION,
            definition_registry.REGISTRY_ENTRY_SCHEMA_VERSION,
            definition_registry.REGISTRATION_ANCHOR_SCHEMA_VERSION,
        ):
            with self.subTest(version=version):
                self.assertIn(f"`{version}`", self.canonical)

        object_labels = {
            "process_definition": "Process Definition",
            "process_run": "Process Run",
            "artifact": "Artifact",
            "event_transition_record": "event/transition record",
        }
        self.assertEqual(set(object_labels), set(contracts.ROOT_OBJECT_FAMILIES))
        for name in contracts.ROOT_OBJECT_FAMILIES:
            self.assertIn(object_labels[name], self.canonical)
        for name in contracts.ATTACHED_CONTRACTS:
            documented = {
                "stop_escalation": "stop/escalation",
            }.get(name, name.replace("_", " "))
            self.assertIn(documented, self.canonical.lower())

    def test_graph_and_transition_tables_match_live_grammar(self):
        for kind in contracts.GRAPH_NODE_KINDS:
            with self.subTest(kind=kind):
                self.assertIn(f"`{kind}`", self.canonical)
        for directive, target in contracts.DIRECTIVE_TARGET_STATES.items():
            with self.subTest(directive=directive):
                self.assertIn(f"| `{directive}` | `{target}` |", self.canonical)
        for outcome in contracts.OBSERVATION_OUTCOMES:
            self.assertIn(f"`{outcome}`", self.canonical)

    def test_dialogue_plan_and_library_lifecycle_versions_are_live(self):
        for version in (
            interview.BINDING_SCHEMA_VERSION,
            interview.INTERVIEW_SCHEMA_VERSION,
            plan.PLAN_SCHEMA_VERSION,
            plan.PLAN_STATE_SCHEMA_VERSION,
            library.LIBRARY_SCHEMA_VERSION,
            library.LIFECYCLE_SCHEMA_VERSION,
        ):
            with self.subTest(version=version):
                self.assertIn(f"`{version}`", self.canonical)
        for lifecycle in ("plan:in-planning", "plan:approved"):
            self.assertIn(f"`{lifecycle}`", self.canonical)

    def test_required_maintainer_subjects_are_complete(self):
        for heading in (
            "### Maintainer object and storage reference",
            "### Judgment-step configuration",
            "### Graph grammar and safe graph changes",
            "### Transition routing and correction",
            "### Parent-child continuation and recovery",
            "### Evidence, identity, packages, and catalogs",
            "### Lifecycle and version binding",
            "### Regression obligations and maintainer change protocol",
            "### Migration, compatibility, disablement, and rollback",
            "### Maintainer troubleshooting",
            "### Known maintainer limitations",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, self.canonical)

        for safety_rule in (
            "never edit a stored version or select “latest”",
            "never edit `run.json`",
            "never replays child mutations",
            "never replays child mutations",
            "uncertain mutation",
            "restoring the prior code together with the untouched pre-upgrade store snapshot",
            "no automatic in-place migration tool",
        ):
            with self.subTest(safety_rule=safety_rule):
                self.assertIn(safety_rule, self.canonical)

    def test_code_and_public_plan_surface_map_exist(self):
        plan_review = ROOT / "server" / "static" / "js" / "process-plan-review.js"
        server = (ROOT / "server" / "server.py").read_text(encoding="utf-8")
        self.assertTrue(plan_review.is_file())
        self.assertIn("`server/static/js/process-plan-review.js`", self.canonical)
        self.assertIn("`/api/process-plan-context/<dialogue>`", self.canonical)
        self.assertIn("/api/process-plan-context/", server)

    def test_design_tracker_and_registry_preserve_accepted_gate_3_4(self):
        for token in (
            "Phase 3.3 implementation — COMPLETE; GATE 3.3 ACCEPTED",
            "Phase 3.4 implementation — COMPLETE; GATE 3.4 ACCEPTED",
            "Phase 3.5 implementation — COMPLETE; GATE 3.5 ACCEPTED",
            "### 29.11 Migration, compatibility, and rollback — AS BUILT 2026-07-19",
            "### 29.12 Troubleshooting — AS BUILT 2026-07-19",
            "- [x] Migration, rollback, recovery, and troubleshooting documented.",
        ):
            self.assertIn(token, self.design)
        for token in (
            "Final disposition:** G1.1 complete",
            "Accepted Phase 3.5 authority boundary",
            "Phase 3.4 passed after the maintainer reference",
        ):
            self.assertIn(token, self.tracker)

        technical = h3_section(self.registry, "Reference — Ora Technical Documentation.md")
        for token in (
            "pinned for runtime behavior to Gate 3.3 commit `5bcba502`",
            "eleven-node graph grammar",
            "staged migration/disablement/rollback",
            "Gate 3.4 documentation/test acceptance at `6824bb03`",
            "Gate 3.5 passed at runtime closeout commit `71f0ecf7`",
        ):
            self.assertIn(token, technical)

    def test_obsolete_placeholders_and_premature_closeout_are_rejected(self):
        current_records = "\n".join((self.design, self.tracker, self.registry))
        for obsolete in (
            "### 29.11 Migration, compatibility, and rollback — NOT YET IMPLEMENTED",
            "### 29.12 Troubleshooting — NOT YET IMPLEMENTED",
            "Current phase:** Part 3, Phase 3.3",
            "Phase 3.4 is not authorized",
            "Phase 3.4 implementation — COMPLETE; PENDING GATE 3.4",
            "Phase 3.4 is complete pending Gate 3.4",
            "maintainer §§29.11–29.12 remain gated",
            "- [ ] Migration, rollback, recovery, and troubleshooting documented.",
            "Phase 3.5 remains unauthorized",
            "Phase 3.5 implementation — COMPLETE; PENDING GATE 3.5",
        ):
            self.assertNotIn(obsolete, current_records)
        self.assertIn("GATE 3.5 ACCEPTED", current_records)
        self.assertIn("G1.1 is complete", current_records)


if __name__ == "__main__":
    unittest.main()
