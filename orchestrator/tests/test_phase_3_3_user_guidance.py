"""G1.1 Phase 3.3 — canonical user guidance and mirror reconciliation."""
from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VAULT = Path(
    os.environ.get("ORA_VAULT_PATH")
    or os.environ.get("ORA_VAULT")
    or (Path.home() / "Documents" / "vault")
).resolve()
VAULT_ORA = VAULT / "Projects" / "Ora"
GUIDE = VAULT_ORA / "Guide — Using Ora.md"
MIRROR = ROOT / "docs" / "user-guide.md"
DESIGN = VAULT_ORA / "Working — Programming Oversight Manager Design.md"
TRACKER = VAULT_ORA / "Working — Ora Setup and Refinement.md"
REGISTRY = VAULT_ORA / "Registry — Ora Overview and Document Registry.md"
PAPER = VAULT_ORA / "Paper — Natural Language Programming.md"


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


class TestPhase33UserGuidance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guide_raw = GUIDE.read_text(encoding="utf-8")
        cls.guide = body(GUIDE)
        cls.mirror_raw = MIRROR.read_text(encoding="utf-8")
        cls.mirror = body(MIRROR)
        cls.design = DESIGN.read_text(encoding="utf-8")
        cls.tracker = TRACKER.read_text(encoding="utf-8")
        cls.registry = REGISTRY.read_text(encoding="utf-8")
        cls.paper = PAPER.read_text(encoding="utf-8")

    def test_vault_metadata_is_preserved_and_body_mirror_is_exact(self):
        for token in (
            "nexus:\n  - ora",
            "type: reference",
            "  - documentation",
            "  - guide",
            "date created: 2026-07-04",
            "date modified: 2026-07-19",
        ):
            self.assertIn(token, self.guide_raw)
        self.assertFalse(self.mirror_raw.startswith("---\n"))
        self.assertEqual(self.guide, self.mirror)

    def test_reconciliation_provenance_keeps_vault_first_authority(self):
        for token in (
            "runtime commit `86a888bc` reconciled into this vault canonical once",
            "6740f2fcc6663b5d5e1f57db9ce57de3578ac42c",
            "does not reverse the standing direction of truth",
            "future guide edits begin here",
            "No runtime behavior changed during that one-time documentation reconciliation",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.guide)

        guide_entry = h3_section(self.registry, "Guide — Using Ora.md")
        for token in (
            "verified general-operation behavior from runtime guide commit `86a888bc`",
            "promoted into the vault once",
            "does not reverse the vault-first direction of truth",
            "changed no runtime behavior",
            "Gate 3.3 subsequently found",
            "exactly synchronized",
        ):
            with self.subTest(registry_token=token):
                self.assertIn(token, guide_entry)

    def test_all_required_user_journeys_are_task_indexed(self):
        for heading in (
            "### Start the right kind of work",
            "### Confirm the project and artifact scope",
            "### Answer the management interview",
            "### Review and approve the plan",
            "### Leave and return",
            "### Respond to a decision request",
            "### Read the Run Inspector",
            "### Inspect or edit technical work",
            "### Find and invoke a reusable Process Definition",
            "### Understand activation and standing automation",
            "### Pause, stop, discuss, and recover",
            "### Close a terminal Run",
            "### Troubleshoot a governed Process",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, self.guide)

        for dimension in (
            "Intended result",
            "Affected parties",
            "Inputs and outputs",
            "Reuse",
            "Initiation",
            "Authority",
            "Exceptions",
            "Permissions",
            "Evidence",
            "Stopping",
        ):
            with self.subTest(dimension=dimension):
                self.assertIn(f"| {dimension} |", self.guide)

    def test_documented_controls_and_views_match_public_surfaces(self):
        for label in (
            "Approve and start",
            "Approve without starting",
            "Start approved plan",
            "Prepare plan",
            "Request plan changes",
            "Change scope or permissions",
            "Stop and retain the plan",
            "Approve request",
            "Deny request",
            "Authority unavailable",
            "Promote",
            "Preserve",
            "Archive",
            "Discard",
        ):
            with self.subTest(label=label):
                self.assertIn(f"**{label}**", self.guide)

        for view in (
            "Overview",
            "Plan",
            "Current State",
            "Decisions",
            "Changes",
            "Evidence",
            "Permissions",
            "Artifacts",
            "Technical",
        ):
            with self.subTest(view=view):
                self.assertIn(f"| **{view}** |", self.guide)

        index = (ROOT / "server" / "index-v3.html").read_text(encoding="utf-8")
        plan_review = (
            ROOT / "server" / "static" / "js" / "process-plan-review.js"
        ).read_text(encoding="utf-8")
        self.assertIn("/static/js/process-plan-review.js?v=g11-phase-3-3", index)
        self.assertIn("processEntryContract.intent === 'capability_construction'", index)
        inspector = (ROOT / "server" / "static" / "js" / "process-run-inspector.js").read_text(
            encoding="utf-8"
        )
        for contract in (
            "'approve_and_start'",
            "'approve_without_start'",
            "'request_changes'",
            "'change_scope_or_permissions'",
            "'stop_and_retain'",
            "'delegate'",
        ):
            self.assertIn(contract, plan_review)
        for label in (
            "Authority requested",
            "Approve request",
            "Deny request",
            "Authority unavailable",
            "Copy target path",
            "Current evidence supports the result.",
            "Current evidence does not yet support acceptance.",
        ):
            self.assertIn(label, inspector)

    def test_plan_review_controls_execute_in_a_real_dom(self):
        result = subprocess.run(
            ["node", "server/static/tests/test-process-plan-review.js"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("16/16 passed", result.stdout)

    def test_construction_invocation_activation_and_effects_stay_separate(self):
        for token in (
            "five places",
            "Set up a repeatable monthly cash-flow review",
            "Summarize the Programming documentation",
            "requires a visible project choice",
            "Construction, registration, invocation, activation, trigger binding, and external effects are separate authorities",
            "awaiting activation",
            "no invocation and no Process Run have started",
            "Forged, stale, unavailable, inactive, and out-of-scope references fail closed",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.guide)

    def test_evidence_recovery_and_lifecycle_limits_are_honest(self):
        for token in (
            "there is no user button that can convert stale or missing evidence into acceptance",
            "does **not** provide a general button to force an arbitrary active Run to pause, stop, resume, or reopen",
            "does not ship a general trigger-management or broad activation interface",
            "It does not replay a recorded mutation",
            "**Archive** marks the outputs archived; it does not delete source files",
            "**Discard** marks the outputs discarded; it does not delete source files",
            "There is no general **Reopen** action",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.guide)

    def test_design_tracker_and_registry_expose_the_current_gate_boundary(self):
        for token in (
            "Phase 3.3 implementation — REVISED; PENDING GATE 3.3",
            "### 29.13 User guide — AS BUILT 2026-07-19",
            "[x] User guide completed.",
            "### 29.11 Migration, compatibility, and rollback — NOT YET IMPLEMENTED",
            "### 29.12 Troubleshooting — NOT YET IMPLEMENTED",
            "Phase 3.4 maintainer reference",
        ):
            with self.subTest(design_token=token):
                self.assertIn(token, self.design)

        for token in (
            "Current phase:** Part 3, Phase 3.3",
            "Phase 3.3 authority boundary",
            "Phase 3.4 maintainer reference/migration/rollback/troubleshooting material",
            "Gate 3.3 then proved that the browser could not operate",
            "does not change canonical package identity or enter Phase 3.4",
        ):
            with self.subTest(tracker_token=token):
                self.assertIn(token, self.tracker)

        for token in (
            "Phase 3.3 user guidance is complete pending Gate 3.3",
            "Phase 3.4 is not authorized",
            "maintainer §§29.11–29.12 remain gated",
        ):
            with self.subTest(registry_token=token):
                self.assertIn(token, self.registry)

    def test_conceptual_and_implementation_companions_are_permanent(self):
        self.assertIn(
            "[[Paper — Natural Language Programming]] for the conceptual account",
            self.design,
        )
        self.assertIn(
            "[[Reference — Ora Technical Documentation]] for the implementation account",
            self.design,
        )
        self.assertIn(
            "[[Guide — Using Ora]] — the Phase 3.3 procedural companion",
            self.paper,
        )


if __name__ == "__main__":
    unittest.main()
