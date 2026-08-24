"""G1.24 drift-control closure invariants."""
from __future__ import annotations

import os
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VAULT = Path(
    os.environ.get("ORA_VAULT_PATH")
    or os.environ.get("ORA_VAULT")
    or (Path.home() / "Documents" / "vault")
).resolve()
VAULT_ORA = VAULT / "Projects" / "Ora"
ACCESSIBLE = VAULT_ORA / "Reference — Ora Accessible Overview.md"
ACCESSIBLE_MIRROR = ROOT / "help" / "accessible-overview.md"
TRACKER = VAULT_ORA / "Working — Ora Setup and Refinement.md"
REGISTRY = VAULT_ORA / "Registry — Ora Overview and Document Registry.md"
DCP_REPORT = (
    VAULT
    / "Administration"
    / "DCP"
    / "Working — DCP Drift Report 2026-07-27.md"
)
DCP_HISTORY = (
    VAULT / "Administration" / "DCP" / "Working — DCP Run History.md"
)
DCP_QUEUE = (
    VAULT
    / "Administration"
    / "DCP"
    / "Working — Documentation-Code Parity Escalation Queue.md"
)


def canonical_body_bytes(path: Path) -> bytes:
    raw = path.read_bytes()
    if not raw.startswith(b"---\n"):
        raise AssertionError(f"missing YAML frontmatter: {path}")
    end = raw.find(b"\n---\n", 4)
    if end < 0:
        raise AssertionError(f"unterminated YAML frontmatter: {path}")
    body = raw[end + 5 :]
    if body.startswith(b"\n"):
        body = body[1:]
    return body


class TestG124DriftControl(unittest.TestCase):
    def test_accessible_overview_is_an_exact_body_only_mirror(self):
        self.assertEqual(
            canonical_body_bytes(ACCESSIBLE),
            ACCESSIBLE_MIRROR.read_bytes(),
        )

    def test_accessible_overview_preserves_verified_runtime_provenance(self):
        canonical = ACCESSIBLE.read_text(encoding="utf-8")
        mirror = ACCESSIBLE_MIRROR.read_text(encoding="utf-8")
        for token in (
            "Closure currency note: Commons is the universal all-Dialogue view",
            "Commons rename pass: the default project",
            "Code-level rename landed (ora PR #218, commit `062b67a7`",
        ):
            with self.subTest(token=token):
                self.assertIn(token, canonical)
                self.assertIn(token, mirror)

    def test_tracker_and_registry_share_one_structured_current_boundary(self):
        pattern = re.compile(
            r"\*\*Current executable Gate-1 boundary:\*\* (G1\.\d+)"
        )
        tracker = pattern.findall(TRACKER.read_text(encoding="utf-8"))
        registry = pattern.findall(REGISTRY.read_text(encoding="utf-8"))
        self.assertEqual(len(tracker), 1)
        self.assertEqual(len(registry), 1)
        self.assertEqual(tracker, registry)

    def test_removed_closeout_suites_do_not_survive_as_runtime_contracts(self):
        for name in (
            "test_phase_3_3_user_guidance.py",
            "test_phase_3_5_closeout.py",
        ):
            with self.subTest(name=name):
                self.assertFalse(
                    (ROOT / "orchestrator" / "tests" / name).exists()
                )

    def test_delivered_full_state_audit_authenticates_all_five_repositories(self):
        report = DCP_REPORT.read_text(encoding="utf-8")
        for token in (
            "DRIFT-PRESENT — all five in-scope repos read; NOT coverage-degraded; NOT clean",
            "e49cc69af37796a6e1e25d3d13d2aeb6b71fd992",
            "942efde0c136b4a95683b6575f6cc621eea3dc2e",
            "74ce16d44b54e1b8e760403eeca29c515d447c4f",
            "305f98e34f05af46fe099e543bddf07900d2dd8a",
            "ee5a5c34dd6a2186be711e0541f8020ed6681d8e",
            "unregistered-canonical:0e9383eef0b192d1",
            "f503174859a6333175bc03a5f5fd305d88019efcc4e95a8a3c5cb4819969c949",
            "a2a96bddc4914622fe1e15f93683f67e29111a91513f02e60d388bdb4fcedf51",
            "this run does **not** assert zero omissions",
            "does **not** declare a release candidate",
            "does **not** close deferred G1.22A",
        ):
            with self.subTest(token=token):
                self.assertIn(token, report)

    def test_run_history_leads_with_corrected_rerun_and_preserves_preliminary_attempt(self):
        history = DCP_HISTORY.read_text(encoding="utf-8")
        corrected = "G1.24 FULL-STATE DCP-AUDIT — CORRECTED RERUN"
        preliminary = "G1.24 FULL-STATE DCP-AUDIT (on-demand"
        self.assertLess(history.index(corrected), history.index(preliminary))
        self.assertIn("main-street-independent `main`@ee5a5c34", history)
        self.assertIn("codex/dynamic-storyline-v6", history)

    def test_queue_closes_owned_findings_and_routes_new_blocker_exactly_once(self):
        queue = DCP_QUEUE.read_text(encoding="utf-8")
        for finding in ("E-068", "E-070", "E-071"):
            with self.subTest(finding=finding):
                self.assertIn(f"### ~~{finding} ", queue)
                self.assertNotRegex(queue, rf"(?m)^### {re.escape(finding)} ")
        self.assertEqual(queue.count("### E-093 —"), 1)
        for token in (
            "unregistered-canonical:0e9383eef0b192d1",
            "a2a96bddc4914622fe1e15f93683f67e29111a91513f02e60d388bdb4fcedf51",
            "deferred and incomplete G1.22A",
            "before full G1.22 or a release candidate can pass",
        ):
            with self.subTest(token=token):
                self.assertIn(token, queue)

    def test_submission_records_preserve_judgment_and_release_boundaries(self):
        for path in (TRACKER, REGISTRY):
            record = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("session_017HeFd9ZdmMVmpvJDvzZMLe", record)
                self.assertIn(
                    "e98e81a76daee8488f11344b817f7fb74a1e15fa", record
                )
                self.assertIn("E-093", record)
                self.assertIn("independent judgment", record)
                self.assertIn("no release candidate", record.lower())


if __name__ == "__main__":
    unittest.main()
