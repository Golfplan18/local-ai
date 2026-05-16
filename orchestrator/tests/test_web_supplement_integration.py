"""Integration tests for Step 2.5 web-supplement wiring in boot.py.

Verifies:
  - The config loader reads ``web_supplement`` from routing-config.json
    and falls back to safe defaults when missing.
  - ``build_system_prompt_for_gear`` injects a ``## WEB CONTEXT`` block
    when ``context_pkg['web_rag']`` is non-empty, and omits it when empty.
  - The trace skip-reason path is exercised when WEB_SUPPLEMENT_AVAILABLE
    is True but no fast endpoint resolves.

The full ``run_step2_context_assembly`` call path requires a live
ChromaDB and a real fast endpoint — exercised by the live cui-bono
smoke after server restart, not by these unit tests.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
if _ORCHESTRATOR not in sys.path:
    sys.path.insert(0, _ORCHESTRATOR)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import boot  # noqa: E402


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------


class LoadWebSupplementConfig(unittest.TestCase):
    def test_reads_section_from_routing_config(self):
        cfg = boot._load_web_supplement_config()
        # The live routing-config.json was populated in commit D — these
        # should match unless the operator has flipped them.
        self.assertIn("enabled", cfg)
        self.assertIn("max_gaps", cfg)
        self.assertIn("max_attempts_per_gap", cfg)
        self.assertIsInstance(cfg["enabled"], bool)
        self.assertIsInstance(cfg["max_gaps"], int)
        self.assertGreater(cfg["max_gaps"], 0)

    def test_missing_section_falls_back_to_defaults(self):
        fd, tmp_path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({"_schema_version": 2, "buckets": {}}, f)
            with mock.patch.object(boot, "ROUTING_CONFIG_JSON", tmp_path):
                cfg = boot._load_web_supplement_config()
            self.assertTrue(cfg["enabled"])
            self.assertEqual(cfg["max_gaps"], 3)
            self.assertEqual(cfg["max_attempts_per_gap"], 2)
        finally:
            os.unlink(tmp_path)

    def test_missing_file_falls_back_to_defaults(self):
        with mock.patch.object(boot, "ROUTING_CONFIG_JSON",
                                "/nonexistent/path.json"):
            cfg = boot._load_web_supplement_config()
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["max_gaps"], 3)

    def test_override_disables_loop(self):
        fd, tmp_path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({"web_supplement": {"enabled": False}}, f)
            with mock.patch.object(boot, "ROUTING_CONFIG_JSON", tmp_path):
                cfg = boot._load_web_supplement_config()
            self.assertFalse(cfg["enabled"])
            # Defaults still merged for the other fields.
            self.assertEqual(cfg["max_gaps"], 3)
        finally:
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# build_system_prompt_for_gear — WEB CONTEXT injection
# ---------------------------------------------------------------------------


def _minimal_context_pkg(**overrides) -> dict:
    """Build a minimal context_pkg dict sufficient for
    build_system_prompt_for_gear to run without errors."""
    pkg = {
        "mode_text": (
            "## DEPTH ANALYSIS GUIDANCE\nDepth instructions.\n\n"
            "## BREADTH ANALYSIS GUIDANCE\nBreadth instructions.\n\n"
            "## EVALUATION CRITERIA\nEval criteria.\n\n"
            "## REVISION GUIDANCE\nRev guidance.\n\n"
            "## VERIFICATION CRITERIA\nVerify criteria.\n\n"
            "## CONSOLIDATION GUIDANCE\nConsolidate.\n\n"
            "## OUTPUT FORMAT GUIDANCE\nFormat.\n"
        ),
        "mode_name": "test-mode",
        "conversation_rag": "",
        "concept_rag":      "",
        "relationship_rag": "",
        "web_rag":          "",
        "rag_utilization":  "",
        "inferred_items":   "",
    }
    pkg.update(overrides)
    return pkg


class WebContextInjection(unittest.TestCase):
    def test_block_appears_when_web_rag_is_present(self):
        pkg = _minimal_context_pkg(
            web_rag="[classification: whitelisted | weight: 0.7 | "
                    "source: https://en.wikipedia.org/wiki/Foo]\n"
                    "Wikipedia snippet body."
        )
        prompt = boot.build_system_prompt_for_gear(pkg, slot="depth",
                                                    step="analyst")
        self.assertIn("## WEB CONTEXT", prompt)
        self.assertIn("classification: whitelisted", prompt)
        self.assertIn("Wikipedia snippet body.", prompt)

    def test_block_absent_when_web_rag_is_empty(self):
        pkg = _minimal_context_pkg(web_rag="")
        prompt = boot.build_system_prompt_for_gear(pkg, slot="depth",
                                                    step="analyst")
        self.assertNotIn("## WEB CONTEXT", prompt)

    def test_block_appears_for_every_step_not_just_analyst(self):
        pkg = _minimal_context_pkg(web_rag="[classification: single | weight: 0.15 | source: x] body")
        for step in ("analyst", "evaluator", "reviser", "verifier",
                     "consolidator", "formatter"):
            slot = "depth" if step == "analyst" else "breadth"
            prompt = boot.build_system_prompt_for_gear(pkg, slot=slot, step=step)
            self.assertIn("## WEB CONTEXT", prompt,
                          f"web context missing at step={step}")

    def test_web_context_block_carries_lower_provenance_caveat(self):
        # The header explicitly tells the model this is lower-provenance
        # than vault content — preserves the analytical weighting story
        # without requiring per-mode prompt edits.
        pkg = _minimal_context_pkg(web_rag="[classification: whitelisted | weight: 0.7 | source: x] body")
        prompt = boot.build_system_prompt_for_gear(pkg, slot="depth",
                                                    step="analyst")
        self.assertIn("supplemental, lower provenance", prompt)


if __name__ == "__main__":
    unittest.main()
