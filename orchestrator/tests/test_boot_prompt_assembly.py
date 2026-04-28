#!/usr/bin/env python3
"""
WP-4.1 — Prompt assembly for the rebuilt mode files.

Confirms ``build_system_prompt_for_gear`` extracts the new
``EMISSION CONTRACT`` and ``SUCCESS CRITERIA`` sections added during the
Phase 1-3 mode-specification rebuild. Before Phase 4, the function only
extracted DEPTH/BREADTH MODEL INSTRUCTIONS / CONTENT CONTRACT /
GUARD RAILS; the two new sections were silently dropped, so the rebuilt
mode files had no effect on live behaviour.

The tests load a representative rebuilt mode (``root-cause-analysis``),
assemble the prompt, and assert the new sections appear verbatim in the
output alongside the pre-existing ones. A companion negative-path test
loads ``spatial-reasoning`` (preserved reference, does have EMISSION
CONTRACT but no SUCCESS CRITERIA) and confirms the extractor is tolerant
of the section-absent case.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
WORKSPACE = ORCHESTRATOR.parent
sys.path.insert(0, str(ORCHESTRATOR))

MODES_DIR = WORKSPACE / "modes"


def _context_package(mode_name: str) -> dict:
    """Build the minimum context package ``build_system_prompt_for_gear``
    requires. The function only reads three fields from the package:
    ``mode_text``, ``mode_name``, and the optional RAG fields. We zero out
    the RAG fields to isolate the mode-file extraction under test.
    """
    mode_text = (MODES_DIR / f"{mode_name}.md").read_text()
    return {
        "mode_text": mode_text,
        "mode_name": mode_name,
        "conversation_rag": "",
        "concept_rag": "",
        "relationship_rag": "",
        "rag_utilization": "",
    }


class TestBuildSystemPromptForGear(unittest.TestCase):
    """WP-4.1 — extraction of EMISSION CONTRACT + SUCCESS CRITERIA."""

    def test_rebuilt_mode_includes_emission_contract(self) -> None:
        from boot import build_system_prompt_for_gear
        prompt = build_system_prompt_for_gear(
            _context_package("root-cause-analysis"), slot="breadth"
        )
        self.assertIn("## EMISSION CONTRACT", prompt,
                      "rebuilt mode prompt should include EMISSION CONTRACT heading")
        # Canonical envelope is embedded in that section — one distinctive
        # marker is enough to confirm the section body was extracted.
        self.assertIn('"type": "fishbone"', prompt,
                      "EMISSION CONTRACT body (canonical envelope) should be present")
        self.assertIn("Envelope type selection", prompt,
                      "EMISSION CONTRACT body (selection rule) should be present")

    def test_rebuilt_mode_includes_success_criteria(self) -> None:
        from boot import build_system_prompt_for_gear
        prompt = build_system_prompt_for_gear(
            _context_package("root-cause-analysis"), slot="breadth"
        )
        self.assertIn("## SUCCESS CRITERIA", prompt,
                      "rebuilt mode prompt should include SUCCESS CRITERIA heading")
        self.assertIn("Structural (machine-checkable)", prompt,
                      "SUCCESS CRITERIA body should list Structural criteria")
        self.assertIn("S1 — Envelope presence", prompt,
                      "SUCCESS CRITERIA should surface individual criterion IDs")
        self.assertIn("success_criteria:", prompt,
                      "SUCCESS CRITERIA should surface the machine-readable YAML tag")

    def test_existing_sections_still_extracted(self) -> None:
        """Regression guard — the Phase 4 addition must not drop the
        pre-existing four sections."""
        from boot import build_system_prompt_for_gear
        prompt = build_system_prompt_for_gear(
            _context_package("root-cause-analysis"), slot="breadth"
        )
        self.assertIn(
            "## MODE INSTRUCTIONS — root-cause-analysis", prompt,
            "mode-instructions heading (depth/breadth dispatch) is load-bearing"
        )
        self.assertIn("## CONTENT CONTRACT", prompt)
        self.assertIn("## GUARD RAILS", prompt)

    def test_depth_slot_extracts_depth_instructions(self) -> None:
        """Ensure the slot argument still governs which instruction block
        ships to the model, post-Phase-4 edit."""
        from boot import build_system_prompt_for_gear
        depth_prompt = build_system_prompt_for_gear(
            _context_package("root-cause-analysis"), slot="depth"
        )
        breadth_prompt = build_system_prompt_for_gear(
            _context_package("root-cause-analysis"), slot="breadth"
        )
        self.assertIn("White Hat", depth_prompt)
        self.assertIn("Green Hat", breadth_prompt)

    def test_mode_without_success_criteria_is_tolerated(self) -> None:
        """``spatial-reasoning`` (reference) lacks SUCCESS CRITERIA; the
        extractor must silently omit the heading rather than crash."""
        from boot import build_system_prompt_for_gear
        prompt = build_system_prompt_for_gear(
            _context_package("spatial-reasoning"), slot="breadth"
        )
        # The reference file does carry EMISSION CONTRACT, so we expect
        # that heading to appear.
        self.assertIn("## EMISSION CONTRACT", prompt)
        # SUCCESS CRITERIA: absent from spatial-reasoning pre-Phase-4 —
        # assembly must still complete without raising.
        # (We do not assert its absence, since a future pass might add it.)

    def test_phase4_additions_ordered_after_guard_rails_siblings(self) -> None:
        """Ordering guard — EMISSION CONTRACT + SUCCESS CRITERIA sit
        between CONTENT CONTRACT and GUARD RAILS so the model reads the
        positive output spec before the negative guard list."""
        from boot import build_system_prompt_for_gear
        prompt = build_system_prompt_for_gear(
            _context_package("root-cause-analysis"), slot="breadth"
        )
        idx_cc = prompt.index("## CONTENT CONTRACT")
        idx_ec = prompt.index("## EMISSION CONTRACT")
        idx_sc = prompt.index("## SUCCESS CRITERIA")
        idx_gr = prompt.index("## GUARD RAILS")
        self.assertLess(idx_cc, idx_ec)
        self.assertLess(idx_ec, idx_sc)
        self.assertLess(idx_sc, idx_gr)


class TestExtractHelpers(unittest.TestCase):
    """Phase 5 WP-5.3 — the ``_extract_section`` / ``_extract_subsection``
    module-level helpers underpinning the per-step dispatch."""

    def test_extract_section_returns_body_stripped(self) -> None:
        from boot import _extract_section
        text = (
            "# Title\n\n"
            "## SUCCESS CRITERIA\n\n"
            "Body line 1.\n"
            "Body line 2.\n\n"
            "## KNOWN FAILURE MODES\n\n"
            "After.\n"
        )
        self.assertEqual(
            _extract_section(text, "SUCCESS CRITERIA"),
            "Body line 1.\nBody line 2."
        )

    def test_extract_section_absent_returns_empty(self) -> None:
        from boot import _extract_section
        self.assertEqual(_extract_section("# Nothing here", "SUCCESS CRITERIA"), "")

    def test_extract_subsection_nested_inside_parent(self) -> None:
        from boot import _extract_subsection
        text = (
            "## EVALUATION CRITERIA\n\n"
            "Prose before subsections.\n\n"
            "### Focus for this mode\n\n"
            "Focus body.\n\n"
            "### Suggestion templates per criterion\n\n"
            "Templates body.\n\n"
            "## KNOWN FAILURE MODES\n\n"
            "Next section.\n"
        )
        self.assertEqual(
            _extract_subsection(text, "EVALUATION CRITERIA", "Focus for this mode"),
            "Focus body."
        )
        self.assertEqual(
            _extract_subsection(
                text, "EVALUATION CRITERIA", "Suggestion templates per criterion"
            ),
            "Templates body."
        )

    def test_extract_subsection_respects_section_boundary(self) -> None:
        """A ### that exists outside the named ## parent must not match."""
        from boot import _extract_subsection
        text = (
            "## OTHER SECTION\n\n"
            "### Focus for this mode\n\n"
            "Should NOT match — this subsection sits under a different parent.\n\n"
            "## EVALUATION CRITERIA\n\n"
            "Prose only here.\n"
        )
        self.assertEqual(
            _extract_subsection(text, "EVALUATION CRITERIA", "Focus for this mode"),
            ""
        )

    def test_extract_subsection_absent_returns_empty(self) -> None:
        from boot import _extract_subsection
        text = (
            "## EVALUATION CRITERIA\n\n"
            "No subsections here.\n"
        )
        self.assertEqual(
            _extract_subsection(text, "EVALUATION CRITERIA", "Focus for this mode"),
            ""
        )

    def test_extract_subsection_stops_at_sibling_subsection(self) -> None:
        """A ### body must not spill into the next ### sibling."""
        from boot import _extract_subsection
        text = (
            "## EVALUATION CRITERIA\n\n"
            "### Focus for this mode\n\n"
            "Focus body only.\n\n"
            "### Suggestion templates per criterion\n\n"
            "Templates body — must not be returned for Focus.\n"
        )
        self.assertEqual(
            _extract_subsection(text, "EVALUATION CRITERIA", "Focus for this mode"),
            "Focus body only."
        )


class TestRealModeSubsectionsExtractable(unittest.TestCase):
    """Phase 5 WP-5.3 — confirm every required subsection is extractable
    from every rebuilt mode file. This is the acceptance test for the
    WP-5.2 authoring sweep: 20 modes × 8 subsections = 160 non-empty
    extractions."""

    REQUIRED_SUBSECTIONS = (
        ("DEPTH MODEL INSTRUCTIONS", "Cascade — what to leave for the evaluator"),
        ("DEPTH MODEL INSTRUCTIONS", "Consolidator guidance"),
        ("BREADTH MODEL INSTRUCTIONS", "Cascade — what to leave for the evaluator"),
        ("EVALUATION CRITERIA", "Focus for this mode"),
        ("EVALUATION CRITERIA", "Suggestion templates per criterion"),
        ("EVALUATION CRITERIA", "Known failure modes to call out"),
        ("EVALUATION CRITERIA", "Verifier checks for this mode"),
        ("CONTENT CONTRACT", "Reviser guidance per criterion"),
    )

    REBUILT_MODES = [
        "benefits-analysis", "competing-hypotheses", "consequences-and-sequel",
        "constraint-mapping", "cui-bono", "decision-under-uncertainty",
        "deep-clarification", "dialectical-analysis", "paradigm-suspension",
        "passion-exploration", "project-mode", "relationship-mapping",
        "root-cause-analysis", "scenario-planning", "steelman-construction",
        "strategic-interaction", "structured-output", "synthesis",
        "systems-dynamics", "terrain-mapping",
    ]

    def test_every_rebuilt_mode_carries_every_subsection(self) -> None:
        from boot import _extract_subsection
        missing: list[str] = []
        for mode in self.REBUILT_MODES:
            mode_text = (MODES_DIR / f"{mode}.md").read_text()
            for parent, sub in self.REQUIRED_SUBSECTIONS:
                body = _extract_subsection(mode_text, parent, sub)
                if not body:
                    missing.append(f"{mode} / {parent} / {sub}")
        self.assertEqual(
            missing, [],
            f"{len(missing)} subsection(s) missing or empty across "
            f"{len(self.REBUILT_MODES)} modes"
        )

    def test_spatial_reasoning_deliberately_excluded(self) -> None:
        """``spatial-reasoning.md`` is the reference file, preserved
        unchanged. It is NOT expected to carry Phase 5 subsections; this
        test documents that intentional exclusion."""
        self.assertNotIn("spatial-reasoning", self.REBUILT_MODES)


class TestPerStepPromptDispatch(unittest.TestCase):
    """Phase 5 WP-5.3 — build_system_prompt_for_gear dispatches by pipeline
    step. Each step's prompt contains the subsections the step needs and
    does NOT contain subsections that belong to a different step."""

    def setUp(self) -> None:
        self.ctx = _context_package("root-cause-analysis")

    def test_analyst_default_step_matches_pre_phase5_shape(self) -> None:
        """Omitting the step argument must preserve Phase 4 behaviour."""
        from boot import build_system_prompt_for_gear
        with_step = build_system_prompt_for_gear(self.ctx, slot="breadth", step="analyst")
        without_step = build_system_prompt_for_gear(self.ctx, slot="breadth")
        self.assertEqual(with_step, without_step)

    def test_unknown_step_raises(self) -> None:
        from boot import build_system_prompt_for_gear
        with self.assertRaises(ValueError):
            build_system_prompt_for_gear(self.ctx, slot="breadth", step="nonsense")

    # Helpers: each step injects the mode's subsection as a *top-level*
    # ``## MODE — <mode> — <subsection-label>`` heading (distinct from the
    # same label when it lives as a ``###`` subsection nested inside a
    # parent section such as CONTENT CONTRACT or EVALUATION CRITERIA).
    # Absence-of-top-level-injection is how we confirm that step X's
    # distinctive subsection does not escape to step Y.

    @staticmethod
    def _has_top_level_injection(prompt: str, mode: str, label: str) -> bool:
        header = f"## MODE — {mode} — {label}"
        return header in prompt

    def test_evaluator_step_contains_focus_and_templates_and_known_failures(self) -> None:
        from boot import build_system_prompt_for_gear
        prompt = build_system_prompt_for_gear(self.ctx, slot="breadth", step="evaluator")
        self.assertTrue(self._has_top_level_injection(
            prompt, "root-cause-analysis", "Focus for this mode"))
        self.assertTrue(self._has_top_level_injection(
            prompt, "root-cause-analysis", "Suggestion templates per criterion"))
        self.assertTrue(self._has_top_level_injection(
            prompt, "root-cause-analysis", "Known failure modes to call out"))
        self.assertIn("SUCCESS CRITERIA (criteria to evaluate against)", prompt)
        self.assertIn("EMISSION CONTRACT (analyst's target)", prompt)
        # Evaluator must NOT receive the reviser / verifier / consolidator
        # subsections as top-level injections (nested-inside-parent
        # occurrences are OK — the whole CONTENT CONTRACT is intentionally
        # shipped as reference, and it carries its own ### subsections).
        self.assertFalse(self._has_top_level_injection(
            prompt, "root-cause-analysis", "Reviser guidance per criterion"))
        self.assertFalse(self._has_top_level_injection(
            prompt, "root-cause-analysis", "Verifier checks for this mode"))
        self.assertFalse(self._has_top_level_injection(
            prompt, "root-cause-analysis", "Consolidator guidance"))

    def test_reviser_step_contains_reviser_guidance(self) -> None:
        from boot import build_system_prompt_for_gear
        prompt = build_system_prompt_for_gear(self.ctx, slot="breadth", step="reviser")
        self.assertTrue(self._has_top_level_injection(
            prompt, "root-cause-analysis", "Reviser guidance per criterion"))
        self.assertIn("CONTENT CONTRACT (must be preserved)", prompt)
        self.assertIn("SUCCESS CRITERIA (revision must meet)", prompt)
        self.assertIn("## GUARD RAILS", prompt)
        # Reviser must NOT receive evaluator / verifier / consolidator
        # subsections as top-level injections.
        self.assertFalse(self._has_top_level_injection(
            prompt, "root-cause-analysis", "Focus for this mode"))
        self.assertFalse(self._has_top_level_injection(
            prompt, "root-cause-analysis", "Suggestion templates per criterion"))
        self.assertFalse(self._has_top_level_injection(
            prompt, "root-cause-analysis", "Known failure modes to call out"))
        self.assertFalse(self._has_top_level_injection(
            prompt, "root-cause-analysis", "Verifier checks for this mode"))
        self.assertFalse(self._has_top_level_injection(
            prompt, "root-cause-analysis", "Consolidator guidance"))

    def test_verifier_step_contains_verifier_checks(self) -> None:
        from boot import build_system_prompt_for_gear
        prompt = build_system_prompt_for_gear(self.ctx, slot="breadth", step="verifier")
        self.assertTrue(self._has_top_level_injection(
            prompt, "root-cause-analysis", "Verifier checks for this mode"))
        self.assertIn("SUCCESS CRITERIA (floor for verification)", prompt)
        self.assertIn("EMISSION CONTRACT (reference)", prompt)
        self.assertIn("CONTENT CONTRACT (reference)", prompt)
        self.assertFalse(self._has_top_level_injection(
            prompt, "root-cause-analysis", "Focus for this mode"))
        self.assertFalse(self._has_top_level_injection(
            prompt, "root-cause-analysis", "Reviser guidance per criterion"))
        self.assertFalse(self._has_top_level_injection(
            prompt, "root-cause-analysis", "Consolidator guidance"))

    def test_consolidator_step_contains_consolidator_guidance(self) -> None:
        # Use systems-dynamics (Gear 4) where consolidator guidance is
        # substantive rather than a "not applicable" note.
        from boot import build_system_prompt_for_gear
        ctx_sd = _context_package("systems-dynamics")
        prompt = build_system_prompt_for_gear(ctx_sd, slot="breadth", step="consolidator")
        self.assertTrue(self._has_top_level_injection(
            prompt, "systems-dynamics", "Consolidator guidance"))
        self.assertIn("CONTENT CONTRACT (target for consolidated output)", prompt)
        self.assertIn("EMISSION CONTRACT (target for consolidated output)", prompt)
        self.assertIn("SUCCESS CRITERIA (target for consolidated output)", prompt)
        self.assertFalse(self._has_top_level_injection(
            prompt, "systems-dynamics", "Focus for this mode"))
        self.assertFalse(self._has_top_level_injection(
            prompt, "systems-dynamics", "Reviser guidance per criterion"))
        self.assertFalse(self._has_top_level_injection(
            prompt, "systems-dynamics", "Verifier checks for this mode"))

    def test_analyst_step_carries_spatial_state_gating(self) -> None:
        """The spatial / vision / image inputs belong only to the analyst step —
        they describe the user's drawn inputs, not the analyst's output. Other
        steps must not see them even when the context package carries them."""
        from boot import build_system_prompt_for_gear
        ctx = dict(self.ctx)
        ctx["spatial_representation"] = {
            "entities": [{"id": "E1", "label": "User box", "bbox": [0, 0, 100, 100]}],
            "relationships": [],
            "annotations_on_canvas": [],
        }
        analyst_prompt = build_system_prompt_for_gear(ctx, slot="breadth", step="analyst")
        evaluator_prompt = build_system_prompt_for_gear(ctx, slot="breadth", step="evaluator")
        # Analyst sees the spatial input fence; evaluator does not.
        self.assertIn("USER SPATIAL INPUT", analyst_prompt)
        self.assertNotIn("USER SPATIAL INPUT", evaluator_prompt)

    def test_consolidator_gear3_mode_carries_not_applicable_note(self) -> None:
        """For Gear 1-3 modes, the consolidator subsection is a 'not applicable
        at this mode's default gear' note — it still extracts and ships as
        instructions so the extractor remains uniform."""
        from boot import build_system_prompt_for_gear
        ctx = _context_package("root-cause-analysis")  # Gear 3
        prompt = build_system_prompt_for_gear(ctx, slot="breadth", step="consolidator")
        self.assertIn("Consolidator guidance", prompt)
        self.assertIn("Not applicable at this mode's default gear", prompt)


class TestPhase6GearHelpers(unittest.TestCase):
    """Phase 6 — ``_assemble_step_prompt``, ``_rag_tail``, and
    ``_verifier_passed`` underpin the refactored ``run_gear3`` /
    ``run_gear4``. These tests cover the helpers directly; the pipeline
    functions themselves require network calls and are exercised via
    the live cascade tests in test_mode_emission.py."""

    def setUp(self) -> None:
        self.ctx = _context_package("root-cause-analysis")

    def test_rag_tail_empty_when_no_rag_fields(self) -> None:
        from boot import _rag_tail
        ctx = {"conversation_rag": "", "concept_rag": ""}
        self.assertEqual(_rag_tail(ctx), "")

    def test_rag_tail_includes_conversation_and_concept(self) -> None:
        from boot import _rag_tail
        ctx = {
            "conversation_rag": "prior turn context",
            "concept_rag": "mental models retrieved",
        }
        tail = _rag_tail(ctx)
        self.assertIn("## CONVERSATION CONTEXT", tail)
        self.assertIn("prior turn context", tail)
        self.assertIn("## KNOWLEDGE CONTEXT", tail)
        self.assertIn("mental models retrieved", tail)

    def test_rag_tail_skips_empty_individual_fields(self) -> None:
        from boot import _rag_tail
        ctx = {"conversation_rag": "only conv", "concept_rag": ""}
        tail = _rag_tail(ctx)
        self.assertIn("## CONVERSATION CONTEXT", tail)
        self.assertNotIn("## KNOWLEDGE CONTEXT", tail)

    def test_assemble_step_analyst_omits_framework(self) -> None:
        """The analyst step has no F-* universal scaffolding — the mode
        file's DEPTH/BREADTH MODEL INSTRUCTIONS replace F-ANALYSIS-* per
        Phase 5."""
        from boot import _assemble_step_prompt
        prompt = _assemble_step_prompt(
            self.ctx, slot="depth", step="analyst", framework_name=None
        )
        self.assertIn("MODE INSTRUCTIONS", prompt)
        self.assertNotIn("F-* UNIVERSAL SCAFFOLDING", prompt)

    def test_assemble_step_evaluator_attaches_f_evaluate(self) -> None:
        from boot import _assemble_step_prompt
        prompt = _assemble_step_prompt(
            self.ctx, slot="depth", step="evaluator",
            framework_name="f-evaluate.md"
        )
        self.assertIn("F-* UNIVERSAL SCAFFOLDING — f-evaluate.md", prompt)
        self.assertIn("Focus for this mode", prompt)

    def test_assemble_step_reviser_attaches_f_revise(self) -> None:
        from boot import _assemble_step_prompt
        prompt = _assemble_step_prompt(
            self.ctx, slot="depth", step="reviser",
            framework_name="f-revise.md"
        )
        self.assertIn("F-* UNIVERSAL SCAFFOLDING — f-revise.md", prompt)
        self.assertIn("Reviser guidance per criterion", prompt)

    def test_assemble_step_verifier_attaches_f_verify(self) -> None:
        from boot import _assemble_step_prompt
        prompt = _assemble_step_prompt(
            self.ctx, slot="depth", step="verifier",
            framework_name="f-verify.md"
        )
        self.assertIn("F-* UNIVERSAL SCAFFOLDING — f-verify.md", prompt)
        self.assertIn("Verifier checks for this mode", prompt)

    def test_assemble_step_consolidator_attaches_f_consolidate(self) -> None:
        from boot import _assemble_step_prompt
        ctx = _context_package("systems-dynamics")  # Gear 4 mode
        prompt = _assemble_step_prompt(
            ctx, slot="breadth", step="consolidator",
            framework_name="f-consolidate.md"
        )
        self.assertIn("F-* UNIVERSAL SCAFFOLDING — f-consolidate.md", prompt)
        self.assertIn("Consolidator guidance", prompt)

    def test_assemble_step_appends_rag_tail(self) -> None:
        from boot import _assemble_step_prompt
        ctx = dict(self.ctx)
        ctx["conversation_rag"] = "PRIOR"
        ctx["concept_rag"] = "MODELS"
        prompt = _assemble_step_prompt(
            ctx, slot="depth", step="analyst", framework_name=None
        )
        idx_mode = prompt.index("MODE INSTRUCTIONS")
        idx_conv = prompt.index("CONVERSATION CONTEXT")
        self.assertLess(idx_mode, idx_conv,
                        "RAG tail must sit after the step prompt")

    def test_verifier_passed_detects_plain_verified(self) -> None:
        from boot import _verifier_passed
        self.assertTrue(_verifier_passed(
            "Status: VERIFIED — all checks pass."))

    def test_verifier_passed_detects_verified_with_corrections(self) -> None:
        from boot import _verifier_passed
        self.assertTrue(_verifier_passed(
            "VERIFIED WITH CORRECTIONS — short_alt trimmed inline."))

    def test_verifier_passed_rejects_verification_failed(self) -> None:
        from boot import _verifier_passed
        self.assertFalse(_verifier_passed(
            "VERIFICATION FAILED — the envelope was absent."))

    def test_verifier_passed_rejects_mixed_token(self) -> None:
        """A response containing both 'VERIFIED' and 'VERIFICATION FAILED'
        (e.g. the verifier discusses one check that verified, then
        another that failed) must be read as overall fail."""
        from boot import _verifier_passed
        self.assertFalse(_verifier_passed(
            "V1 VERIFIED. V4 VERIFICATION FAILED — depth floor regressed."))

    def test_verifier_passed_rejects_no_token(self) -> None:
        from boot import _verifier_passed
        self.assertFalse(_verifier_passed("The analysis looks okay to me."))


if __name__ == "__main__":
    unittest.main()
