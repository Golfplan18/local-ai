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
        self.assertEqual(
            resolve_user_invocable_framework("deep-research"),
            "deep-research-protocol.md",
        )
        self.assertEqual(
            resolve_user_invocable_framework("knowledge-artifact-coaching"),
            "knowledge-artifact-coach.md",
        )

    def test_internal_pipeline_specs_are_not_user_invocable_or_pickable(self):
        for framework_id in ("f-consult", "f-format", "supplemental-rag-protocol"):
            self.assertTrue(is_internal_only_framework(framework_id))
            self.assertFalse(is_user_invocable_framework(framework_id))
            self.assertFalse(is_user_pickable_framework(framework_id))
            with self.assertRaises(FrameworkInvocabilityError):
                resolve_user_invocable_framework(framework_id)

    def test_dedicated_only_frameworks_are_neither_picker_nor_slash_invocable(self):
        for framework_id in (
            "api-key-setup", "document-processing", "engram-cleaning",
            "news-supersession", "periodic-maintenance",
            "video-editing-suggestions",
        ):
            self.assertFalse(is_user_pickable_framework(framework_id))
            self.assertFalse(is_user_invocable_framework(framework_id))
            with self.assertRaises(FrameworkInvocabilityError):
                resolve_user_invocable_framework(framework_id)

    def test_registry_lists_share_the_same_public_framework_set(self):
        invocable = set(user_invocable_framework_ids())
        pickable = set(user_pickable_framework_ids())
        expected = {
            "conversation-processing", "corpus-formalization",
            "deep-research", "knowledge-artifact-coaching",
            "mindspec-interview", "mission-objectives-milestones",
            "output-formalization", "problem-evolution",
            "process-formalization", "process-inference", "terrain-mapping",
        }
        self.assertEqual(invocable, expected)
        self.assertEqual(pickable, expected)
        self.assertNotIn("programming", pickable)
        self.assertNotIn("programming", invocable)

    def test_programming_uses_its_explicit_surface_not_framework_invocation(self):
        self.assertFalse(is_user_pickable_framework("programming"))
        self.assertFalse(is_user_invocable_framework("programming"))
        with self.assertRaises(FrameworkInvocabilityError):
            resolve_user_invocable_framework("programming")


if __name__ == "__main__":
    unittest.main()
