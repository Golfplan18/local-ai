"""Tests for the mode-aware relationship-priority wiring (2026-05-09).

Confirms:
- All 58 mode files carry the `### RAG PROFILE — RELATIONSHIP PRIORITIES`
  section the parser at `relationship_traversal.parse_mode_relationship_priorities`
  expects.
- Each mode returns a non-empty priority list using only valid taxonomy types.
- Two contrasting modes (causal vs argument) score the same relationship
  differently — verifying the differentiation the wiring exists to provide.
- Per-mode overrides (e.g., third-side in stakeholder-strategy family) deviate
  from family default as documented.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

# Derived from __file__ (same pattern as test_stealth_short_circuit_purge_2026_05_17.py)
# rather than hardcoded to ~/ora, so this resolves correctly from a worktree too.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

from orchestrator.tools.relationship_traversal import (
    parse_mode_relationship_priorities,
    score_relationship,
)


MODES_DIR = Path(REPO_ROOT) / "modes"

# 13-type taxonomy from Schema §7
VALID_TYPES = {
    "supports", "contradicts", "qualifies", "extends", "supersedes",
    "analogous-to", "derived-from", "enables", "requires", "produces",
    "precedes", "parent", "child",
}


# Bypass-style modes that don't go through the analytical pipeline and
# therefore don't need cross-mode relationship priorities. The RAG
# relationship-traversal step is gear-2+; gear-1 / catch-all modes are
# exempted from the priority-presence checks.
_BYPASS_STYLE_MODES = {"simple"}


class TestAllModesCarryPriorities(unittest.TestCase):
    """Every analytical mode file must carry the section the parser expects."""

    def test_section_present_in_every_mode(self):
        mode_files = sorted(MODES_DIR.glob("*.md"))
        analytical = [p for p in mode_files if p.stem not in _BYPASS_STYLE_MODES]
        self.assertGreaterEqual(
            len(analytical), 58,
            f"expected at least 58 analytical mode files, found {len(analytical)}"
        )
        missing = []
        for path in analytical:
            text = path.read_text(encoding="utf-8")
            if "### RAG PROFILE — RELATIONSHIP PRIORITIES" not in text:
                missing.append(path.stem)
        self.assertEqual(
            missing, [],
            f"these modes lack the section: {missing}"
        )

    def test_each_mode_parses_to_nonempty_priority_list(self):
        """Parser must return at least one prioritized type for each
        analytical mode. Bypass-style modes (gear-1, direct-response)
        are exempted — they don't use cross-mode relationship traversal."""
        for path in sorted(MODES_DIR.glob("*.md")):
            if path.stem in _BYPASS_STYLE_MODES:
                continue
            with self.subTest(mode=path.stem):
                text = path.read_text(encoding="utf-8")
                pri = parse_mode_relationship_priorities(text)
                self.assertGreaterEqual(
                    len(pri["priority"]), 3,
                    f"{path.stem} has fewer than 3 priorities: {pri['priority']}"
                )
                self.assertGreaterEqual(
                    len(pri["depriority"]), 1,
                    f"{path.stem} has no deprioritized types"
                )

    def test_all_types_valid(self):
        """No mode references a type outside the 13-type taxonomy."""
        for path in sorted(MODES_DIR.glob("*.md")):
            with self.subTest(mode=path.stem):
                text = path.read_text(encoding="utf-8")
                pri = parse_mode_relationship_priorities(text)
                for t in pri["priority"] + pri["depriority"]:
                    self.assertIn(
                        t, VALID_TYPES,
                        f"{path.stem} uses unknown type '{t}'"
                    )


class TestModeDifferentiation(unittest.TestCase):
    """The whole point of the wiring: different modes score relationships differently."""

    def setUp(self):
        with open(MODES_DIR / "root-cause-analysis.md", encoding="utf-8") as f:
            self.causal = parse_mode_relationship_priorities(f.read())
        with open(MODES_DIR / "argument-audit.md", encoding="utf-8") as f:
            self.argument = parse_mode_relationship_priorities(f.read())

    def test_causal_mode_amplifies_temporal_relationships(self):
        rel = {"type": "precedes", "confidence": "high"}
        causal_score = score_relationship(
            rel, self.causal["priority"], self.causal["depriority"]
        )
        argument_score = score_relationship(
            rel, self.argument["priority"], self.argument["depriority"]
        )
        self.assertGreater(
            causal_score, argument_score,
            "precedes should score higher under causal mode than argument mode"
        )

    def test_argument_mode_amplifies_evidence_relationships(self):
        rel = {"type": "supports", "confidence": "high"}
        causal_score = score_relationship(
            rel, self.causal["priority"], self.causal["depriority"]
        )
        argument_score = score_relationship(
            rel, self.argument["priority"], self.argument["depriority"]
        )
        self.assertGreater(
            argument_score, causal_score,
            "supports should score higher under argument mode than causal mode"
        )


class TestPerModeOverride(unittest.TestCase):
    """The third-side override pulls in analogous-to despite stakeholder-strategy
    family default deprioritizing it."""

    def test_third_side_includes_analogous_to(self):
        with open(MODES_DIR / "third-side.md", encoding="utf-8") as f:
            pri = parse_mode_relationship_priorities(f.read())
        self.assertIn(
            "analogous-to", pri["priority"],
            "third-side should prioritize analogous-to (per-mode override)"
        )
        self.assertIn(
            "contradicts", pri["depriority"],
            "third-side should deprioritize contradicts (per-mode override)"
        )

    def test_other_stakeholder_strategy_modes_use_family_default(self):
        """cui-bono should follow family default — analogous-to deprioritized."""
        with open(MODES_DIR / "cui-bono.md", encoding="utf-8") as f:
            pri = parse_mode_relationship_priorities(f.read())
        self.assertIn(
            "analogous-to", pri["depriority"],
            "cui-bono should deprioritize analogous-to (family default)"
        )


if __name__ == "__main__":
    unittest.main()
