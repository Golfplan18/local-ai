#!/usr/bin/env python3
"""Regression tests for the curated framework invocability boundary.

The framework picker and the `/framework` slash command should not infer
user-facing availability from files merely existing in frameworks/book/.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))

from framework_invocability import (  # noqa: E402
    FrameworkInvocabilityError,
    is_internal_only_framework,
    is_user_invocable_framework,
    is_user_pickable_framework,
    reset_framework_invocability_registry_cache,
    resolve_user_invocable_framework,
    user_invocable_framework_ids,
    user_pickable_framework_ids,
)


class TestFrameworkInvocability(unittest.TestCase):
    def setUp(self):
        reset_framework_invocability_registry_cache()

    def tearDown(self):
        reset_framework_invocability_registry_cache()

    def test_aliases_resolve_to_canonical_invocable_frameworks(self):
        self.assertEqual(
            resolve_user_invocable_framework("pff"),
            "process-formalization.md",
        )
        self.assertEqual(
            resolve_user_invocable_framework("cff"),
            "corpus-formalization.md",
        )
        self.assertEqual(
            resolve_user_invocable_framework("off"),
            "output-formalization.md",
        )

    def test_internal_pipeline_specs_are_not_user_invocable_or_pickable(self):
        for framework_id in ("f-consult", "f-format", "supplemental-rag-protocol"):
            self.assertTrue(is_internal_only_framework(framework_id))
            self.assertFalse(is_user_invocable_framework(framework_id))
            self.assertFalse(is_user_pickable_framework(framework_id))
            with self.assertRaises(FrameworkInvocabilityError):
                resolve_user_invocable_framework(framework_id)

    def test_picker_only_framework_can_appear_without_slash_command_access(self):
        self.assertTrue(is_user_pickable_framework("document-processing"))
        self.assertFalse(is_user_invocable_framework("document-processing"))
        with self.assertRaises(FrameworkInvocabilityError):
            resolve_user_invocable_framework("document-processing")

    def test_registry_lists_keep_picker_and_invocable_boundaries_distinct(self):
        invocable = set(user_invocable_framework_ids())
        pickable = set(user_pickable_framework_ids())
        self.assertIn("process-formalization", invocable)
        self.assertIn("document-processing", pickable)
        self.assertNotIn("document-processing", invocable)
        self.assertTrue(invocable.issubset(pickable))


if __name__ == "__main__":
    unittest.main()
