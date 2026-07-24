"""G1.1 Phase 3.5 closeout artifacts, reconciliation, and negative status checks."""
from __future__ import annotations

import hashlib
import os
import re
import unittest
from pathlib import Path


ORCH = Path(__file__).resolve().parents[1]
ROOT = ORCH.parent
VAULT = Path(
    os.environ.get("ORA_VAULT_PATH")
    or os.environ.get("ORA_VAULT")
    or (Path.home() / "Documents" / "vault")
).resolve()
VAULT_ORA = VAULT / "Projects" / "Ora"

PACKET_DIR = ROOT / "outputs" / "g1-1-phase-3-5"
PACKET = PACKET_DIR / "closeout-evidence.md"
WORKBOOK = ROOT / "outputs" / "g1-1-phase-1-7" / "cash-flow-exception-trial.xlsx"
DESIGN = VAULT_ORA / "Working — Programming Oversight Manager Design.md"
TRACKER = VAULT_ORA / "Working — Ora Setup and Refinement.md"
REGISTRY = VAULT_ORA / "Registry — Ora Overview and Document Registry.md"
TECHNICAL = VAULT_ORA / "Reference — Ora Technical Documentation.md"
TECHNICAL_MIRROR = ROOT / "docs" / "technical-documentation.md"

PROGRAMMING_DIGEST = (
    "sha256:b79d06b401ca54ec62588ab9cd64393fc049d4cf599298a5b057d93aa4e2a927"
)
WORKBOOK_DIGEST = "f84131073851245560d4c29c29c33f2e47cd757c85e175eb7b4eb3ceeafe066e"
SCREENSHOTS = {
    "01-governed-entry.jpg": "ba45c05d59ab3a98c5bf68d8d7c923f1b5df61bb7fb9142b23f4256ff4cd0c24",
    "02-plan-review-principal.jpg": "a8b0322f3074b4a676058e39a53c52b00fced542d73d6ead875cebe0a6d67a29",
    "03-plan-review-technical.jpg": "a7af6026682a8759373232ac1ba4755bfd8991c61438521bae102451189cd54f",
    "04-run-inspector-overview.jpg": "a9fb76295d2924273eb3ec59840f270a2781306fcc8c195f0bd0f76035d70a77",
    "05-run-inspector-evidence.jpg": "ddea775460da41dfa99e7c397ac310a0aaf2d6f7a01f992c4459778be0c1c4ec",
    "06-workspace-surfaces.jpg": "ed62fd2825e8f200ec13a9eaad6d209604d1f6e5d6a74d169da1fdc8a44b0ec3",
    "07-process-library.jpg": "82173acbac77e84911452cc0e73c9ffd71d4c36e32f7ba1d0a125f3f8c67dc22",
}


def body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end < 0:
            raise AssertionError(f"unterminated frontmatter: {path}")
        text = text[end + 5 :]
    return text.lstrip("\n").rstrip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def h3_section(text: str, heading: str) -> str:
    marker = f"### {heading}\n"
    start = text.index(marker)
    end = text.find("\n### ", start + len(marker))
    return text[start:] if end < 0 else text[start:end]


def jpeg_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if not data.startswith(b"\xff\xd8"):
        raise AssertionError(f"not a JPEG: {path}")
    pos = 2
    sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while pos + 4 <= len(data):
        while pos < len(data) and data[pos] != 0xFF:
            pos += 1
        while pos < len(data) and data[pos] == 0xFF:
            pos += 1
        if pos >= len(data):
            break
        marker = data[pos]
        pos += 1
        if marker in {0xD8, 0xD9}:
            continue
        if marker == 0xDA or pos + 2 > len(data):
            break
        length = int.from_bytes(data[pos : pos + 2], "big")
        if marker in sof and pos + 7 <= len(data):
            height = int.from_bytes(data[pos + 3 : pos + 5], "big")
            width = int.from_bytes(data[pos + 5 : pos + 7], "big")
            return width, height
        pos += length
    raise AssertionError(f"JPEG dimensions not found: {path}")


class TestPhase35Closeout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet = PACKET.read_text(encoding="utf-8")
        cls.design = DESIGN.read_text(encoding="utf-8")
        cls.tracker = TRACKER.read_text(encoding="utf-8")
        cls.registry = REGISTRY.read_text(encoding="utf-8")

    def test_packet_is_complete_without_self_issuing_gate_acceptance(self):
        for token in (
            "State: execution evidence complete; independent Gate 3.5 judgment pending",
            "## Candidate salvage disposition",
            "## Trial packets",
            "## Rendered interface manifest",
            "## As-built and documentation set",
            "## Source topology and synchronization",
            "## Regression and integrity matrix",
            "## Deferred beyond G1.1",
            "## Gate boundary",
        ):
            self.assertIn(token, self.packet)
        self.assertNotIn("PENDING_PHASE35_MATRIX", self.packet)
        self.assertNotIn("GATE 3.5 ACCEPTED", self.packet)
        self.assertNotIn("G1.1 is complete", self.packet)

    def test_command_provenance_is_copy_pasteable_and_exit_bound(self):
        blocks = re.findall(r"```sh\n(.*?)\n```", self.packet, flags=re.DOTALL)
        self.assertEqual(len(blocks), 10)
        commands = "\n".join(blocks)

        for heading in (
            "### Execution environment",
            "### Python kernel, trial, interface, and documentation matrix",
            "### Browser DOM matrix",
            "### Python compilation",
            "### Canonical drift",
            "### Artifact integrity",
            "### Repository integrity and synchronization",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, self.packet)

        for token in (
            "cd /Users/oracle/ora-msi-central-routing",
            "export ORA_VAULT_PATH=/Users/oracle/Documents/vault",
            "python3 --version",
            "node --version",
            "python3 -m pytest -q",
            "orchestrator/tests/test_process_contracts.py",
            "orchestrator/tests/test_governed_process_runtime.py",
            "orchestrator/tests/test_phase_1_5_governed_sources.py",
            "orchestrator/tests/test_phase_1_6_programming_definition.py",
            "orchestrator/tests/test_phase_1_7_kernel_trials.py",
            "orchestrator/tests/test_verifier_retry.py",
            "orchestrator/tests/test_execution_loop.py",
            "orchestrator/tests/test_execution_review.py",
            "orchestrator/tests/test_phase_2_1_entry_routing.py",
            "orchestrator/tests/test_phase_2_8_experience_validation.py",
            "orchestrator/tests/test_phase_3_1_as_built_reconciliation.py",
            "orchestrator/tests/test_phase_3_4_maintainer_reference.py",
            "orchestrator/tests/test_phase_3_5_closeout.py",
            "server/static/tests/test-process-entry.js",
            "server/static/tests/test-process-plan-review.js",
            "server/static/tests/test-process-attention.js",
            "server/static/tests/test-process-run-inspector.js",
            "server/static/tests/test-process-surface-boundaries.js",
            "python3 -m py_compile",
            "python3 scripts/verify-implementation.py --check drift",
            "::TestPhase35Closeout::test_rendered_manifest_is_exact_and_images_are_reviewable",
            "git diff --check 6824bb03bf8bf9a94c1e87020c40d7007457608a..HEAD",
            "git diff --check 7675124ec1b2b4ddfd512e901a611ab63224b5bb..HEAD",
            "git diff --name-only 7675124ec1b2b4ddfd512e901a611ab63224b5bb..HEAD",
            "git -C /Users/oracle/Documents/vault diff --check",
            "git -C /Users/oracle/Documents/vault status --short",
            "rev-parse '@{u}'",
        ):
            with self.subTest(command_token=token):
                self.assertIn(token, commands)

        self.assertEqual(self.packet.count("Observed exit status: `0`."), 10)
        for result in (
            "217 passed, 120 subtests passed",
            "213 passed, 63 subtests passed",
            "29 passed, 161 subtests passed",
            "13 passed, 57 subtests passed",
            "21 + 16 + 14 + 24 + 8 = 83 passed",
            "6 passed, 11 subtests passed",
            "both HEADs equal their tracking upstreams",
        ):
            with self.subTest(result=result):
                self.assertIn(result, self.packet)

    def test_immutable_programming_identity_is_consistent(self):
        for text in (self.packet, self.design, self.tracker, self.registry):
            self.assertIn("ora/programming@2.0.1", text)
            self.assertIn(PROGRAMMING_DIGEST, text)
        self.assertEqual(
            body(VAULT_ORA / "Framework — Programming.md"),
            body(ROOT / "frameworks" / "book" / "programming.md"),
        )

    def test_candidate_disposition_rejects_integration_baselines(self):
        for token in (
            "codex/programming-candidate-preservation",
            "`97a8b98e`",
            "codex/programming-candidate-separation",
            "`7d6fc7c2`",
            "never an integration baseline",
            "No dedicated Programming dispatch/compiler/controller/runtime was imported",
            "Concurrent MSI `model_dispatch.py` and `router.py` material remains excluded",
        ):
            self.assertIn(token, self.packet)

    def test_all_four_trial_paths_are_bound(self):
        for token in (
            "TestProgrammingTrial",
            "TestCrossDomainReusableDefinitionTrial",
            "TestProblemEvolutionContingentTrial",
            "test_known_procedure_routes_directly_without_problem_evolution",
            "test_phase_2_8_experience_validation.py",
            "run-management-d816843a71653e1715e45481",
            "mutation was not authorized",
        ):
            self.assertIn(token, self.packet)
        self.assertTrue(WORKBOOK.is_file())
        self.assertEqual(sha256(WORKBOOK), WORKBOOK_DIGEST)

    def test_rendered_manifest_is_exact_and_images_are_reviewable(self):
        actual = {path.name for path in PACKET_DIR.glob("*.jpg")}
        self.assertEqual(actual, set(SCREENSHOTS))
        for name, expected_digest in SCREENSHOTS.items():
            with self.subTest(name=name):
                path = PACKET_DIR / name
                self.assertGreater(path.stat().st_size, 30_000)
                self.assertEqual(sha256(path), expected_digest)
                self.assertEqual(jpeg_size(path), (1280, 720))
                self.assertIn(expected_digest, self.packet)

    def test_four_mirrors_two_direct_and_one_documentation_only_are_preserved(self):
        pairs = (
            ("Framework — Process Inference.md", "process-inference.md"),
            ("Framework — Process Formalization.md", "process-formalization.md"),
            ("Framework — Problem Evolution.md", "problem-evolution.md"),
            ("Specification — F-Quality-Gate.md", "f-quality-gate.md"),
        )
        for canonical_name, mirror_name in pairs:
            with self.subTest(canonical=canonical_name):
                self.assertEqual(
                    body(VAULT_ORA / canonical_name),
                    body(ROOT / "frameworks" / "book" / mirror_name),
                )
        for absent in (
            "process-coherence.md",
            "oversight-configuration.md",
            "meta-layer-architecture.md",
        ):
            self.assertFalse((ROOT / "frameworks" / "book" / absent).exists())
        for token in (
            "four exact canonical/runtime mirror pairs",
            "loaded directly from the vault",
            "registered against the vault canonical",
            "documentation-only",
            "No scheduled synchronization or unnecessary mirror was introduced",
        ):
            self.assertIn(token, self.packet)

    def test_user_and_technical_mirrors_are_body_identical(self):
        self.assertEqual(
            body(VAULT_ORA / "Guide — Using Ora.md"),
            body(ROOT / "docs" / "user-guide.md"),
        )
        self.assertEqual(body(TECHNICAL), body(TECHNICAL_MIRROR))
        technical = body(TECHNICAL)
        self.assertIn("### Phase 3.5 closeout evidence", technical)
        self.assertIn("not a comprehensive cross-platform accessibility certification", technical)

    def test_design_checklist_and_external_gate_acceptance_are_exact(self):
        for token in (
            "Phase 3.4 implementation — COMPLETE; GATE 3.4 ACCEPTED",
            "Phase 3.5 implementation — COMPLETE; GATE 3.5 ACCEPTED",
            "### 29.14 G1.1 closeout evidence — AS BUILT 2026-07-19",
            "- [x] UI screenshots rendered and verified.",
            "- [x] G1.1 exit criteria verified, Gate 3.5 independently accepted, and tracker disposition closed.",
            "The independent judge returned `PASS — ACCEPT` for Gate 3.5",
            "runtime commit `71f0ecf72802a4e54c3a8f2cd12223cf8628e309`",
            "G1.1 is complete",
        ):
            self.assertIn(token, self.design)
        self.assertNotIn("- [ ] UI screenshots rendered and verified.", self.design)
        self.assertNotIn("- [ ] G1.1 exit criteria verified", self.design)
        self.assertNotIn("Phase 3.5 implementation — COMPLETE; PENDING GATE 3.5", self.design)

    def test_tracker_closes_g11_and_advances_only_to_existing_g12_scope(self):
        g11 = self.tracker[
            self.tracker.index("### G1.1 —") : self.tracker.index("\n### G1.2 —")
        ]
        for token in (
            "### G1.1 — Governed process construction and Programming Oversight proof of concept — ✅",
            "completed 2026-07-19 after Parts 1 and 2 plus Phases 3.1–3.5 passed independent judgment",
            "Final disposition:** G1.1 complete",
            "Accepted Phase 3.5 authority boundary",
            "authorized G1.2 under G1.2's existing scope only",
            "G1.2 separately owns the complete Gear 1/2/3 specification",
        ):
            self.assertIn(token, g11)
        for obsolete in (
            "Phase 3.4 current",
            "Current phase:** Part 3, Phase 3.4",
            "Current phase:** Part 3, Phase 3.5",
            "Phase 3.5 remains gated",
            "Phase 3.5 remains unauthorized",
            "pending independent Gate 3.5",
        ):
            self.assertNotIn(obsolete, g11)

    def test_registry_records_gate_3_5_acceptance_and_g11_completion(self):
        technical = h3_section(self.registry, "Reference — Ora Technical Documentation.md")
        tracker = h3_section(self.registry, "Working — Ora Setup and Refinement.md")
        design = h3_section(self.registry, "Working — Programming Oversight Manager Design.md")
        self.assertIn("Gate 3.4 documentation/test acceptance at `6824bb03`", technical)
        self.assertIn("Gate 3.5 passed at runtime closeout commit `71f0ecf7`; G1.1 is complete", technical)
        self.assertIn("G1.1 is complete after independent Gate 3.5 acceptance", tracker)
        self.assertIn(
            "G1.18’s bounded correction is implemented and awaits independent re-judgment",
            tracker,
        )
        self.assertIn("G1.3, and G1.7 are user-deferred", tracker)
        self.assertIn("Parts 1 and 2 plus Phases 3.1–3.5 are accepted", design)
        self.assertIn("G1.1 is complete", design)
        current = "\n".join((technical, tracker, design))
        for obsolete in (
            "Phase 3.4 is complete pending Gate 3.4",
            "Phase 3.5 remains unauthorized",
            "Screenshot and final closeout sections remain explicitly unimplemented",
            "Phase 3.5 evidence is complete pending Gate 3.5",
            "pending independent Gate 3.5",
        ):
            self.assertNotIn(obsolete, current)

    def test_closeout_deferrals_preserve_adjacent_ownership(self):
        for token in (
            "G1.2's full Gear 1/2/3 specification",
            "Windows/Linux portability",
            "Broad standing-trigger management",
            "external-effect or complex-entry graphs",
            "active-Run pause/stop/resume/reopen",
            "general in-place state migration engine",
            "assistive-technology and cross-platform visual certification",
            "Marketplace, analytics, automatic optimization",
        ):
            self.assertIn(token, self.packet)

    def test_temporary_visual_fixture_is_not_release_state(self):
        for path in (
            ROOT / "sessions" / "g11-phase35-interface-evidence",
            ROOT / "sessions" / "thread-20260720-004435-ovas59",
            ROOT / "data" / "process-runs" / "id-0da66b9a2380e4912837b059",
            ROOT / "data" / "pipeline-traces" / "thread-20260720-004435-ovas59",
        ):
            self.assertFalse(path.exists(), str(path))


if __name__ == "__main__":
    unittest.main()
