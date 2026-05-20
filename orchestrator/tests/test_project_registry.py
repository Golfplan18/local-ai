#!/usr/bin/env python3
"""Tests for project_registry.py — Ora's project plugin convention."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
ROOT = ORCHESTRATOR.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ORCHESTRATOR))

from orchestrator import project_registry as pr  # noqa: E402


# Tiny in-tree tool scripts used by invocation tests. Written into a temp
# project directory in setUp.
_ECHO_ARGV_TOOL = """\
#!/usr/bin/env python3
\"\"\"argv-stdout-json: echoes argv as a JSON list on stdout.\"\"\"
import json, sys
print(json.dumps({"argv": sys.argv[1:]}))
"""

_ECHO_STDIN_TOOL = """\
#!/usr/bin/env python3
\"\"\"stdin-stdout-json: echoes parsed stdin JSON back as 'received'.\"\"\"
import json, sys
data = json.loads(sys.stdin.read() or "{}")
print(json.dumps({"received": data}))
"""

_NO_OUTPUT_TOOL = """\
#!/usr/bin/env python3
\"\"\"argv-stdout-json: emits nothing on stdout. Should yield None.\"\"\"
"""

_FAILING_TOOL = """\
#!/usr/bin/env python3
\"\"\"Exits non-zero with a stderr message.\"\"\"
import sys
sys.stderr.write("intentional failure for test\\n")
sys.exit(7)
"""

_BAD_JSON_TOOL = """\
#!/usr/bin/env python3
\"\"\"Emits non-JSON on stdout.\"\"\"
print("this is not json {{{")
"""

_SLASH_OUTPUT = """\
#!/usr/bin/env python3
\"\"\"Slash command: emits free-form markdown.\"\"\"
import sys
print("# Hello")
print("Args:", *sys.argv[1:])
"""


# ---------------------------------------------------------------------------
# Manifest parsing tests (no chromadb / no subprocess required)
# ---------------------------------------------------------------------------


class TestManifestParsing(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="proj_reg_test_")
        self.root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_manifest(self, data):
        (self.root / pr.MANIFEST_FILENAME).write_text(json.dumps(data), encoding="utf-8")

    def test_minimal_manifest(self):
        self._write_manifest({"nexus": "test-proj", "name": "Test"})
        p = pr.load_project_at(self.root)
        self.assertEqual(p.nexus, "test-proj")
        self.assertEqual(p.name, "Test")
        self.assertEqual(p.tools, {})
        self.assertEqual(p.slash_commands, {})
        self.assertEqual(p.frameworks, [])

    def test_full_manifest(self):
        self._write_manifest({
            "nexus": "main-street-independent",
            "name": "Main Street Independent",
            "version": "0.1.0",
            "description": "AI-driven distributional-honesty news publication",
            "tools": [
                {"name": "news-index", "command": ["python3", "tools/news_index.py"]},
                {
                    "name": "news-related-find",
                    "command": ["python3", "tools/news_related.py"],
                    "interface": "stdin-stdout-json",
                    "description": "Three-signal retrieval",
                },
            ],
            "slash_commands": [
                {"name": "publish-cycle", "command": ["python3", "scripts/publish.py"]},
            ],
            "frameworks": ["frameworks/news-article-generator.md"],
            "peds": ["peds/historical-forward.md"],
            "workflow_specs": ["workflow-specs/historical-forward-run.md"],
            "chromadb_collections": ["msi_news_articles"],
        })
        p = pr.load_project_at(self.root)
        self.assertEqual(p.nexus, "main-street-independent")
        self.assertEqual(set(p.tools.keys()), {"news-index", "news-related-find"})
        self.assertEqual(p.tools["news-related-find"].interface, "stdin-stdout-json")
        self.assertEqual(p.tools["news-related-find"].description, "Three-signal retrieval")
        self.assertEqual(set(p.slash_commands.keys()), {"publish-cycle"})
        self.assertEqual(p.frameworks, ["frameworks/news-article-generator.md"])
        self.assertEqual(p.chromadb_collections, ["msi_news_articles"])

    def test_missing_manifest_file(self):
        with self.assertRaises(pr.ManifestError) as ctx:
            pr.load_project_at(self.root)
        self.assertIn("No manifest", str(ctx.exception))

    def test_invalid_json(self):
        (self.root / pr.MANIFEST_FILENAME).write_text("{ not valid json", encoding="utf-8")
        with self.assertRaises(pr.ManifestError) as ctx:
            pr.load_project_at(self.root)
        self.assertIn("invalid JSON", str(ctx.exception))

    def test_top_level_not_object(self):
        (self.root / pr.MANIFEST_FILENAME).write_text("[]", encoding="utf-8")
        with self.assertRaises(pr.ManifestError):
            pr.load_project_at(self.root)

    def test_missing_nexus(self):
        self._write_manifest({"name": "Test"})
        with self.assertRaises(pr.ManifestError) as ctx:
            pr.load_project_at(self.root)
        self.assertIn("nexus", str(ctx.exception))

    def test_invalid_nexus_uppercase(self):
        self._write_manifest({"nexus": "Test-Proj", "name": "Test"})
        with self.assertRaises(pr.ManifestError):
            pr.load_project_at(self.root)

    def test_invalid_nexus_special_chars(self):
        self._write_manifest({"nexus": "test/proj", "name": "Test"})
        with self.assertRaises(pr.ManifestError):
            pr.load_project_at(self.root)

    def test_missing_name(self):
        self._write_manifest({"nexus": "test"})
        with self.assertRaises(pr.ManifestError) as ctx:
            pr.load_project_at(self.root)
        self.assertIn("name", str(ctx.exception))

    def test_tool_missing_command(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "tools": [{"name": "broken"}],
        })
        with self.assertRaises(pr.ManifestError):
            pr.load_project_at(self.root)

    def test_tool_unknown_interface(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "tools": [{"name": "t", "command": ["ls"], "interface": "rpc-bizarre"}],
        })
        with self.assertRaises(pr.ManifestError):
            pr.load_project_at(self.root)

    def test_tool_duplicate_name(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "tools": [
                {"name": "t", "command": ["ls"]},
                {"name": "t", "command": ["pwd"]},
            ],
        })
        with self.assertRaises(pr.ManifestError):
            pr.load_project_at(self.root)

    def test_slash_command_with_leading_slash_rejected(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "slash_commands": [{"name": "/publish", "command": ["ls"]}],
        })
        with self.assertRaises(pr.ManifestError) as ctx:
            pr.load_project_at(self.root)
        self.assertIn("leading slash", str(ctx.exception))

    def test_resolve_path_relative(self):
        self._write_manifest({"nexus": "test", "name": "Test"})
        p = pr.load_project_at(self.root)
        resolved = p.resolve_path("tools/news_index.py")
        self.assertTrue(resolved.is_absolute())
        self.assertTrue(str(resolved).endswith("tools/news_index.py"))

    def test_resolve_path_absolute(self):
        self._write_manifest({"nexus": "test", "name": "Test"})
        p = pr.load_project_at(self.root)
        resolved = p.resolve_path("/etc/hosts")
        self.assertEqual(str(resolved), "/etc/hosts")


# ---------------------------------------------------------------------------
# Capability-slot parsing tests (Plugin Convention §12)
# ---------------------------------------------------------------------------


class TestCapabilitySlotParsing(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="proj_reg_slot_test_")
        self.root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_manifest(self, data):
        (self.root / pr.MANIFEST_FILENAME).write_text(json.dumps(data), encoding="utf-8")

    def _load_quietly(self):
        """Load the project, capturing parser diagnostics to keep test output clean."""
        import io
        from contextlib import redirect_stdout
        with redirect_stdout(io.StringIO()):
            return pr.load_project_at(self.root)

    def test_no_capability_slots_field(self):
        self._write_manifest({"nexus": "test", "name": "Test"})
        p = pr.load_project_at(self.root)
        self.assertEqual(p.capability_slots, {})

    def test_minimal_capability_slot(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "capability_slots": [
                {
                    "name": "image_generates_cartoon",
                    "contract": {
                        "summary": "Generate an editorial cartoon.",
                        "required_inputs": [{"name": "prompt", "type": "text"}],
                        "output": {"type": "image-bytes"},
                        "execution_pattern": "sync",
                    },
                }
            ],
        })
        p = pr.load_project_at(self.root)
        self.assertIn("image_generates_cartoon", p.capability_slots)
        slot = p.capability_slots["image_generates_cartoon"]
        self.assertIsInstance(slot, pr.ProjectCapabilitySlot)
        self.assertEqual(slot.routing, {})

    def test_full_capability_slot_with_routing(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "capability_slots": [
                {
                    "name": "image_generates_cartoon",
                    "contract": {
                        "summary": "Generate an editorial cartoon.",
                        "required_inputs": [{"name": "prompt", "type": "text"}],
                        "optional_inputs": [
                            {"name": "aspect_ratio", "type": "enum", "default": "1:1"}
                        ],
                        "output": {"type": "image-bytes"},
                        "execution_pattern": "sync",
                        "common_errors": [{"code": "model_unavailable"}],
                    },
                    "routing": {
                        "inherits": "image_generates",
                        "exclude_inherited": ["local-diffusers"],
                        "append_fallback": ["civitai-hector-lora-v1"],
                    },
                }
            ],
        })
        p = pr.load_project_at(self.root)
        slot = p.capability_slots["image_generates_cartoon"]
        self.assertEqual(slot.routing["inherits"], "image_generates")
        self.assertEqual(slot.routing["exclude_inherited"], ["local-diffusers"])
        self.assertEqual(slot.routing["append_fallback"], ["civitai-hector-lora-v1"])

    def test_capability_slots_top_level_not_array_raises(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "capability_slots": "not-an-array",
        })
        with self.assertRaises(pr.ManifestError) as ctx:
            pr.load_project_at(self.root)
        self.assertIn("must be an array", str(ctx.exception))

    def test_slot_missing_name_skipped(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "capability_slots": [{"contract": {}}],
        })
        p = self._load_quietly()
        self.assertEqual(p.capability_slots, {})

    def test_slot_invalid_name_uppercase_skipped(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "capability_slots": [
                {"name": "Image_Generates", "contract": {}},
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.capability_slots, {})

    def test_slot_invalid_name_hyphen_skipped(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "capability_slots": [
                {"name": "image-generates", "contract": {}},
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.capability_slots, {})

    def test_slot_missing_contract_skipped(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "capability_slots": [{"name": "image_generates_cartoon"}],
        })
        p = self._load_quietly()
        self.assertEqual(p.capability_slots, {})

    def test_slot_preferred_in_routing_skipped(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "capability_slots": [
                {
                    "name": "image_generates_cartoon",
                    "contract": {"summary": "x"},
                    "routing": {"preferred": "some-provider"},
                }
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.capability_slots, {})

    def test_slot_fallback_in_routing_skipped(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "capability_slots": [
                {
                    "name": "image_generates_cartoon",
                    "contract": {"summary": "x"},
                    "routing": {"fallback": ["x", "y"]},
                }
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.capability_slots, {})

    def test_slot_unknown_routing_key_skipped(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "capability_slots": [
                {
                    "name": "image_generates_cartoon",
                    "contract": {"summary": "x"},
                    "routing": {"prefer_local": True},
                }
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.capability_slots, {})

    def test_slot_invalid_input_type_skipped(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "capability_slots": [
                {
                    "name": "image_generates_cartoon",
                    "contract": {
                        "required_inputs": [{"name": "x", "type": "blob-bizarre"}],
                    },
                }
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.capability_slots, {})

    def test_slot_invalid_execution_pattern_skipped(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "capability_slots": [
                {
                    "name": "image_generates_cartoon",
                    "contract": {
                        "summary": "x",
                        "execution_pattern": "interpretive-dance",
                    },
                }
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.capability_slots, {})

    def test_one_malformed_slot_others_load(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "capability_slots": [
                {"name": "image_generates_cartoon", "contract": {"summary": "good"}},
                {"name": "broken", "contract": {}, "routing": {"preferred": "x"}},
                {"name": "video_generates_intro", "contract": {"summary": "also good"}},
            ],
        })
        p = self._load_quietly()
        self.assertEqual(
            set(p.capability_slots.keys()),
            {"image_generates_cartoon", "video_generates_intro"},
        )

    def test_duplicate_slot_name_keeps_first(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "capability_slots": [
                {"name": "image_generates_cartoon", "contract": {"summary": "first"}},
                {"name": "image_generates_cartoon", "contract": {"summary": "second"}},
            ],
        })
        p = self._load_quietly()
        self.assertEqual(len(p.capability_slots), 1)
        self.assertEqual(
            p.capability_slots["image_generates_cartoon"].contract["summary"], "first"
        )

    def test_slot_routing_optional(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "capability_slots": [
                {"name": "image_generates_cartoon", "contract": {"summary": "x"}},
            ],
        })
        p = pr.load_project_at(self.root)
        slot = p.capability_slots["image_generates_cartoon"]
        self.assertEqual(slot.routing, {})

    def test_malformed_slot_does_not_block_other_manifest_fields(self):
        """A malformed capability_slot must not affect tools/slash_commands/etc."""
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "tools": [{"name": "real-tool", "command": ["python3", "x.py"]}],
            "capability_slots": [
                {"name": "broken", "contract": {}, "routing": {"preferred": "x"}},
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.capability_slots, {})
        self.assertIn("real-tool", p.tools)


# ---------------------------------------------------------------------------
# Pointer-file lifecycle tests
# ---------------------------------------------------------------------------


class TestPointerFileLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="proj_reg_test_")
        self.pointer_dir = os.path.join(self.tmpdir, "pointers")
        self.proj_root = Path(self.tmpdir) / "myproject"
        self.proj_root.mkdir()
        (self.proj_root / pr.MANIFEST_FILENAME).write_text(
            json.dumps({"nexus": "myproject", "name": "MyProject"}), encoding="utf-8"
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_register_writes_pointer(self):
        p = pr.register_project(self.proj_root, pointer_dir=self.pointer_dir)
        self.assertEqual(p.nexus, "myproject")
        pf = Path(self.pointer_dir) / "myproject.json"
        self.assertTrue(pf.is_file())
        data = json.loads(pf.read_text())
        self.assertEqual(data["nexus"], "myproject")
        self.assertEqual(Path(data["root"]).resolve(), self.proj_root.resolve())

    def test_register_rejects_invalid_manifest(self):
        bad = Path(self.tmpdir) / "bad"
        bad.mkdir()
        (bad / pr.MANIFEST_FILENAME).write_text("nope", encoding="utf-8")
        with self.assertRaises(pr.ManifestError):
            pr.register_project(bad, pointer_dir=self.pointer_dir)

    def test_get_project_round_trip(self):
        pr.register_project(self.proj_root, pointer_dir=self.pointer_dir)
        p = pr.get_project("myproject", pointer_dir=self.pointer_dir)
        self.assertIsNotNone(p)
        self.assertEqual(p.nexus, "myproject")

    def test_get_project_returns_none_for_missing(self):
        self.assertIsNone(pr.get_project("nonexistent", pointer_dir=self.pointer_dir))

    def test_list_projects_sorted(self):
        # Build a second project alongside myproject.
        other = Path(self.tmpdir) / "alpha-project"
        other.mkdir()
        (other / pr.MANIFEST_FILENAME).write_text(
            json.dumps({"nexus": "alpha-project", "name": "Alpha"}), encoding="utf-8"
        )
        pr.register_project(self.proj_root, pointer_dir=self.pointer_dir)
        pr.register_project(other, pointer_dir=self.pointer_dir)
        projects = pr.list_projects(pointer_dir=self.pointer_dir)
        self.assertEqual([p.nexus for p in projects], ["alpha-project", "myproject"])

    def test_list_projects_skips_bad_pointer(self):
        pr.register_project(self.proj_root, pointer_dir=self.pointer_dir)
        bad_pf = Path(self.pointer_dir) / "broken.json"
        bad_pf.write_text("{not json", encoding="utf-8")
        projects = pr.list_projects(pointer_dir=self.pointer_dir)
        # myproject still loads; broken pointer skipped silently (with stderr msg).
        self.assertEqual([p.nexus for p in projects], ["myproject"])

    def test_list_projects_skips_pointer_to_missing_manifest(self):
        # Pointer file with valid JSON but the project root has no manifest.
        os.makedirs(self.pointer_dir, exist_ok=True)
        pf = Path(self.pointer_dir) / "ghost.json"
        pf.write_text(json.dumps({"nexus": "ghost", "root": "/nowhere/at/all"}),
                      encoding="utf-8")
        self.assertEqual(pr.list_projects(pointer_dir=self.pointer_dir), [])

    def test_list_projects_skips_nexus_mismatch(self):
        os.makedirs(self.pointer_dir, exist_ok=True)
        pf = Path(self.pointer_dir) / "myproject.json"
        # Pointer claims a different nexus than the manifest.
        pf.write_text(
            json.dumps({"nexus": "wrong-nexus", "root": str(self.proj_root)}),
            encoding="utf-8",
        )
        self.assertEqual(pr.list_projects(pointer_dir=self.pointer_dir), [])

    def test_unregister(self):
        pr.register_project(self.proj_root, pointer_dir=self.pointer_dir)
        self.assertTrue(pr.unregister_project("myproject", pointer_dir=self.pointer_dir))
        self.assertFalse(pr.unregister_project("myproject", pointer_dir=self.pointer_dir))
        self.assertIsNone(pr.get_project("myproject", pointer_dir=self.pointer_dir))

    def test_register_idempotent_overwrites(self):
        pr.register_project(self.proj_root, pointer_dir=self.pointer_dir)
        # Move the project root, re-register; pointer should follow.
        moved = Path(self.tmpdir) / "moved"
        shutil.move(str(self.proj_root), str(moved))
        pr.register_project(moved, pointer_dir=self.pointer_dir)
        p = pr.get_project("myproject", pointer_dir=self.pointer_dir)
        self.assertEqual(p.root, moved.resolve())


# ---------------------------------------------------------------------------
# Tool invocation tests (real subprocesses against in-tree scripts)
# ---------------------------------------------------------------------------


class TestToolInvocation(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="proj_reg_test_")
        self.pointer_dir = os.path.join(self.tmpdir, "pointers")
        self.proj_root = Path(self.tmpdir) / "myproject"
        (self.proj_root / "tools").mkdir(parents=True)

        for name, body in [
            ("echo_argv.py", _ECHO_ARGV_TOOL),
            ("echo_stdin.py", _ECHO_STDIN_TOOL),
            ("no_output.py", _NO_OUTPUT_TOOL),
            ("failing.py", _FAILING_TOOL),
            ("bad_json.py", _BAD_JSON_TOOL),
            ("slash_output.py", _SLASH_OUTPUT),
        ]:
            (self.proj_root / "tools" / name).write_text(body, encoding="utf-8")

        manifest = {
            "nexus": "myproject", "name": "MyProject",
            "tools": [
                {"name": "echo-argv", "command": ["python3", "tools/echo_argv.py"]},
                {"name": "echo-stdin",
                 "command": ["python3", "tools/echo_stdin.py"],
                 "interface": "stdin-stdout-json"},
                {"name": "silent", "command": ["python3", "tools/no_output.py"]},
                {"name": "failing", "command": ["python3", "tools/failing.py"]},
                {"name": "bad-json", "command": ["python3", "tools/bad_json.py"]},
                {"name": "missing-binary", "command": ["does-not-exist-on-path"]},
            ],
            "slash_commands": [
                {"name": "say-hi", "command": ["python3", "tools/slash_output.py"]},
            ],
        }
        (self.proj_root / pr.MANIFEST_FILENAME).write_text(
            json.dumps(manifest), encoding="utf-8",
        )
        pr.register_project(self.proj_root, pointer_dir=self.pointer_dir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_argv_stdout_passes_args(self):
        result = pr.invoke_project_tool(
            "myproject", "echo-argv", args=["one", "two"],
            pointer_dir=self.pointer_dir,
        )
        self.assertEqual(result, {"argv": ["one", "two"]})

    def test_stdin_stdout_passes_json(self):
        result = pr.invoke_project_tool(
            "myproject", "echo-stdin", stdin_json={"hello": "world", "n": 42},
            pointer_dir=self.pointer_dir,
        )
        self.assertEqual(result, {"received": {"hello": "world", "n": 42}})

    def test_silent_tool_returns_none(self):
        result = pr.invoke_project_tool(
            "myproject", "silent", pointer_dir=self.pointer_dir,
        )
        self.assertIsNone(result)

    def test_unknown_project_raises(self):
        with self.assertRaises(pr.ProjectNotFoundError):
            pr.invoke_project_tool("nope", "echo-argv", pointer_dir=self.pointer_dir)

    def test_unknown_tool_raises(self):
        with self.assertRaises(pr.ToolNotFoundError):
            pr.invoke_project_tool("myproject", "nope", pointer_dir=self.pointer_dir)

    def test_failing_tool_raises_with_exit_code(self):
        with self.assertRaises(pr.ToolInvocationError) as ctx:
            pr.invoke_project_tool("myproject", "failing", pointer_dir=self.pointer_dir)
        self.assertEqual(ctx.exception.exit_code, 7)
        self.assertIn("intentional failure", ctx.exception.stderr)

    def test_bad_json_raises(self):
        with self.assertRaises(pr.ToolInvocationError) as ctx:
            pr.invoke_project_tool("myproject", "bad-json", pointer_dir=self.pointer_dir)
        self.assertIn("invalid JSON", str(ctx.exception))

    def test_missing_binary_raises(self):
        with self.assertRaises(pr.ToolInvocationError) as ctx:
            pr.invoke_project_tool(
                "myproject", "missing-binary", pointer_dir=self.pointer_dir,
            )
        self.assertIn("not found", str(ctx.exception).lower())

    def test_extra_env_passed(self):
        # Re-use echo-argv but verify the env via a separate inline tool.
        env_tool = self.proj_root / "tools" / "echo_env.py"
        env_tool.write_text(
            "import json, os, sys\n"
            "print(json.dumps({'val': os.environ.get('TEST_VAR')}))\n",
            encoding="utf-8",
        )
        # Re-register to pick up new tool.
        manifest = json.loads((self.proj_root / pr.MANIFEST_FILENAME).read_text())
        manifest["tools"].append({
            "name": "echo-env", "command": ["python3", "tools/echo_env.py"],
        })
        (self.proj_root / pr.MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")
        result = pr.invoke_project_tool(
            "myproject", "echo-env", extra_env={"TEST_VAR": "hello"},
            pointer_dir=self.pointer_dir,
        )
        self.assertEqual(result, {"val": "hello"})


# ---------------------------------------------------------------------------
# Slash command invocation
# ---------------------------------------------------------------------------


class TestSlashCommandInvocation(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="proj_reg_test_")
        self.pointer_dir = os.path.join(self.tmpdir, "pointers")
        self.proj_root = Path(self.tmpdir) / "myproject"
        (self.proj_root / "tools").mkdir(parents=True)
        (self.proj_root / "tools" / "slash.py").write_text(_SLASH_OUTPUT, encoding="utf-8")
        (self.proj_root / pr.MANIFEST_FILENAME).write_text(
            json.dumps({
                "nexus": "myproject", "name": "MyProject",
                "slash_commands": [
                    {"name": "say-hi", "command": ["python3", "tools/slash.py"]},
                ],
            }), encoding="utf-8",
        )
        pr.register_project(self.proj_root, pointer_dir=self.pointer_dir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_returns_stdout_string(self):
        out = pr.invoke_project_slash_command(
            "myproject", "say-hi", args=["alpha", "beta"],
            pointer_dir=self.pointer_dir,
        )
        self.assertIn("# Hello", out)
        self.assertIn("alpha", out)
        self.assertIn("beta", out)

    def test_unknown_project_returns_error_string(self):
        out = pr.invoke_project_slash_command(
            "nope", "say-hi", pointer_dir=self.pointer_dir,
        )
        self.assertIn("[Slash command error", out)

    def test_unknown_command_returns_error_string(self):
        out = pr.invoke_project_slash_command(
            "myproject", "nope", pointer_dir=self.pointer_dir,
        )
        self.assertIn("[Slash command error", out)

    def test_find_project_for_slash_command(self):
        p = pr.find_project_for_slash_command("say-hi", pointer_dir=self.pointer_dir)
        self.assertIsNotNone(p)
        self.assertEqual(p.nexus, "myproject")

    def test_find_project_for_slash_command_not_found(self):
        p = pr.find_project_for_slash_command("nope", pointer_dir=self.pointer_dir)
        self.assertIsNone(p)


class TestThemeParsing(unittest.TestCase):
    """Tests for Plugin Convention §13 — project-defined themes."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="proj_reg_theme_test_")
        self.root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_manifest(self, data):
        (self.root / pr.MANIFEST_FILENAME).write_text(json.dumps(data), encoding="utf-8")

    def _write_theme_assets(self, directory, *, include_css=True, include_manifest=True):
        """Create a theme assets directory under self.root with the
        files §13's validation requires (theme.css + manifest.json).
        Either file can be omitted to test asset-incomplete behavior.
        """
        asset_dir = self.root / directory
        asset_dir.mkdir(parents=True, exist_ok=True)
        if include_css:
            (asset_dir / "theme.css").write_text("/* test theme */", encoding="utf-8")
        if include_manifest:
            (asset_dir / "manifest.json").write_text(
                json.dumps({"name": "Test Theme", "version": "1.0.0"}),
                encoding="utf-8",
            )
        return asset_dir

    def _load_quietly(self):
        import io
        from contextlib import redirect_stdout
        with redirect_stdout(io.StringIO()):
            return pr.load_project_at(self.root)

    # --- Happy paths ----------------------------------------------------

    def test_no_themes_field(self):
        self._write_manifest({"nexus": "test", "name": "Test"})
        p = pr.load_project_at(self.root)
        self.assertEqual(p.themes, {})

    def test_minimal_theme(self):
        self._write_theme_assets("themes/main-street-independent")
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "themes": [
                {
                    "id": "main-street-independent",
                    "name": "Main Street Independent",
                    "directory": "themes/main-street-independent",
                }
            ],
        })
        p = pr.load_project_at(self.root)
        self.assertIn("main-street-independent", p.themes)
        theme = p.themes["main-street-independent"]
        self.assertIsInstance(theme, pr.ProjectTheme)
        self.assertEqual(theme.name, "Main Street Independent")
        self.assertEqual(theme.directory, "themes/main-street-independent")

    def test_multiple_themes(self):
        self._write_theme_assets("themes/alpha")
        self._write_theme_assets("themes/beta")
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "themes": [
                {"id": "alpha", "name": "Alpha", "directory": "themes/alpha"},
                {"id": "beta", "name": "Beta", "directory": "themes/beta"},
            ],
        })
        p = pr.load_project_at(self.root)
        self.assertEqual(set(p.themes.keys()), {"alpha", "beta"})

    # --- Top-level validation -------------------------------------------

    def test_themes_top_level_not_array_raises(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "themes": "not-an-array",
        })
        with self.assertRaises(pr.ManifestError):
            pr.load_project_at(self.root)

    # --- Per-entry validation (graceful skip) ---------------------------

    def test_entry_not_object_skipped(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "themes": ["not-an-object"],
        })
        p = self._load_quietly()
        self.assertEqual(p.themes, {})

    def test_missing_id_skipped(self):
        self._write_theme_assets("themes/anon")
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "themes": [{"name": "Anon", "directory": "themes/anon"}],
        })
        p = self._load_quietly()
        self.assertEqual(p.themes, {})

    def test_invalid_id_regex_skipped(self):
        self._write_theme_assets("themes/anon")
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "themes": [
                {"id": "Has-Capitals", "name": "Anon", "directory": "themes/anon"}
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.themes, {})

    def test_reserved_default_id_skipped(self):
        self._write_theme_assets("themes/default")
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "themes": [
                {"id": "default", "name": "Default Override Attempt",
                 "directory": "themes/default"}
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.themes, {})

    def test_missing_name_skipped(self):
        self._write_theme_assets("themes/alpha")
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "themes": [{"id": "alpha", "directory": "themes/alpha"}],
        })
        p = self._load_quietly()
        self.assertEqual(p.themes, {})

    def test_missing_directory_skipped(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "themes": [{"id": "alpha", "name": "Alpha"}],
        })
        p = self._load_quietly()
        self.assertEqual(p.themes, {})

    def test_absolute_directory_rejected(self):
        # Even if the absolute path exists, the manifest must use a
        # project-root-relative directory.
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "themes": [
                {"id": "alpha", "name": "Alpha", "directory": "/absolute/path"}
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.themes, {})

    def test_missing_asset_directory_skipped(self):
        # directory looks valid but doesn't exist on disk
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "themes": [
                {"id": "alpha", "name": "Alpha", "directory": "themes/nonexistent"}
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.themes, {})

    def test_missing_theme_css_skipped(self):
        self._write_theme_assets("themes/alpha", include_css=False)
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "themes": [
                {"id": "alpha", "name": "Alpha", "directory": "themes/alpha"}
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.themes, {})

    def test_missing_manifest_json_skipped(self):
        self._write_theme_assets("themes/alpha", include_manifest=False)
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "themes": [
                {"id": "alpha", "name": "Alpha", "directory": "themes/alpha"}
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.themes, {})

    # --- Duplicate handling ---------------------------------------------

    def test_duplicate_id_keeps_first(self):
        self._write_theme_assets("themes/alpha")
        self._write_theme_assets("themes/alpha-too")
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "themes": [
                {"id": "alpha", "name": "First", "directory": "themes/alpha"},
                {"id": "alpha", "name": "Second", "directory": "themes/alpha-too"},
            ],
        })
        p = self._load_quietly()
        self.assertEqual(set(p.themes.keys()), {"alpha"})
        self.assertEqual(p.themes["alpha"].name, "First")

    # --- Graceful degradation -------------------------------------------

    def test_malformed_one_skipped_others_kept(self):
        self._write_theme_assets("themes/good")
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "themes": [
                {"id": "good", "name": "Good", "directory": "themes/good"},
                {"id": "bad", "name": "Bad", "directory": "themes/nonexistent"},
            ],
        })
        p = self._load_quietly()
        self.assertEqual(set(p.themes.keys()), {"good"})

    def test_theme_parse_error_doesnt_break_other_manifest_fields(self):
        # Tools and themes are independent; a bad theme entry should not
        # prevent tools from loading.
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "tools": [
                {"name": "my-tool", "command": ["python3", "tools/x.py"]}
            ],
            "themes": [
                {"id": "bad", "name": "Bad", "directory": "themes/nonexistent"}
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.themes, {})
        self.assertIn("my-tool", p.tools)


class TestFrameworkConfigurationParsing(unittest.TestCase):
    """Tests for Plugin Convention §14 — project-defined framework
    configurations."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="proj_reg_fc_test_")
        self.root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_manifest(self, data):
        (self.root / pr.MANIFEST_FILENAME).write_text(
            json.dumps(data), encoding="utf-8"
        )

    def _write_overlay_file(self, relative_path, content="# overlay"):
        full = self.root / relative_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")

    def _load_quietly(self):
        import io
        from contextlib import redirect_stdout
        with redirect_stdout(io.StringIO()):
            return pr.load_project_at(self.root)

    # --- Happy paths ----------------------------------------------------

    def test_no_framework_configurations_field(self):
        self._write_manifest({"nexus": "test", "name": "Test"})
        p = pr.load_project_at(self.root)
        self.assertEqual(p.framework_configurations, [])

    def test_minimal_framework_configuration(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "framework_configurations": [
                {
                    "framework": "document-processing",
                    "profile_name": "msi-editorial-research",
                }
            ],
        })
        p = pr.load_project_at(self.root)
        self.assertEqual(len(p.framework_configurations), 1)
        fc = p.framework_configurations[0]
        self.assertIsInstance(fc, pr.ProjectFrameworkConfiguration)
        self.assertEqual(fc.framework, "document-processing")
        self.assertEqual(fc.profile_name, "msi-editorial-research")
        self.assertEqual(fc.config, {})
        self.assertEqual(fc.overlays, [])

    def test_full_framework_configuration_with_config_and_overlays(self):
        self._write_overlay_file(
            "framework-overlays/document-processing/post-output.md",
            "## Project-Specific Output\n\nFoo.\n",
        )
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "framework_configurations": [
                {
                    "framework": "document-processing",
                    "profile_name": "msi-editorial-research",
                    "config": {
                        "chromadb_collection": "msi-research",
                        "output_type_override": {
                            "from": "incubator", "to": "msi-research",
                        },
                        "voice_property_name": "source_voice",
                    },
                    "overlays": [
                        {
                            "extension_point": "post-output-contract",
                            "file": "framework-overlays/document-processing/post-output.md",
                        }
                    ],
                }
            ],
        })
        p = pr.load_project_at(self.root)
        fc = p.framework_configurations[0]
        self.assertEqual(fc.config["chromadb_collection"], "msi-research")
        self.assertEqual(fc.config["voice_property_name"], "source_voice")
        self.assertEqual(len(fc.overlays), 1)
        ov = fc.overlays[0]
        self.assertIsInstance(ov, pr.ProjectFrameworkOverlay)
        self.assertEqual(ov.extension_point, "post-output-contract")

    def test_find_framework_configuration_helper(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "framework_configurations": [
                {"framework": "fw-a", "profile_name": "p1"},
                {"framework": "fw-a", "profile_name": "p2"},
                {"framework": "fw-b", "profile_name": "p1"},
            ],
        })
        p = pr.load_project_at(self.root)
        self.assertEqual(len(p.framework_configurations), 3)
        # Same profile name OK across different frameworks
        fc1 = p.find_framework_configuration("fw-a", "p1")
        fc2 = p.find_framework_configuration("fw-b", "p1")
        self.assertIsNotNone(fc1)
        self.assertIsNotNone(fc2)
        self.assertEqual(fc1.framework, "fw-a")
        self.assertEqual(fc2.framework, "fw-b")
        # Non-existent → None
        self.assertIsNone(p.find_framework_configuration("fw-a", "nope"))
        self.assertIsNone(p.find_framework_configuration("nope", "p1"))

    # --- Top-level validation -------------------------------------------

    def test_top_level_not_array_raises(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "framework_configurations": "not-an-array",
        })
        with self.assertRaises(pr.ManifestError):
            pr.load_project_at(self.root)

    # --- Per-entry validation (graceful skip) ---------------------------

    def test_entry_not_object_skipped(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "framework_configurations": ["not-an-object"],
        })
        p = self._load_quietly()
        self.assertEqual(p.framework_configurations, [])

    def test_missing_framework_skipped(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "framework_configurations": [{"profile_name": "anon"}],
        })
        p = self._load_quietly()
        self.assertEqual(p.framework_configurations, [])

    def test_missing_profile_name_skipped(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "framework_configurations": [{"framework": "fw"}],
        })
        p = self._load_quietly()
        self.assertEqual(p.framework_configurations, [])

    def test_invalid_profile_name_regex_skipped(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "framework_configurations": [
                {"framework": "fw", "profile_name": "Has-Capitals"}
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.framework_configurations, [])

    def test_config_not_object_skipped(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "framework_configurations": [
                {"framework": "fw", "profile_name": "p1", "config": "string"}
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.framework_configurations, [])

    def test_overlays_not_array_skipped(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "framework_configurations": [
                {"framework": "fw", "profile_name": "p1", "overlays": "x"}
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.framework_configurations, [])

    def test_overlay_missing_extension_point_skipped(self):
        self._write_overlay_file("overlays/x.md")
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "framework_configurations": [
                {
                    "framework": "fw", "profile_name": "p1",
                    "overlays": [{"file": "overlays/x.md"}],
                }
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.framework_configurations, [])

    def test_overlay_invalid_extension_point_regex_skipped(self):
        self._write_overlay_file("overlays/x.md")
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "framework_configurations": [
                {
                    "framework": "fw", "profile_name": "p1",
                    "overlays": [
                        {"extension_point": "Has Spaces", "file": "overlays/x.md"}
                    ],
                }
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.framework_configurations, [])

    def test_overlay_missing_file_skipped(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "framework_configurations": [
                {
                    "framework": "fw", "profile_name": "p1",
                    "overlays": [{"extension_point": "ep1"}],
                }
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.framework_configurations, [])

    def test_overlay_absolute_file_path_skipped(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "framework_configurations": [
                {
                    "framework": "fw", "profile_name": "p1",
                    "overlays": [
                        {"extension_point": "ep1", "file": "/absolute/path.md"}
                    ],
                }
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.framework_configurations, [])

    def test_overlay_nonexistent_file_skipped(self):
        # file path is valid + relative, but doesn't exist on disk
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "framework_configurations": [
                {
                    "framework": "fw", "profile_name": "p1",
                    "overlays": [
                        {"extension_point": "ep1", "file": "overlays/missing.md"}
                    ],
                }
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.framework_configurations, [])

    # --- Duplicate handling ---------------------------------------------

    def test_duplicate_framework_profile_pair_keeps_first(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "framework_configurations": [
                {"framework": "fw", "profile_name": "p1",
                 "config": {"x": "first"}},
                {"framework": "fw", "profile_name": "p1",
                 "config": {"x": "second"}},
            ],
        })
        p = self._load_quietly()
        self.assertEqual(len(p.framework_configurations), 1)
        self.assertEqual(
            p.framework_configurations[0].config["x"], "first",
        )

    def test_same_profile_name_different_framework_both_kept(self):
        # Profile name uniqueness is scoped per framework — both should land.
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "framework_configurations": [
                {"framework": "fw-a", "profile_name": "shared"},
                {"framework": "fw-b", "profile_name": "shared"},
            ],
        })
        p = pr.load_project_at(self.root)
        self.assertEqual(len(p.framework_configurations), 2)

    # --- Graceful degradation -------------------------------------------

    def test_one_bad_entry_doesnt_block_others(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "framework_configurations": [
                {"framework": "good", "profile_name": "p1"},
                {"framework": "bad"},  # missing profile_name
                {"framework": "also-good", "profile_name": "p1"},
            ],
        })
        p = self._load_quietly()
        self.assertEqual(len(p.framework_configurations), 2)
        frameworks = [fc.framework for fc in p.framework_configurations]
        self.assertEqual(set(frameworks), {"good", "also-good"})

    def test_fc_parse_error_doesnt_break_other_manifest_fields(self):
        self._write_manifest({
            "nexus": "test", "name": "Test",
            "tools": [
                {"name": "my-tool", "command": ["python3", "tools/x.py"]}
            ],
            "framework_configurations": [
                {"framework": "fw"}  # missing profile_name
            ],
        })
        p = self._load_quietly()
        self.assertEqual(p.framework_configurations, [])
        self.assertIn("my-tool", p.tools)


if __name__ == "__main__":
    unittest.main()
