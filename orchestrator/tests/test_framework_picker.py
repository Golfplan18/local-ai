#!/usr/bin/env python3
"""V3 Input Handling Phase 2 — framework picker parser tests.

Covers ``parse_framework_picker_metadata`` and ``list_pickable_frameworks``:

- Frameworks declaring ``## Display Name`` AND ``## Display Description`` are
  picker-eligible and parsed into the documented row shape.
- Frameworks missing either heading return ``None`` from the parser and are
  excluded from the picker list. Pipeline-internal frameworks (F-* and
  Phase A — Prompt Cleanup) live in this category by design.
- The picker list is sorted by ``(category, display_name)`` so the UI can
  render groups without re-sorting.
- Display Name and Display Description respect the design-doc length caps
  (60 / 400 chars) for the 19 shipped pickable frameworks.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))

from boot import (
    list_pickable_frameworks,
    parse_framework_picker_metadata,
    parse_framework_input_spec,
    _parse_setup_questions,
)

PIPELINE_INTERNAL_IDS = {
    "f-analysis-breadth", "f-analysis-depth", "f-consolidate",
    "f-evaluate", "f-revise", "f-verify", "phase-a-prompt-cleanup",
}

EXPECTED_PICKABLE_COUNT = 19


class TestParseFrameworkPickerMetadata(unittest.TestCase):

    def test_parses_pickable_framework(self):
        meta = parse_framework_picker_metadata("document-processing")
        self.assertIsNotNone(meta)
        self.assertEqual(meta["id"], "document-processing")
        self.assertEqual(meta["display_name"], "Document Processing")
        self.assertTrue(meta["display_description"].startswith(
            "Convert any document"))
        self.assertEqual(meta["category"], "standard")

    def test_pipeline_internal_returns_none(self):
        # Pipeline-internal frameworks deliberately omit Display Name /
        # Display Description so they are excluded from the picker.
        for pid in PIPELINE_INTERNAL_IDS:
            self.assertIsNone(parse_framework_picker_metadata(pid),
                              msg=f"{pid} must not be picker-eligible")

    def test_unknown_id_returns_none(self):
        self.assertIsNone(parse_framework_picker_metadata("nope-not-a-framework"))


class TestListPickableFrameworks(unittest.TestCase):

    def test_returns_expected_count(self):
        rows = list_pickable_frameworks()
        self.assertEqual(len(rows), EXPECTED_PICKABLE_COUNT)

    def test_excludes_pipeline_internal(self):
        rows = list_pickable_frameworks()
        ids = {r["id"] for r in rows}
        for pid in PIPELINE_INTERNAL_IDS:
            self.assertNotIn(pid, ids)

    def test_rows_have_required_fields(self):
        rows = list_pickable_frameworks()
        for r in rows:
            self.assertIn("id", r)
            self.assertIn("display_name", r)
            self.assertIn("display_description", r)
            self.assertIn("category", r)
            self.assertTrue(r["display_name"].strip())
            self.assertTrue(r["display_description"].strip())

    def test_sorted_by_category_then_display_name(self):
        rows = list_pickable_frameworks()
        keys = [(r["category"], r["display_name"].lower()) for r in rows]
        self.assertEqual(keys, sorted(keys))

    def test_display_name_under_60_chars(self):
        rows = list_pickable_frameworks()
        for r in rows:
            self.assertLessEqual(
                len(r["display_name"]), 60,
                msg=f"{r['id']} display_name too long: "
                    f"{len(r['display_name'])} chars",
            )

    def test_display_description_under_400_chars(self):
        rows = list_pickable_frameworks()
        for r in rows:
            self.assertLessEqual(
                len(r["display_description"]), 400,
                msg=f"{r['id']} display_description too long: "
                    f"{len(r['display_description'])} chars",
            )


class TestParseSetupQuestions(unittest.TestCase):
    """V3 Phase 7 — parse the `## Setup Questions` section into a list of
    question dicts. Each `### Name` block has its body's first-sentence
    flag (Required. / Optional.) extracted, with the rest as description.
    """

    def test_parses_required_and_optional(self):
        text = (
            "# Test Framework\n\n"
            "## Setup Questions\n\n"
            "### Document to process\n"
            "Required. The full text or file path.\n\n"
            "### Source provenance\n"
            "Optional. Where the document came from.\n\n"
            "## PURPOSE\n"
        )
        qs = _parse_setup_questions(text)
        self.assertEqual(len(qs), 2)
        self.assertEqual(qs[0]["name"], "Document to process")
        self.assertTrue(qs[0]["required"])
        self.assertIn("file path", qs[0]["description"])
        self.assertEqual(qs[1]["name"], "Source provenance")
        self.assertFalse(qs[1]["required"])

    def test_no_setup_questions_section_returns_none(self):
        text = "# Test\n\n## PURPOSE\nSomething.\n"
        self.assertIsNone(_parse_setup_questions(text))

    def test_empty_section_returns_none(self):
        text = "## Setup Questions\n\n## PURPOSE\n"
        self.assertIsNone(_parse_setup_questions(text))

    def test_missing_flag_defaults_to_required(self):
        # If a question forgets to declare Required./Optional., default
        # to required so the user sees it as a gap rather than skipping it.
        text = (
            "## Setup Questions\n\n"
            "### Mystery input\n"
            "Some description without a flag.\n"
        )
        qs = _parse_setup_questions(text)
        self.assertEqual(len(qs), 1)
        self.assertTrue(qs[0]["required"])
        self.assertEqual(qs[0]["description"], "Some description without a flag.")

    def test_flag_case_insensitive(self):
        text = (
            "## Setup Questions\n\n"
            "### A\nREQUIRED. Yes.\n\n"
            "### B\noptional. Maybe.\n"
        )
        qs = _parse_setup_questions(text)
        self.assertTrue(qs[0]["required"])
        self.assertFalse(qs[1]["required"])


class TestParseFrameworkInputSpec(unittest.TestCase):

    def test_document_processing_input_contract_parsed(self):
        # Document Processing carries a substantial INPUT CONTRACT — the
        # parser must extract it regardless of whether other sections
        # (Setup Questions, etc.) are present.
        spec = parse_framework_input_spec("document-processing")
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec["input_contract"])
        self.assertGreater(len(spec["input_contract"]), 100)

    def test_document_processing_setup_questions_parsed(self):
        # Document Processing now declares Setup Questions
        # (`### Document or files`, `### Source provenance`). Verify the
        # parser surfaces them in the canonical shape callers expect.
        spec = parse_framework_input_spec("document-processing")
        self.assertIsNotNone(spec)
        questions = spec["setup_questions"]
        self.assertIsNotNone(questions)
        self.assertGreaterEqual(len(questions), 1)
        # Each question carries name / required / description.
        for q in questions:
            self.assertIn("name", q)
            self.assertIn("required", q)
            self.assertIn("description", q)
            self.assertIsInstance(q["required"], bool)

    def test_unknown_framework_returns_none(self):
        self.assertIsNone(parse_framework_input_spec("nope-not-a-framework"))


if __name__ == "__main__":
    unittest.main()
