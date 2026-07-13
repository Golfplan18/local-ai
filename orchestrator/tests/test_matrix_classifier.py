"""Tests for the shared Matrix classifier.

Covers matrix_classifier.classify_matrix and matrix_classifier.schema_valid
across the full input space defined by the Project Type Registry and the
approved compatibility-now behavior.
"""
from __future__ import annotations

import os
import sys
import unittest

# Make orchestrator/ importable
HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = os.path.dirname(HERE)
if ORCH not in sys.path:
    sys.path.insert(0, ORCH)

from matrix_classifier import (  # noqa: E402
    VALID_CLASSIFICATIONS,
    VALID_DOMAIN_TYPES,
    VALID_TOKENS,
    InvalidProjectTypeError,
    classify_matrix,
    schema_valid,
)


class TestClassifyMatrix(unittest.TestCase):
    """Exercise classify_matrix(frontmatter, file_path) across the full input space."""

    # ---- Absent / None ----

    def test_none_frontmatter_defaults_to_project(self):
        classification, warnings = classify_matrix(None, "/tmp/test.md")
        self.assertEqual(classification, "project")
        self.assertEqual(len(warnings), 1)
        self.assertIn("project_type absent", warnings[0])

    def test_empty_dict_defaults_to_project(self):
        classification, warnings = classify_matrix({}, "/tmp/test.md")
        self.assertEqual(classification, "project")
        self.assertEqual(len(warnings), 1)

    def test_empty_project_type_list_defaults_to_project(self):
        classification, warnings = classify_matrix(
            {"project_type": []}, "/tmp/test.md",
        )
        self.assertEqual(classification, "project")
        self.assertEqual(len(warnings), 1)
        self.assertIn("no classification token", warnings[0])

    # ---- Scalar string ----

    def test_scalar_project(self):
        classification, warnings = classify_matrix(
            {"project_type": "project"}, "/tmp/test.md",
        )
        self.assertEqual(classification, "project")
        self.assertEqual(len(warnings), 1)
        self.assertIn("scalar string", warnings[0])

    def test_scalar_operation(self):
        classification, warnings = classify_matrix(
            {"project_type": "operation"}, "/tmp/test.md",
        )
        self.assertEqual(classification, "operation")
        self.assertEqual(len(warnings), 1)
        self.assertIn("scalar string", warnings[0])

    def test_scalar_passion(self):
        classification, warnings = classify_matrix(
            {"project_type": "passion"}, "/tmp/test.md",
        )
        self.assertEqual(classification, "passion")
        self.assertEqual(len(warnings), 1)
        self.assertIn("scalar string", warnings[0])

    def test_scalar_incubator(self):
        classification, warnings = classify_matrix(
            {"project_type": "incubator"}, "/tmp/test.md",
        )
        self.assertEqual(classification, "incubator")
        self.assertEqual(len(warnings), 1)
        self.assertIn("scalar string", warnings[0])

    # ---- Single-element list ----

    def test_list_single_project(self):
        classification, warnings = classify_matrix(
            {"project_type": ["project"]}, "/tmp/test.md",
        )
        self.assertEqual(classification, "project")
        self.assertEqual(warnings, [])

    def test_list_single_operation(self):
        classification, warnings = classify_matrix(
            {"project_type": ["operation"]}, "/tmp/test.md",
        )
        self.assertEqual(classification, "operation")
        self.assertEqual(warnings, [])

    def test_list_single_passion(self):
        classification, warnings = classify_matrix(
            {"project_type": ["passion"]}, "/tmp/test.md",
        )
        self.assertEqual(classification, "passion")
        self.assertEqual(warnings, [])

    def test_list_single_incubator(self):
        classification, warnings = classify_matrix(
            {"project_type": ["incubator"]}, "/tmp/test.md",
        )
        self.assertEqual(classification, "incubator")
        self.assertEqual(warnings, [])

    # ---- Classification + domain tokens ----

    def test_project_plus_book(self):
        classification, warnings = classify_matrix(
            {"project_type": ["project", "book"]}, "/tmp/test.md",
        )
        self.assertEqual(classification, "project")
        self.assertEqual(warnings, [])

    def test_operation_plus_book(self):
        classification, warnings = classify_matrix(
            {"project_type": ["operation", "book"]}, "/tmp/test.md",
        )
        self.assertEqual(classification, "operation")
        self.assertEqual(warnings, [])

    def test_project_plus_book_and_knowledge(self):
        classification, warnings = classify_matrix(
            {"project_type": ["project", "book", "knowledge"]}, "/tmp/test.md",
        )
        self.assertEqual(classification, "project")
        self.assertEqual(warnings, [])

    def test_passion_plus_workflow(self):
        classification, warnings = classify_matrix(
            {"project_type": ["passion", "workflow"]}, "/tmp/test.md",
        )
        self.assertEqual(classification, "passion")
        self.assertEqual(warnings, [])

    # ---- Domain-only (no classification token) ----

    def test_domain_only_book_knowledge_defaults_to_project(self):
        classification, warnings = classify_matrix(
            {"project_type": ["book", "knowledge"]}, "/tmp/test.md",
        )
        self.assertEqual(classification, "project")
        self.assertEqual(len(warnings), 1)
        self.assertIn("no classification token", warnings[0])

    def test_domain_only_workflow_defaults_to_project(self):
        classification, warnings = classify_matrix(
            {"project_type": ["workflow"]}, "/tmp/test.md",
        )
        self.assertEqual(classification, "project")
        self.assertEqual(len(warnings), 1)

    def test_domain_only_fiction_defaults_to_project(self):
        classification, warnings = classify_matrix(
            {"project_type": ["fiction"]}, "/tmp/test.md",
        )
        self.assertEqual(classification, "project")
        self.assertEqual(len(warnings), 1)

    # ---- Multiple classifications (error) ----

    def test_two_classifications_raises(self):
        with self.assertRaises(InvalidProjectTypeError) as cm:
            classify_matrix(
                {"project_type": ["operation", "passion"]}, "/tmp/test.md",
            )
        self.assertIn("multiple classifications", str(cm.exception))
        self.assertEqual(cm.exception.matrix_path, "/tmp/test.md")

    def test_three_classifications_raises(self):
        with self.assertRaises(InvalidProjectTypeError):
            classify_matrix(
                {"project_type": ["project", "operation", "passion"]},
                "/tmp/test.md",
            )

    def test_classification_plus_domain_plus_classification_raises(self):
        with self.assertRaises(InvalidProjectTypeError):
            classify_matrix(
                {"project_type": ["project", "book", "operation"]},
                "/tmp/test.md",
            )

    # ---- Invalid types ----

    def test_integer_raises(self):
        with self.assertRaises(InvalidProjectTypeError) as cm:
            classify_matrix({"project_type": 42}, "/tmp/test.md")
        self.assertIn("unsupported", str(cm.exception))

    def test_float_raises(self):
        with self.assertRaises(InvalidProjectTypeError):
            classify_matrix({"project_type": 3.14}, "/tmp/test.md")

    def test_boolean_raises(self):
        with self.assertRaises(InvalidProjectTypeError):
            classify_matrix({"project_type": True}, "/tmp/test.md")

    # ---- Edge cases ----

    def test_whitespace_stripped_from_scalar(self):
        classification, warnings = classify_matrix(
            {"project_type": "  project  "}, "/tmp/test.md",
        )
        self.assertEqual(classification, "project")

    def test_file_path_appears_in_error(self):
        with self.assertRaises(InvalidProjectTypeError) as cm:
            classify_matrix(
                {"project_type": ["project", "operation"]},
                "/vault/Matrix/Project Matrix Test.md",
            )
        self.assertIn("Project Matrix Test.md", str(cm.exception))

    # ---- Non-string list entries (Finding 2) ----

    def test_integer_in_list_raises(self):
        with self.assertRaises(InvalidProjectTypeError) as cm:
            classify_matrix({"project_type": ["project", 1]}, "/tmp/test.md")
        self.assertIn("non-string entry", str(cm.exception))
        self.assertIn("index 1", str(cm.exception))

    def test_float_in_list_raises(self):
        with self.assertRaises(InvalidProjectTypeError):
            classify_matrix({"project_type": [3.14]}, "/tmp/test.md")

    def test_bool_in_list_raises(self):
        with self.assertRaises(InvalidProjectTypeError):
            classify_matrix({"project_type": [True, "project"]}, "/tmp/test.md")

    def test_none_in_list_raises(self):
        with self.assertRaises(InvalidProjectTypeError):
            classify_matrix({"project_type": [None, "project"]}, "/tmp/test.md")

    def test_mixed_string_and_int_raises(self):
        with self.assertRaises(InvalidProjectTypeError):
            classify_matrix(
                {"project_type": ["project", "book", 42]}, "/tmp/test.md",
            )

    # ---- Unknown token diagnostics (Finding 3) ----

    def test_unknown_token_warns(self):
        classification, warnings = classify_matrix(
            {"project_type": ["project", "unknown_thing"]}, "/tmp/test.md",
        )
        self.assertEqual(classification, "project")
        unknown_warnings = [w for w in warnings if "unrecognized token" in w]
        self.assertEqual(len(unknown_warnings), 1)
        self.assertIn("unknown_thing", unknown_warnings[0])

    def test_multiple_unknown_tokens_warn(self):
        classification, warnings = classify_matrix(
            {"project_type": ["project", "foo", "bar"]}, "/tmp/test.md",
        )
        self.assertEqual(classification, "project")
        unknown_warnings = [w for w in warnings if "unrecognized token" in w]
        self.assertEqual(len(unknown_warnings), 1)
        self.assertIn("foo", unknown_warnings[0])
        self.assertIn("bar", unknown_warnings[0])

    def test_unknown_token_plus_domain_still_classifies(self):
        classification, warnings = classify_matrix(
            {"project_type": ["operation", "book", "not_a_real_type"]},
            "/tmp/test.md",
        )
        self.assertEqual(classification, "operation")
        unknown_warnings = [w for w in warnings if "unrecognized token" in w]
        self.assertEqual(len(unknown_warnings), 1)
        self.assertIn("not_a_real_type", unknown_warnings[0])

    # ---- Token sets ----

    def test_valid_classifications_has_four_entries(self):
        self.assertEqual(len(VALID_CLASSIFICATIONS), 4)
        self.assertIn("project", VALID_CLASSIFICATIONS)
        self.assertIn("operation", VALID_CLASSIFICATIONS)
        self.assertIn("passion", VALID_CLASSIFICATIONS)
        self.assertIn("incubator", VALID_CLASSIFICATIONS)

    def test_valid_domain_types_has_four_entries(self):
        self.assertEqual(len(VALID_DOMAIN_TYPES), 4)
        self.assertIn("book", VALID_DOMAIN_TYPES)
        self.assertIn("knowledge", VALID_DOMAIN_TYPES)
        self.assertIn("workflow", VALID_DOMAIN_TYPES)
        self.assertIn("fiction", VALID_DOMAIN_TYPES)

    def test_valid_tokens_is_union(self):
        self.assertEqual(VALID_TOKENS, VALID_CLASSIFICATIONS | VALID_DOMAIN_TYPES)


class TestSchemaValid(unittest.TestCase):
    """Exercise schema_valid(frontmatter) — the write-gate check."""

    def test_valid_project(self):
        self.assertTrue(schema_valid({"project_type": ["project"]}))

    def test_valid_operation(self):
        self.assertTrue(schema_valid({"project_type": ["operation"]}))

    def test_valid_passion(self):
        self.assertTrue(schema_valid({"project_type": ["passion"]}))

    def test_valid_incubator(self):
        self.assertTrue(schema_valid({"project_type": ["incubator"]}))

    def test_valid_project_plus_domain(self):
        self.assertTrue(schema_valid({"project_type": ["project", "book"]}))

    def test_valid_operation_plus_domains(self):
        self.assertTrue(schema_valid({"project_type": ["operation", "book", "workflow"]}))

    def test_missing_frontmatter(self):
        self.assertFalse(schema_valid(None))

    def test_missing_project_type(self):
        self.assertFalse(schema_valid({}))

    def test_scalar_string(self):
        self.assertFalse(schema_valid({"project_type": "project"}))

    def test_empty_list(self):
        self.assertFalse(schema_valid({"project_type": []}))

    def test_domain_only(self):
        self.assertFalse(schema_valid({"project_type": ["book", "knowledge"]}))

    def test_multiple_classifications(self):
        self.assertFalse(schema_valid({"project_type": ["project", "operation"]}))

    def test_unknown_token(self):
        self.assertFalse(schema_valid({"project_type": ["project", "unknown_thing"]}))

    def test_integer_value(self):
        self.assertFalse(schema_valid({"project_type": 42}))

    def test_duplicate_domain_tokens(self):
        self.assertFalse(schema_valid({"project_type": ["project", "book", "book"]}))

    def test_duplicate_classification_token(self):
        self.assertFalse(schema_valid({"project_type": ["project", "project"]}))

    def test_non_string_entry_in_list(self):
        self.assertFalse(schema_valid({"project_type": ["project", 1]}))

    def test_none_entry_in_list(self):
        self.assertFalse(schema_valid({"project_type": [None, "project"]}))


class TestBackwardCompatibility(unittest.TestCase):
    """Verify that oversight_context still re-exports the shared symbols."""

    def test_import_classify_matrix_from_oversight_context(self):
        from oversight_context import classify_matrix as oc_classify
        # Should be callable and return (classification, warnings)
        from ped_parser import parse_ped_text
        ped = parse_ped_text(
            "---\nnexus:\n  - test\n---\n\n# Test\n\n## Mission\n\n- **Resolution Statement:** Done.\n",
            file_path="/tmp/test.md",
        )
        classification, warnings = oc_classify(ped)
        self.assertEqual(classification, "project")
        self.assertIn("project_type absent", warnings[0])

    def test_import_invalid_project_type_error_from_oversight_context(self):
        from oversight_context import InvalidProjectTypeError as oc_exc
        # Should be the same class as the shared one
        self.assertIs(oc_exc, InvalidProjectTypeError)

    def test_import_valid_classifications_from_oversight_context(self):
        from oversight_context import VALID_CLASSIFICATIONS as oc_valid
        self.assertIs(oc_valid, VALID_CLASSIFICATIONS)


if __name__ == "__main__":
    unittest.main()
