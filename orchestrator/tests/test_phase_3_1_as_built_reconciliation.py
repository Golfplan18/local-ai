"""G1.1 Phase 3.1 — as-built documentation and identity reconciliation."""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path


ORCH = Path(__file__).resolve().parents[1]
ROOT = ORCH.parent
if str(ORCH) not in sys.path:
    sys.path.insert(0, str(ORCH))

import process_contracts as contracts  # noqa: E402
from tests.test_phase_1_6_programming_definition import (  # noqa: E402
    body,
    embedded_definition,
)


VAULT = Path(
    os.environ.get("ORA_VAULT_PATH")
    or os.environ.get("ORA_VAULT")
    or (Path.home() / "Documents" / "vault")
).resolve()
VAULT_ORA = VAULT / "Projects" / "Ora"


class TestPhase31AsBuiltReconciliation(unittest.TestCase):
    def test_current_mirror_topology_and_versions(self):
        pairs = (
            ("Framework — Process Inference.md", "process-inference.md", "1.5"),
            ("Framework — Process Formalization.md", "process-formalization.md", "2.6"),
            ("Framework — Problem Evolution.md", "problem-evolution.md", "3.2"),
            ("Specification — F-Quality-Gate.md", "f-quality-gate.md", "2.1"),
            ("Framework — Programming.md", "programming.md", "2.0.1"),
        )
        for canonical_name, mirror_name, version in pairs:
            with self.subTest(canonical=canonical_name):
                canonical = body(VAULT_ORA / canonical_name)
                mirror = body(ROOT / "frameworks" / "book" / mirror_name)
                self.assertEqual(canonical, mirror)
                self.assertIn(version, canonical)

        self.assertIn(
            "Version 4.1",
            (VAULT_ORA / "Framework — Process Coherence.md").read_text(
                encoding="utf-8"
            ),
        )
        self.assertIn(
            "Version 2.1",
            (VAULT_ORA / "Framework — Oversight Configuration.md").read_text(
                encoding="utf-8"
            ),
        )
        meta = (VAULT_ORA / "Reference — Meta-Layer Architecture.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Version 2.1", meta)
        self.assertIn("G1.1 as-built architecture", meta)
        for absent in (
            "process-coherence.md",
            "oversight-configuration.md",
            "meta-layer-architecture.md",
        ):
            self.assertFalse((ROOT / "frameworks" / "book" / absent).exists())

    def test_programming_issued_package_identity_is_unchanged_and_valid(self):
        canonical = body(VAULT_ORA / "Framework — Programming.md")
        definition = embedded_definition(canonical)
        validated = contracts.validate_process_definition(definition)
        expected = (
            "sha256:"
            "b79d06b401ca54ec62588ab9cd64393fc049d4cf599298a5b057d93aa4e2a927"
        )
        self.assertEqual(validated["version"], "2.0.1")
        self.assertEqual(validated["digest"], expected)
        manifest = validated["package_manifest"]
        self.assertEqual(manifest["package_version"], "2.0.1")
        self.assertEqual(manifest["definition_ref"]["digest"], expected)
        self.assertEqual(manifest["members"][0]["identity"]["digest"], expected)

    def test_framework_registries_are_semantically_synchronized(self):
        vault_registry = body(VAULT_ORA / "Registry — Framework Registry.md")
        runtime_registry = body(ROOT / "frameworks" / "framework-registry.md")
        expected = {
            "Problem Evolution": "3.2",
            "Process Formalization": "2.6",
            "Process Inference": "1.5",
            "Programming": "2.0.1",
            "Oversight Configuration": "2.1",
            "Process Coherence": "4.1",
        }
        for heading, version in expected.items():
            pattern = rf"### {re.escape(heading)}\n(?:(?!\n### )[\s\S])*?\n- \*\*Version:\*\* {re.escape(version)}(?:\n|$)"
            self.assertRegex(vault_registry, pattern)
            self.assertRegex(runtime_registry, pattern)

    def test_technical_documentation_has_exact_body_mirror(self):
        canonical = body(VAULT_ORA / "Reference — Ora Technical Documentation.md")
        mirror = body(ROOT / "docs" / "technical-documentation.md")
        self.assertEqual(canonical, mirror)
        for token in (
            "Part VI — Governed Processes",
            "6740f2fcc6663b5d5e1f57db9ce57de3578ac42c",
            "ora.process-contracts/1.0",
            "ora.process-graph/1.0",
            "ora.process-package/1.0",
            "G1.2's separately owned full Gear 1/2/3 pipeline specification",
        ):
            self.assertIn(token, canonical)

    def test_design_registry_and_tracker_record_phase_boundary(self):
        design = (VAULT_ORA / "Working — Programming Oversight Manager Design.md").read_text(
            encoding="utf-8"
        )
        for section in range(1, 11):
            self.assertIn(f"### 29.{section}", design)
        self.assertNotIn("### 29.1 Release identity — NOT YET IMPLEMENTED", design)
        self.assertIn("### 29.11 Migration, compatibility, and rollback — NOT YET IMPLEMENTED", design)
        self.assertIn("Phase 3.2", design)

        tracker = (VAULT_ORA / "Working — Ora Setup and Refinement.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Phase 3.2", tracker)
        self.assertIn("Phase 3.1 passed", tracker)

        overview = (
            VAULT_ORA / "Registry — Ora Overview and Document Registry.md"
        ).read_text(encoding="utf-8")
        for token in (
            "Active canonical (v1.5",
            "Active canonical (v2.6",
            "Active canonical (v3.2",
            "Active canonical (v4.1",
            "Active governed observation contract (v2.1",
            "Active architecture reference (v2.1",
            "Phases 3.1 and 3.2 are accepted",
        ):
            self.assertIn(token, overview)


if __name__ == "__main__":
    unittest.main()
