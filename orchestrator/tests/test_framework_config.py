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

        # Pointer file pointing at the project. Written through
        # register_project, not by hand: since the 2026-07-25 authority-binding
        # fix (8f1cd428) a pointer must carry the manifest_sha256 it was issued
        # against, and one without it resolves to "no project registered".
        self.pointer_dir = Path(tempfile.mkdtemp(prefix="fc_ptr_"))
        pr.register_project(str(self.proj_dir), pointer_dir=str(self.pointer_dir))

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
        # Editing the manifest breaks the identity the pointer was issued
        # against (8f1cd428). Re-register, as an operator would.
        pr.register_project(str(self.proj_dir), pointer_dir=str(self.pointer_dir))
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
        # Editing the manifest breaks the identity the pointer was issued
        # against (8f1cd428). Re-register, as an operator would.
        pr.register_project(str(self.proj_dir), pointer_dir=str(self.pointer_dir))
        out = fc.compose_framework_spec(
            "synth-fw.md", project_nexus="fc-test-proj",
            profile_name="test-profile",
        )
        self.assertIn("Index into fc-test-collection.", out)


# ---------------------------------------------------------------------------
# splice_extension_overlays + compose end-to-end with overlays (chunk 3)
# ---------------------------------------------------------------------------

class TestSpliceExtensionOverlays(unittest.TestCase):
    def test_single_marker_with_overlay(self):
        spec = (
            "Header.\n\n"
            "<!-- ora-project-extension: foo -->\n\n"
            "Footer.\n"
        )
        out = fc.splice_extension_overlays(spec, {"foo": "## Foo Overlay\n\nBody."})
        self.assertIn("## Foo Overlay", out)
        self.assertIn("Body.", out)
        self.assertNotIn("ora-project-extension", out)

    def test_marker_without_overlay_dropped(self):
        spec = (
            "Header.\n\n"
            "<!-- ora-project-extension: missing -->\n\n"
            "Footer.\n"
        )
        out = fc.splice_extension_overlays(spec, {})
        self.assertNotIn("ora-project-extension", out)
        self.assertIn("Header.", out)
        self.assertIn("Footer.", out)

    def test_multiple_markers_independent_resolution(self):
        spec = (
            "<!-- ora-project-extension: a -->\n"
            "middle\n"
            "<!-- ora-project-extension: b -->\n"
            "end\n"
        )
        out = fc.splice_extension_overlays(
            spec,
            {"a": "AAA", "b": "BBB"},
        )
        self.assertIn("AAA", out)
        self.assertIn("BBB", out)
        # Both markers consumed
        self.assertNotIn("ora-project-extension", out)

    def test_overlay_for_missing_marker_silently_ignored(self):
        # Projects may declare overlays for extension points the current
        # framework spec doesn't expose — that's a forward-compat scenario,
        # not an error.
        spec = "<!-- ora-project-extension: present -->\n"
        out = fc.splice_extension_overlays(
            spec,
            {"present": "P", "absent": "should-not-appear"},
        )
        self.assertIn("P", out)
        self.assertNotIn("absent", out)
        self.assertNotIn("should-not-appear", out)

    def test_no_markers_passes_through(self):
        spec = "Plain text with no markers.\n"
        out = fc.splice_extension_overlays(spec, {"foo": "ignored"})
        self.assertEqual(out, spec)

    def test_idempotent(self):
        spec = "<!-- ora-project-extension: foo -->\n"
        out1 = fc.splice_extension_overlays(spec, {"foo": "F"})
        out2 = fc.splice_extension_overlays(out1, {"foo": "DIFFERENT"})
        # Re-running on already-spliced text is a no-op — the marker
        # was consumed in the first pass.
        self.assertEqual(out1, out2)

    def test_overlay_trailing_whitespace_trimmed(self):
        # Overlay text gets .rstrip()'d so a file with trailing newlines
        # doesn't produce a double-blank-line.
        spec = "<!-- ora-project-extension: a -->"
        out = fc.splice_extension_overlays(spec, {"a": "X\n\n\n\n"})
        # Should not have 4 consecutive newlines after the splice
        self.assertNotIn("\n\n\n\n", out)


class TestComposeWithOverlays(unittest.TestCase):
    """End-to-end compose_framework_spec with overlay files supplied
    via the project's framework_configurations.overlays array."""

    def setUp(self):
        # Synthetic project + overlay file
        self.proj_dir = Path(tempfile.mkdtemp(prefix="fc_overlay_proj_"))
        overlay_dir = self.proj_dir / "framework-overlays" / "synth-fw"
        overlay_dir.mkdir(parents=True)
        (overlay_dir / "post-output.md").write_text(
            "## Project Output Extensions\n\nProject-specific stuff.",
            encoding="utf-8",
        )
        (self.proj_dir / "ora-project.json").write_text(json.dumps({
            "nexus": "overlay-test-proj",
            "name": "Overlay Test",
            "framework_configurations": [
                {
                    "framework": "synth-fw",
                    "profile_name": "test-profile",
                    "config": {"required": "X"},
                    "overlays": [
                        {
                            "extension_point": "post-output-contract",
                            "file": "framework-overlays/synth-fw/post-output.md",
                        }
                    ],
                }
            ],
        }), encoding="utf-8")

        # Pointer file — see the note in TestComposeFrameworkSpec.setUp on why
        # this goes through register_project rather than being written by hand.
        self.pointer_dir = Path(tempfile.mkdtemp(prefix="fc_overlay_ptr_"))
        pr.register_project(str(self.proj_dir), pointer_dir=str(self.pointer_dir))

        # Synthetic framework with the extension marker
        self.frameworks_dir = Path(tempfile.mkdtemp(prefix="fc_overlay_fw_"))
        (self.frameworks_dir / "synth-fw.md").write_text(
            "## CONFIGURATION INTERFACE\n\n"
            "- **`required`** (string) — must supply\n\n"
            "## OUTPUT CONTRACT\n\n"
            "Generic output: ${config.required}.\n\n"
            "<!-- ora-project-extension: post-output-contract -->\n\n"
            "## NEXT SECTION\n\n"
            "More content.\n",
            encoding="utf-8",
        )

        self._orig_dir = fc.FRAMEWORKS_DIR
        fc.FRAMEWORKS_DIR = self.frameworks_dir

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

    def test_compose_splices_overlay_at_marker(self):
        out = fc.compose_framework_spec(
            "synth-fw",
            project_nexus="overlay-test-proj",
            profile_name="test-profile",
        )
        # Config was substituted
        self.assertIn("Generic output: X.", out)
        # Overlay was spliced
        self.assertIn("## Project Output Extensions", out)
        # Marker was consumed
        self.assertNotIn("ora-project-extension", out)

    def test_compose_drops_marker_without_project_context(self):
        # With no project context, the marker is dropped (project-neutral)
        # but the spec still needs `required` from somewhere. Add it as
        # a default to the spec so we can compose project-neutral.
        (self.frameworks_dir / "synth-fw.md").write_text(
            "## CONFIGURATION INTERFACE\n\n"
            "- **`required`** (string, default: `def`) — has a default\n\n"
            "## OUTPUT CONTRACT\n\n"
            "Generic output: ${config.required}.\n\n"
            "<!-- ora-project-extension: post-output-contract -->\n\n"
            "## NEXT SECTION\n",
            encoding="utf-8",
        )
        out = fc.compose_framework_spec("synth-fw")
        self.assertIn("Generic output: def.", out)
        self.assertNotIn("ora-project-extension", out)
        self.assertNotIn("Project Output Extensions", out)

    def test_compose_silent_when_overlay_file_disappears(self):
        # Delete the overlay file AFTER manifest registration —
        # simulates a file getting moved between registration and
        # invocation. The framework should still compose; overlay just
        # missing from output. Diagnostic captured to stay quiet in tests.
        os.unlink(self.proj_dir / "framework-overlays" / "synth-fw" / "post-output.md")

        # Re-create the registered manifest to skip the registration-time
        # existence check (which would now fail). For this test we just
        # exercise the invocation-time gracefulness — so we bypass the
        # parser entirely by injecting a synthetic Project.

        class _StubFC:
            framework = "synth-fw"
            profile_name = "test-profile"
            config = {"required": "X"}

            class _Overlay:
                extension_point = "post-output-contract"
                file = "framework-overlays/synth-fw/post-output.md"

            overlays = [_Overlay()]

        class _StubProject:
            root = self.proj_dir
            nexus = "overlay-test-proj"
            framework_configurations = [_StubFC()]

            def find_framework_configuration(self, fw, prof):
                if fw == "synth-fw" and prof == "test-profile":
                    return _StubFC()
                return None

            def resolve_path(self, rel):
                return self.root / rel

        # Patch get_project to return our stub
        orig_get_project = pr.get_project
        pr.get_project = lambda nexus, pointer_dir=None: _StubProject()
        try:
            with redirect_stdout(io.StringIO()) as captured:
                out = fc.compose_framework_spec(
                    "synth-fw",
                    project_nexus="overlay-test-proj",
                    profile_name="test-profile",
                )
            self.assertIn("Skipping overlay", captured.getvalue())
            # Spec still composes; overlay text just missing
            self.assertIn("Generic output: X.", out)
            self.assertNotIn("ora-project-extension", out)
            self.assertNotIn("Project Output Extensions", out)
        finally:
            pr.get_project = orig_get_project


if __name__ == "__main__":
    unittest.main()
