#!/usr/bin/env python3
"""Tests for orchestrator.framework_config (Plugin Convention §14, chunk 2).

Covers:
  - parse_config_interface: section detection, key extraction, default
    decoding (string / null / int / float / bool), no-default sentinel
  - substitute_config_refs: priority (supplied > default), None
    rendering, unresolved-reference error
  - compose_framework_spec: end-to-end against synthetic frameworks and
    synthetic project fixtures (project_not_registered, profile_not_declared,
    happy paths with + without project context)
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORA_ORCH = HERE.parent
sys.path.insert(0, str(ORA_ORCH.parent))  # ~/ora

from orchestrator import framework_config as fc  # noqa: E402
from orchestrator import project_registry as pr  # noqa: E402


# ---------------------------------------------------------------------------
# parse_config_interface
# ---------------------------------------------------------------------------

class TestParseConfigInterface(unittest.TestCase):
    def test_no_section_returns_empty(self):
        spec = "# Framework\n\n## OTHER SECTION\n\nbody\n"
        self.assertEqual(fc.parse_config_interface(spec), {})

    def test_string_default(self):
        spec = (
            "## CONFIGURATION INTERFACE\n\n"
            "- **`collection`** (string, default: `knowledge`) — desc\n"
        )
        result = fc.parse_config_interface(spec)
        self.assertEqual(result, {"collection": "knowledge"})

    def test_null_default_bare(self):
        spec = (
            "## CONFIGURATION INTERFACE\n\n"
            "- **`override`** (object or null, default: null) — desc\n"
        )
        result = fc.parse_config_interface(spec)
        self.assertIn("override", result)
        self.assertIsNone(result["override"])

    def test_null_default_backticked(self):
        spec = (
            "## CONFIGURATION INTERFACE\n\n"
            "- **`override`** (object or null, default: `null`) — desc\n"
        )
        result = fc.parse_config_interface(spec)
        self.assertIsNone(result["override"])

    def test_no_default_returns_sentinel(self):
        spec = (
            "## CONFIGURATION INTERFACE\n\n"
            "- **`required`** (string) — must be supplied\n"
        )
        result = fc.parse_config_interface(spec)
        self.assertIs(result["required"], fc.NO_DEFAULT)

    def test_int_default(self):
        spec = (
            "## CONFIGURATION INTERFACE\n\n"
            "- **`max_retries`** (int, default: `5`) — desc\n"
        )
        result = fc.parse_config_interface(spec)
        self.assertEqual(result["max_retries"], 5)

    def test_float_default(self):
        spec = (
            "## CONFIGURATION INTERFACE\n\n"
            "- **`threshold`** (float, default: `0.85`) — desc\n"
        )
        result = fc.parse_config_interface(spec)
        self.assertEqual(result["threshold"], 0.85)

    def test_bool_default(self):
        spec = (
            "## CONFIGURATION INTERFACE\n\n"
            "- **`enabled`** (bool, default: `true`) — desc\n"
            "- **`disabled`** (bool, default: `false`) — desc\n"
        )
        result = fc.parse_config_interface(spec)
        self.assertIs(result["enabled"], True)
        self.assertIs(result["disabled"], False)

    def test_multiple_keys_in_section(self):
        spec = (
            "## CONFIGURATION INTERFACE\n\n"
            "Some prose.\n\n"
            "- **`a`** (string, default: `x`) — desc-a\n"
            "- **`b`** (int, default: `42`) — desc-b\n"
            "- **`c`** (string) — desc-c\n"
        )
        result = fc.parse_config_interface(spec)
        self.assertEqual(
            set(result.keys()),
            {"a", "b", "c"},
        )
        self.assertEqual(result["a"], "x")
        self.assertEqual(result["b"], 42)
        self.assertIs(result["c"], fc.NO_DEFAULT)

    def test_section_terminates_at_next_h2(self):
        # Keys after the next ## heading must NOT be picked up
        spec = (
            "## CONFIGURATION INTERFACE\n\n"
            "- **`real`** (string, default: `x`) — in-section\n\n"
            "## OUTPUT CONTRACT\n\n"
            "- **`fake`** (string, default: `y`) — not in CI section\n"
        )
        result = fc.parse_config_interface(spec)
        self.assertIn("real", result)
        self.assertNotIn("fake", result)


# ---------------------------------------------------------------------------
# substitute_config_refs
# ---------------------------------------------------------------------------

class TestSubstituteConfigRefs(unittest.TestCase):
    def test_supplied_wins_over_default(self):
        spec = "Hello ${config.who}."
        out = fc.substitute_config_refs(
            spec, {"who": "world"}, {"who": "default-world"},
        )
        self.assertEqual(out, "Hello world.")

    def test_default_used_when_not_supplied(self):
        spec = "Hello ${config.who}."
        out = fc.substitute_config_refs(spec, {}, {"who": "default-world"})
        self.assertEqual(out, "Hello default-world.")

    def test_unresolved_raises(self):
        spec = "Hello ${config.who}."
        with self.assertRaises(fc.FrameworkConfigError) as cm:
            fc.substitute_config_refs(spec, {}, {})
        self.assertEqual(cm.exception.code, "unresolved_reference")
        self.assertIn("who", str(cm.exception))

    def test_multiple_unresolved_dedup(self):
        spec = "${config.a} and ${config.b} and ${config.a}."
        with self.assertRaises(fc.FrameworkConfigError) as cm:
            fc.substitute_config_refs(spec, {}, {})
        msg = str(cm.exception)
        # Both keys reported, no dupe of 'a'
        self.assertIn("a", msg)
        self.assertIn("b", msg)

    def test_none_value_renders_as_null(self):
        spec = "override = ${config.override}"
        out = fc.substitute_config_refs(spec, {"override": None}, {})
        self.assertEqual(out, "override = null")

    def test_no_default_sentinel_is_not_a_default(self):
        # NO_DEFAULT in the declared map means "no default" — substitution
        # should still raise unresolved when the key isn't supplied.
        spec = "x = ${config.x}"
        with self.assertRaises(fc.FrameworkConfigError):
            fc.substitute_config_refs(spec, {}, {"x": fc.NO_DEFAULT})

    def test_no_references_passes_through(self):
        spec = "Just plain text with no ${config} refs."
        out = fc.substitute_config_refs(spec, {}, {})
        self.assertEqual(out, spec)

    def test_int_default_renders_as_str(self):
        spec = "max = ${config.max}"
        out = fc.substitute_config_refs(spec, {}, {"max": 42})
        self.assertEqual(out, "max = 42")


# ---------------------------------------------------------------------------
# compose_framework_spec end-to-end
# ---------------------------------------------------------------------------

class TestComposeFrameworkSpec(unittest.TestCase):
    """Exercises the full compose path with a synthetic framework file
    and a synthetic project + pointer-file fixture.
    """

    def setUp(self):
        # Synthetic project root with a framework_configurations entry
        self.proj_dir = Path(tempfile.mkdtemp(prefix="fc_proj_"))
        (self.proj_dir / "ora-project.json").write_text(json.dumps({
            "nexus": "fc-test-proj",
            "name": "FC Test Project",
            "framework_configurations": [
                {
                    "framework": "synth-fw",
                    "profile_name": "test-profile",
                    "config": {
                        "collection": "fc-test-collection",
                        "override": None,
                    },
                }
            ],
        }), encoding="utf-8")

        # Pointer file pointing at the project
        self.pointer_dir = Path(tempfile.mkdtemp(prefix="fc_ptr_"))
        (self.pointer_dir / "fc-test-proj.json").write_text(json.dumps({
            "nexus": "fc-test-proj",
            "root": str(self.proj_dir),
        }), encoding="utf-8")

        # Synthetic framework file in a temp FRAMEWORKS_DIR
        self.frameworks_dir = Path(tempfile.mkdtemp(prefix="fc_fw_"))
        (self.frameworks_dir / "synth-fw.md").write_text(
            "# Synthetic Framework\n\n"
            "## CONFIGURATION INTERFACE\n\n"
            "- **`collection`** (string, default: `default-coll`) — Where stuff lands.\n"
            "- **`override`** (object or null, default: null) — Optional.\n"
            "- **`docless`** (string) — Must be supplied by every caller.\n\n"
            "## BODY\n\n"
            "Index into ${config.collection}.\n"
            "Override = ${config.override}.\n"
            "Docless = ${config.docless}.\n",
            encoding="utf-8",
        )

        # Patch FRAMEWORKS_DIR for this test class
        self._orig_dir = fc.FRAMEWORKS_DIR
        fc.FRAMEWORKS_DIR = self.frameworks_dir

        # Patch project_registry.get_project to read from our pointer dir
        self._orig_get_project = pr.get_project
        pointer_dir_str = str(self.pointer_dir)

        def _patched_get_project(nexus, pointer_dir=None):
            return self._orig_get_project(nexus, pointer_dir=pointer_dir_str)

        pr.get_project = _patched_get_project

    def tearDown(self):
        fc.FRAMEWORKS_DIR = self._orig_dir
        pr.get_project = self._orig_get_project
        shutil.rmtree(self.proj_dir, ignore_errors=True)
        shutil.rmtree(self.pointer_dir, ignore_errors=True)
        shutil.rmtree(self.frameworks_dir, ignore_errors=True)

    def test_no_project_context_falls_back_to_defaults(self):
        # docless has NO_DEFAULT → must raise without project context
        with self.assertRaises(fc.FrameworkConfigError) as cm:
            fc.compose_framework_spec("synth-fw")
        self.assertEqual(cm.exception.code, "unresolved_reference")
        self.assertIn("docless", str(cm.exception))

    def test_with_project_context_supplies_values(self):
        # Project supplies collection + override but NOT docless → still raises
        with self.assertRaises(fc.FrameworkConfigError) as cm:
            fc.compose_framework_spec(
                "synth-fw", project_nexus="fc-test-proj",
                profile_name="test-profile",
            )
        self.assertEqual(cm.exception.code, "unresolved_reference")
        self.assertIn("docless", str(cm.exception))

    def test_with_full_supply_substitutes_correctly(self):
        # Add docless to the project's config dynamically
        manifest_path = self.proj_dir / "ora-project.json"
        data = json.loads(manifest_path.read_text())
        data["framework_configurations"][0]["config"]["docless"] = "X"
        manifest_path.write_text(json.dumps(data))
        out = fc.compose_framework_spec(
            "synth-fw", project_nexus="fc-test-proj",
            profile_name="test-profile",
        )
        # Verify all three substitutions
        self.assertIn("Index into fc-test-collection.", out)
        self.assertIn("Override = null.", out)
        self.assertIn("Docless = X.", out)

    def test_framework_not_found_raises(self):
        with self.assertRaises(fc.FrameworkConfigError) as cm:
            fc.compose_framework_spec("nonexistent-framework")
        self.assertEqual(cm.exception.code, "framework_not_found")

    def test_project_not_registered_raises(self):
        with self.assertRaises(fc.FrameworkConfigError) as cm:
            fc.compose_framework_spec(
                "synth-fw", project_nexus="ghost-project",
                profile_name="any",
            )
        self.assertEqual(cm.exception.code, "project_not_registered")

    def test_profile_not_declared_raises(self):
        with self.assertRaises(fc.FrameworkConfigError) as cm:
            fc.compose_framework_spec(
                "synth-fw", project_nexus="fc-test-proj",
                profile_name="nonexistent-profile",
            )
        self.assertEqual(cm.exception.code, "profile_not_declared")

    def test_filename_with_dot_md_also_works(self):
        # caller-friendly: accept both bare id and full filename
        manifest_path = self.proj_dir / "ora-project.json"
        data = json.loads(manifest_path.read_text())
        data["framework_configurations"][0]["config"]["docless"] = "X"
        manifest_path.write_text(json.dumps(data))
        out = fc.compose_framework_spec(
            "synth-fw.md", project_nexus="fc-test-proj",
            profile_name="test-profile",
        )
        self.assertIn("Index into fc-test-collection.", out)


if __name__ == "__main__":
    unittest.main()
