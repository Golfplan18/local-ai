#!/usr/bin/env python3
"""Tests for boot.build_system_prompt_for_gear under the locked mode template.

The mode template was locked 2026-05-01 with a flat-H2 structure: one ##
section per pipeline step (DEPTH ANALYSIS GUIDANCE, BREADTH ANALYSIS
GUIDANCE, EVALUATION CRITERIA, REVISION GUIDANCE, CONSOLIDATION GUIDANCE,
VERIFICATION CRITERIA). build_system_prompt_for_gear dispatches each
pipeline step to its matching section.

The prior cascade-architecture test suite (test_mode_emission.py,
test_boot_prompt_assembly.py, test_mode_success_criteria.py — all
deleted) asserted on the pre-2026-05-01 section names. These tests
replace that suite with a minimal load-bearing check: that each
pipeline step's prompt contains substantive mode-specific content from
the matching section of the mode file.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
REPO_ROOT = ORCHESTRATOR.parent
sys.path.insert(0, str(ORCHESTRATOR))

from boot import (  # noqa: E402
    build_system_prompt_for_gear,
    _extract_section,
    _extract_boot_behavioral_preamble,
)


def _load_mode(name: str) -> str:
    return (REPO_ROOT / "modes" / f"{name}.md").read_text()


def _ctx(mode_name: str) -> dict:
    return {
        "mode_text": _load_mode(mode_name),
        "mode_name": mode_name,
        "conversation_rag": "",
        "concept_rag": "",
        "relationship_rag": "",
    }


class PerStepDispatch(unittest.TestCase):
    """Each step's prompt must include the body of its mapped section."""

    MODE = "root-cause-analysis"

    def _prompt(self, step: str, slot: str = "breadth") -> str:
        return build_system_prompt_for_gear(_ctx(self.MODE), slot=slot, step=step)

    def _section_body(self, name: str) -> str:
        return _extract_section(_load_mode(self.MODE), name)

    def test_analyst_depth_includes_depth_analysis_guidance(self):
        body = self._section_body("DEPTH ANALYSIS GUIDANCE")
        self.assertTrue(body, "fixture missing DEPTH ANALYSIS GUIDANCE")
        prompt = self._prompt("analyst", slot="depth")
        self.assertIn(body.strip(), prompt)

    def test_analyst_breadth_includes_breadth_analysis_guidance(self):
        body = self._section_body("BREADTH ANALYSIS GUIDANCE")
        self.assertTrue(body, "fixture missing BREADTH ANALYSIS GUIDANCE")
        prompt = self._prompt("analyst", slot="breadth")
        self.assertIn(body.strip(), prompt)

    def test_evaluator_includes_evaluation_criteria(self):
        body = self._section_body("EVALUATION CRITERIA")
        self.assertTrue(body, "fixture missing EVALUATION CRITERIA")
        prompt = self._prompt("evaluator")
        self.assertIn(body.strip(), prompt)

    def test_reviser_includes_revision_guidance(self):
        body = self._section_body("REVISION GUIDANCE")
        self.assertTrue(body, "fixture missing REVISION GUIDANCE")
        prompt = self._prompt("reviser")
        self.assertIn(body.strip(), prompt)

    def test_verifier_includes_verification_criteria(self):
        body = self._section_body("VERIFICATION CRITERIA")
        self.assertTrue(body, "fixture missing VERIFICATION CRITERIA")
        prompt = self._prompt("verifier")
        self.assertIn(body.strip(), prompt)

    def test_consolidator_includes_consolidation_guidance(self):
        body = self._section_body("CONSOLIDATION GUIDANCE")
        self.assertTrue(body, "fixture missing CONSOLIDATION GUIDANCE")
        prompt = self._prompt("consolidator")
        self.assertIn(body.strip(), prompt)

    def test_each_step_omits_other_steps_section_bodies(self):
        # The dispatch should ONLY include the section for the active step,
        # not bleed in guidance for other steps. Verifier should not see
        # the consolidation guidance, etc.
        step_to_section = {
            "analyst":      "DEPTH ANALYSIS GUIDANCE",
            "evaluator":    "EVALUATION CRITERIA",
            "reviser":      "REVISION GUIDANCE",
            "verifier":     "VERIFICATION CRITERIA",
            "consolidator": "CONSOLIDATION GUIDANCE",
        }
        for active, own_section in step_to_section.items():
            slot = "depth" if active == "analyst" else "breadth"
            prompt = self._prompt(active, slot=slot)
            for other_step, other_section in step_to_section.items():
                if other_step == active:
                    continue
                # Skip analyst's mirror — breadth analyst sees breadth, not
                # depth, but the dispatch above already requested depth.
                if active == "analyst" and other_step == "analyst":
                    continue
                other_body = self._section_body(other_section)
                self.assertNotIn(
                    other_body.strip(),
                    prompt,
                    f"step={active!r} prompt unexpectedly contains "
                    f"the body of {other_section} (belongs to {other_step})",
                )


class UnknownStepRaises(unittest.TestCase):
    def test_unknown_step_rejected(self):
        with self.assertRaises(ValueError):
            build_system_prompt_for_gear(_ctx("root-cause-analysis"), step="nonsense")


class BootMdAlwaysFirst(unittest.TestCase):
    """The behavioral subset of boot.md leads every pipeline-step prompt.

    Pipeline steps receive a trimmed subset of boot.md (constitution +
    anti-sycophancy + hat assignments + universal anti-confabulation) via
    `_extract_boot_behavioral_preamble`, not the full file. The architectural
    sections (mode registry, models, tools, pipeline, etc.) are stripped
    because a dispatched pipeline step doesn't need them. The behavioral
    preamble must still lead every step's prompt.
    """

    def test_boot_behavioral_preamble_leads_every_step(self):
        from boot import load_boot_md
        boot_md = load_boot_md()
        preamble = _extract_boot_behavioral_preamble(boot_md)
        self.assertTrue(preamble, "behavioral preamble unexpectedly empty")
        for step in ("analyst", "evaluator", "reviser", "verifier", "consolidator"):
            prompt = build_system_prompt_for_gear(_ctx("root-cause-analysis"), step=step)
            self.assertTrue(
                prompt.startswith(preamble),
                f"step={step!r}: prompt does not start with the boot.md "
                f"behavioral preamble",
            )


class AllModeFilesProduceNonEmptyPromptsAcrossSteps(unittest.TestCase):
    """Catch the regression where the dispatch finds no matching section
    and silently returns boot.md + RAG only. Every mode + step should
    contribute at least one mode-specific block."""

    def test_every_mode_file_contributes_mode_content_at_every_step(self):
        import os
        from boot import load_boot_md
        boot_md = load_boot_md()
        preamble = _extract_boot_behavioral_preamble(boot_md)
        modes_dir = REPO_ROOT / "modes"
        mode_files = sorted(f for f in os.listdir(modes_dir) if f.endswith(".md"))
        self.assertGreater(len(mode_files), 0, "no mode files found")
        failures = []
        for fname in mode_files:
            name = fname.replace(".md", "")
            for step in ("analyst", "evaluator", "reviser", "verifier", "consolidator"):
                slot = "depth" if step == "analyst" else "breadth"
                prompt = build_system_prompt_for_gear(_ctx(name), slot=slot, step=step)
                # Strip the behavioral preamble to inspect what mode content
                # the dispatch added.
                tail = prompt[len(preamble):] if prompt.startswith(preamble) else prompt
                if len(tail.strip()) < 50:
                    failures.append(f"{name}/{step}: prompt tail only {len(tail.strip())} chars")
        self.assertFalse(
            failures,
            f"{len(failures)} mode/step combinations produced near-empty prompts:\n  "
            + "\n  ".join(failures[:20])
        )


if __name__ == "__main__":
    unittest.main()
