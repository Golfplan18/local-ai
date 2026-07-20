"""G1.1 Phase 3.2 — conceptual/public guide reconciliation."""
from __future__ import annotations

import os
import unittest
from pathlib import Path


VAULT = Path(
    os.environ.get("ORA_VAULT_PATH")
    or os.environ.get("ORA_VAULT")
    or (Path.home() / "Documents" / "vault")
).resolve()
VAULT_ORA = VAULT / "Projects" / "Ora"
PAPER = VAULT_ORA / "Paper — Natural Language Programming.md"
DESIGN = VAULT_ORA / "Working — Programming Oversight Manager Design.md"
TRACKER = VAULT_ORA / "Working — Ora Setup and Refinement.md"
OVERVIEW = VAULT_ORA / "Registry — Ora Overview and Document Registry.md"


def section(text: str, heading: str) -> str:
    marker = f"#### {heading}\n"
    start = text.index(marker)
    end = text.find("\n#### ", start + len(marker))
    return text[start:] if end < 0 else text[start:end]


def h3_section(text: str, heading: str) -> str:
    marker = f"### {heading}\n"
    start = text.index(marker)
    end = text.find("\n### ", start + len(marker))
    return text[start:] if end < 0 else text[start:end]


class TestPhase32ConceptualPublicGuide(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paper = PAPER.read_text(encoding="utf-8")
        cls.design = DESIGN.read_text(encoding="utf-8")
        cls.tracker = TRACKER.read_text(encoding="utf-8")
        cls.overview = OVERVIEW.read_text(encoding="utf-8")

    def test_existing_consolidated_paper_is_the_active_public_target(self):
        self.assertIn("status: active", self.paper)
        self.assertIn("date modified: 2026-07-19", self.paper)
        self.assertIn("# Natural Language Programming", self.paper)
        self.assertIn(
            "Ora: Natural-Language Programming Through Managed Delegation",
            self.paper,
        )
        self.assertGreater(len(self.paper.split()), 2500)
        self.assertEqual(
            list(VAULT_ORA.glob("Paper — *Managed Delegation*.md")), []
        )

    def test_both_governing_propositions_are_verbatim(self):
        for proposition in (
            "Ora lets people manage AI the way they manage capable professionals: "
            "define the result, clarify the important choices, approve the plan, "
            "delegate the work, and return for decisions or verified completion.",
            "A model contributes bounded judgment. Ora supplies the durable process "
            "that establishes state, limits authority, verifies decisions, corrects "
            "errors, and preserves accountability.",
        ):
            self.assertIn(proposition, self.paper)

    def test_every_required_phase_3_2_concept_is_explained(self):
        for concept in (
            "Managed delegation",
            "Natural Language Programming",
            "bounded judgment",
            "does not use Agent as a canonical runtime object",
            "capability-producing-capability",
            "result artifact",
            "capability artifact",
            "Process Definition",
            "Process Run",
            "PFF",
            "PIF",
            "PEF",
            "Human authority stays explicit",
            "evidence",
            "REVISE",
            "ESCALATE",
            "Process Library",
            "standing automation",
            "Construction",
            "Invocation",
            "Activation",
            "external effect",
        ):
            with self.subTest(concept=concept):
                self.assertIn(concept, self.paper)

    def test_agent_rejection_and_leave_return_boundary_are_explicit(self):
        for token in (
            "not durable digital workers with general discretion",
            "does not introduce a cognition-bearing daemon",
            "does not mean a model acquires an open-ended mission",
            "Triggers, where separately authorized",
            "do not bypass the definition’s authority",
        ):
            self.assertIn(token, self.paper)

    def test_public_claims_include_current_limits(self):
        for limitation in (
            "bounded non-external action entry",
            "independent final acceptance",
            "Broad trigger management",
            "deterministic boundaries",
            "validated on macOS",
            "does not create unscheduled autonomous cognition",
        ):
            self.assertIn(limitation, self.paper)

    def test_registry_design_and_tracker_bind_the_exact_phase_boundary(self):
        entry = section(self.overview, "Paper — Natural Language Programming.md")
        for token in (
            "G1.1 Phase 3.2 conceptual/public guide",
            "Managed delegation",
            "bounded-judgment components",
            "capability may produce another reusable capability",
            "Active canonical public guide",
        ):
            self.assertIn(token, entry)

        self.assertIn(
            "Phase 3.2 implementation — COMPLETE; GATE 3.2 ACCEPTED",
            self.design,
        )
        self.assertIn(
            "[x] Public conceptual guide explains managed delegation",
            self.design,
        )
        self.assertIn(
            "### 29.13 User guide — AS BUILT 2026-07-19",
            self.design,
        )
        self.assertIn("Current phase:** Part 3, Phase 3.5", self.tracker)
        self.assertIn(
            "Phase 3.5 closeout execution is complete pending independent Gate 3.5",
            self.overview,
        )
        self.assertNotIn("Phase 3.5 is not authorized", self.overview)
        self.assertNotIn("GATE 3.5 ACCEPTED", self.overview)

    def test_current_records_reject_obsolete_phase_1_6_future_state(self):
        tracker_entry = h3_section(
            self.tracker,
            "G1.1 — Governed process construction and Programming Oversight proof of concept — 🟡",
        )
        design_entry = h3_section(
            self.overview,
            "Working — Programming Oversight Manager Design.md",
        )
        for current in (tracker_entry, design_entry):
            self.assertIn("Phase 1.6", current)
            self.assertIn("ora/programming@2.0.1", current)
            self.assertIn(
                "sha256:b79d06b401ca54ec62588ab9cd64393fc049d4cf599298a5b057d93aa4e2a927",
                current,
            )
            self.assertIn("historical derivation evidence", current)
            self.assertNotIn("will be regenerated in Phase 1.6", current)
            self.assertNotIn(
                "will be regenerated after its generating sources synchronize",
                current,
            )


if __name__ == "__main__":
    unittest.main()
