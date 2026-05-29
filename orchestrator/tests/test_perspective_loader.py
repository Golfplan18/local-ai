"""Tests for the Analytical Perspectives layer in ``orchestrator/boot.py``.

Covers:
  - thinking-tools.md parsing (13 Tier-1 tools by id)
  - mental-models/*.md walking (frontmatter stripped)
  - parsing of the ``## ANALYTICAL PERSPECTIVES`` section
  - resolving ids → injectable markdown
  - unknown ids skipped silently
  - caches are stable across repeated calls
  - real cui-bono.md mode file resolves cleanly end-to-end

All tests run offline against the actual files in ``~/ora/modules/`` and
``~/ora/knowledge/mental-models/``.
"""

from __future__ import annotations

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
if _ORCHESTRATOR not in sys.path:
    sys.path.insert(0, _ORCHESTRATOR)

import boot  # noqa: E402


class ThinkingToolsLoadTests(unittest.TestCase):

    def setUp(self):
        boot._reset_perspective_caches()

    def test_loads_thirteen_tier1_tools(self):
        tools = boot._load_thinking_tools()
        # Per thinking-tools.md the Tier 1 acronym tools are AGO, CAF,
        # C&S, PMI, OPV, KVI, FIP, APC, plus three name-only tools
        # (Concept Fan, Challenge, Provocation) and RAD, FGL.
        expected_ids = {
            "AGO", "CAF", "C&S", "PMI", "OPV", "KVI",
            "FIP", "APC", "Concept Fan", "Challenge",
            "Provocation", "RAD", "FGL",
        }
        self.assertEqual(set(tools.keys()), expected_ids)

    def test_tool_body_contains_purpose_line(self):
        tools = boot._load_thinking_tools()
        ago = tools.get("AGO")
        self.assertIsNotNone(ago)
        self.assertIn("Purpose", ago)
        self.assertIn("Aims", ago)

    def test_cache_is_reused_across_calls(self):
        tools1 = boot._load_thinking_tools()
        tools2 = boot._load_thinking_tools()
        self.assertIs(tools1, tools2)


class MentalModelsLoadTests(unittest.TestCase):

    def setUp(self):
        boot._reset_perspective_caches()

    def test_loads_expected_models(self):
        models = boot._load_mental_models()
        # Spot-check a handful that should exist per the directory.
        self.assertIn("nash-equilibrium", models)
        self.assertIn("batna", models)
        self.assertIn("cooperation", models)
        self.assertIn("brinkmanship", models)
        # We expect well over 100; matching exact count would be brittle
        # if you add new models — assert a floor.
        self.assertGreater(len(models), 100)

    def test_frontmatter_is_stripped(self):
        models = boot._load_mental_models()
        body = models.get("nash-equilibrium", "")
        self.assertNotIn("---\nlens_id:", body)
        self.assertIn("Nash Equilibrium", body)

    def test_cache_is_reused_across_calls(self):
        m1 = boot._load_mental_models()
        m2 = boot._load_mental_models()
        self.assertIs(m1, m2)


class ParsePerspectivesTests(unittest.TestCase):

    def test_parses_both_buckets(self):
        section = """
Thinking tools (always loaded):
- OPV
- KVI

Mental models (always loaded):
- nash-equilibrium
- batna
"""
        tools, models = boot._parse_analytical_perspectives(section)
        self.assertEqual(tools, ["OPV", "KVI"])
        self.assertEqual(models, ["nash-equilibrium", "batna"])

    def test_tools_only(self):
        tools, models = boot._parse_analytical_perspectives(
            "Thinking tools:\n- OPV\n"
        )
        self.assertEqual(tools, ["OPV"])
        self.assertEqual(models, [])

    def test_models_only(self):
        tools, models = boot._parse_analytical_perspectives(
            "Mental models:\n- batna\n- cooperation\n"
        )
        self.assertEqual(tools, [])
        self.assertEqual(models, ["batna", "cooperation"])

    def test_empty_section_returns_empty_lists(self):
        self.assertEqual(
            boot._parse_analytical_perspectives(""),
            ([], []),
        )

    def test_bullets_without_header_are_ignored(self):
        tools, models = boot._parse_analytical_perspectives(
            "- orphan-bullet\n\nThinking tools:\n- OPV\n"
        )
        self.assertEqual(tools, ["OPV"])
        self.assertEqual(models, [])

    def test_case_insensitive_header_match(self):
        tools, models = boot._parse_analytical_perspectives(
            "THINKING TOOLS:\n- OPV\nLenses:\n- batna\n"
        )
        self.assertEqual(tools, ["OPV"])
        self.assertEqual(models, ["batna"])


class ResolvePerspectivesTests(unittest.TestCase):

    def setUp(self):
        boot._reset_perspective_caches()

    def test_resolves_known_tools_and_models(self):
        out = boot._resolve_analytical_perspectives(
            ["OPV"], ["nash-equilibrium"],
        )
        self.assertIn("Thinking tools", out)
        self.assertIn("OPV", out)
        self.assertIn("Other People", out)  # OPV definition body
        self.assertIn("Mental models", out)
        self.assertIn("Nash Equilibrium", out)

    def test_unknown_tool_skipped_silently(self):
        out = boot._resolve_analytical_perspectives(
            ["OPV", "NOPE"], [],
        )
        self.assertIn("OPV", out)
        self.assertNotIn("NOPE", out)

    def test_unknown_model_skipped_silently(self):
        out = boot._resolve_analytical_perspectives(
            [], ["batna", "does-not-exist"],
        )
        self.assertIn("Batna", out.replace("BATNA", "Batna"))
        self.assertNotIn("does-not-exist", out)

    def test_empty_lists_return_empty_string(self):
        self.assertEqual(
            boot._resolve_analytical_perspectives([], []),
            "",
        )

    def test_all_unknown_returns_empty_string(self):
        self.assertEqual(
            boot._resolve_analytical_perspectives(
                ["NOPE"], ["also-nope"],
            ),
            "",
        )


class CuiBonoEndToEndTests(unittest.TestCase):
    """The cui-bono mode file carries the proof-of-mechanism allowlist."""

    def setUp(self):
        boot._reset_perspective_caches()

    def test_cui_bono_perspectives_resolve(self):
        path = os.path.expanduser("~/ora/modes/cui-bono.md")
        with open(path, "r", encoding="utf-8") as f:
            mode_text = f.read()
        section = boot._extract_section(mode_text, "ANALYTICAL PERSPECTIVES")
        self.assertTrue(section, "## ANALYTICAL PERSPECTIVES section missing in cui-bono.md")
        tools, models = boot._parse_analytical_perspectives(section)
        self.assertEqual(tools, ["OPV", "KVI"])
        self.assertEqual(
            models, ["nash-equilibrium", "batna", "cooperation"],
        )
        resolved = boot._resolve_analytical_perspectives(tools, models)
        self.assertIn("OPV", resolved)
        self.assertIn("KVI", resolved)
        self.assertIn("Nash Equilibrium", resolved)


if __name__ == "__main__":
    unittest.main()
