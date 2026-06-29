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
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
REPO_ROOT = ORCHESTRATOR.parent
sys.path.insert(0, str(ORCHESTRATOR))

from boot import (  # noqa: E402
    build_system_prompt_for_gear,
    _extract_section,
    _extract_boot_behavioral_preamble,
    _build_rag_selection,
)


def _load_mode(name: str) -> str:
    return (REPO_ROOT / "modes" / f"{name}.md").read_text()


def _is_mode_file(fname: str) -> bool:
    """True for real mode files, False for the mode INDEX and any other
    non-mode doc dropped into modes/.

    Real modes declare ``type: mode`` in their YAML frontmatter. modes/INDEX.md
    is the mode index (``type: reference``) — it carries none of the per-step
    guidance sections, so build_system_prompt_for_gear produces an empty
    prompt tail for it. Iterating modes/ blind would flag that empty tail as a
    regression.
    """
    head = (REPO_ROOT / "modes" / fname).read_text()[:800]
    return any(line.strip() == "type: mode" for line in head.splitlines())


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
        # The mode section was renamed "EVALUATION CRITERIA" ->
        # "ANALYTICAL BRIEF AND EVALUATION CRITERIA" on 2026-05-24 (it now
        # absorbs the brief alongside the criteria). build_system_prompt_for_gear
        # injects this bundle as BASELINE for every step, so the evaluator
        # prompt carries it.
        body = self._section_body("ANALYTICAL BRIEF AND EVALUATION CRITERIA")
        self.assertTrue(body, "fixture missing ANALYTICAL BRIEF AND EVALUATION CRITERIA")
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
        # The dispatch layers each step's OWN role-specific guidance on top of
        # a shared baseline. Only the role-specific sections are step-exclusive
        # and must not bleed across steps: DEPTH/BREADTH ANALYSIS GUIDANCE
        # (analyst), REVISION GUIDANCE (reviser), CONSOLIDATION GUIDANCE
        # (consolidator). The evaluator and verifier add no role-specific
        # section of their own — their framing is the universal f-evaluate /
        # f-verify scaffolding plus the baseline.
        #
        # NOTE: the BRIEF + EVALUATION CRITERIA bundle and VERIFICATION
        # CRITERIA are deliberately NOT step-exclusive — boot.py injects them
        # as BASELINE for every pipeline step ("Baseline criteria injection
        # (2026-05-24)") so the analyst writes to the same standard the
        # evaluator and verifier grade against. They are excluded from this
        # cross-bleed check.
        exclusive_owner = {
            "DEPTH ANALYSIS GUIDANCE":   "analyst",
            "REVISION GUIDANCE":         "reviser",
            "CONSOLIDATION GUIDANCE":    "consolidator",
        }
        for active in ("analyst", "evaluator", "reviser", "verifier", "consolidator"):
            # analyst is dispatched in the depth slot, so it owns DEPTH (not
            # BREADTH) ANALYSIS GUIDANCE for this check.
            slot = "depth" if active == "analyst" else "breadth"
            prompt = self._prompt(active, slot=slot)
            for section, owner in exclusive_owner.items():
                if owner == active:
                    continue
                body = self._section_body(section)
                self.assertTrue(body, f"fixture missing {section}")
                self.assertNotIn(
                    body.strip(),
                    prompt,
                    f"step={active!r} prompt unexpectedly contains "
                    f"the body of {section} (belongs to {owner})",
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


class RagSelectionDefaults(unittest.TestCase):
    """RAG selection is a safety layer and should be default-on unless an
    operator explicitly disables it for debugging."""

    def setUp(self):
        self._old = os.environ.get("ORA_RAG_SELECTION")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("ORA_RAG_SELECTION", None)
        else:
            os.environ["ORA_RAG_SELECTION"] = self._old

    def test_default_on(self):
        os.environ.pop("ORA_RAG_SELECTION", None)
        n, floor, _gate, dedup = _build_rag_selection({})
        self.assertEqual(n, 15)
        self.assertEqual(floor, 0.40)
        self.assertTrue(dedup)

    def test_explicit_off(self):
        os.environ["ORA_RAG_SELECTION"] = "0"
        self.assertEqual(_build_rag_selection({}), (None, None, None, False))


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
        mode_files = sorted(
            f for f in os.listdir(modes_dir)
            if f.endswith(".md") and _is_mode_file(f)
        )
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
