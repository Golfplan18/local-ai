"""Focused regression tests for the registered vault/Ora drift pairs."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify-implementation.py"
MODULE_NAME = "ora_verify_implementation"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT)
assert SPEC is not None and SPEC.loader is not None
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = VERIFY
SPEC.loader.exec_module(VERIFY)


class DriftParityTests(unittest.TestCase):
    def test_registered_pairs_are_complete_and_repo_relative(self):
        expected = [
            (
                "Reference — Analytical Territories.md",
                "architecture/territories.md",
            ),
            (
                "Reference — Mode Specification Template.md",
                "architecture/mode-template.md",
            ),
            (
                "Reference — Disambiguation Style Guide.md",
                "architecture/disambiguation-style-guide.md",
            ),
            (
                "Reference — Lens Library Specification.md",
                "architecture/lens-library-specification.md",
            ),
            (
                "Reference — Pre-Routing Pipeline Architecture.md",
                "architecture/pre-routing-pipeline.md",
            ),
            (
                "Registry — Signal Vocabulary Registry.md",
                "architecture/signal-vocabulary-registry.md",
            ),
            (
                "Reference — Within-Territory Disambiguation Trees.md",
                "architecture/within-territory-trees.md",
            ),
            (
                "Reference — Cross-Territory Adjacency.md",
                "architecture/cross-territory-adjacency.md",
            ),
            (
                "Reference — Trusted Web Sources.md",
                "architecture/trusted-web-sources.md",
            ),
            (
                "Framework — Conversation Processing Pipeline.md",
                "frameworks/book/conversation-processing.md",
            ),
            (
                "Specification — F-Quality-Gate.md",
                "frameworks/book/f-quality-gate.md",
            ),
        ]
        self.assertEqual(VERIFY.DRIFT_PAIRS, expected)
        self.assertIs(VERIFY.ARCHITECTURE_PAIRS, VERIFY.DRIFT_PAIRS)

    def test_nested_operational_copy_matches_modulo_vault_yaml(self):
        with tempfile.TemporaryDirectory(prefix="ora-drift-") as tmp:
            root = Path(tmp)
            vault = root / "vault"
            ora = root / "ora"
            vault.mkdir()
            operational = ora / "frameworks" / "book" / "operational.md"
            operational.parent.mkdir(parents=True)
            body = "# Shared body\n\nPortable content.\n"
            (vault / "Canonical.md").write_text(
                "---\nnexus: ora\ntype: framework\n---\n\n" + body,
                encoding="utf-8",
            )
            operational.write_text(body, encoding="utf-8")

            with (
                mock.patch.object(VERIFY, "VAULT_ROOT", vault),
                mock.patch.object(VERIFY, "ORA_ROOT", ora),
                mock.patch.object(
                    VERIFY,
                    "DRIFT_PAIRS",
                    [("Canonical.md", "frameworks/book/operational.md")],
                ),
            ):
                result = VERIFY.check_drift_parity(verbose=True)

            self.assertTrue(result.passed, result.details)
            self.assertEqual(
                result.details,
                ["OK: Canonical.md ↔ frameworks/book/operational.md"],
            )

    def test_nested_operational_copy_reports_first_differing_line(self):
        with tempfile.TemporaryDirectory(prefix="ora-drift-") as tmp:
            root = Path(tmp)
            vault = root / "vault"
            ora = root / "ora"
            vault.mkdir()
            operational = ora / "frameworks" / "book" / "operational.md"
            operational.parent.mkdir(parents=True)
            (vault / "Canonical.md").write_text(
                "---\nnexus: ora\ntype: framework\n---\n# Same\nVault line\n",
                encoding="utf-8",
            )
            operational.write_text("# Same\nOra line\n", encoding="utf-8")

            with (
                mock.patch.object(VERIFY, "VAULT_ROOT", vault),
                mock.patch.object(VERIFY, "ORA_ROOT", ora),
                mock.patch.object(
                    VERIFY,
                    "DRIFT_PAIRS",
                    [("Canonical.md", "frameworks/book/operational.md")],
                ),
            ):
                result = VERIFY.check_drift_parity()

            self.assertFalse(result.passed)
            self.assertEqual(
                result.details,
                [
                    "Drift: Canonical.md ↔ frameworks/book/operational.md "
                    "differ (first diff at line 2)"
                ],
            )


if __name__ == "__main__":
    unittest.main()
