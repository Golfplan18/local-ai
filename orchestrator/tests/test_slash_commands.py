"""Tests for the slash-command dispatcher (orchestrator/slash_commands.py).

Covers:
  - is_runtime_command recognition (positives + negatives)
  - argument parsing (shlex-based, with quoted strings)
  - path resolution (absolute / cwd / vault / ora)
  - delegation to corpus_runtime, output_runtime, redefinition_handler
  - error-string formatting (no exceptions reach the chat UI)
  - queue listing / approval / denial flows
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from textwrap import dedent
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = os.path.dirname(HERE)
if ORCH not in sys.path:
    sys.path.insert(0, ORCH)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from oversight_sandbox import redirect_oversight_logs  # noqa: E402

import slash_commands  # noqa: E402
from slash_commands import (  # noqa: E402
    is_runtime_command,
    run_runtime_command,
    _resolve_input_path,
    _resolve_output_dir,
)
from slash_command_registry import (  # noqa: E402
    find_command,
    project_command_specs,
    runtime_command_names,
)


SAMPLE_TEMPLATE = dedent("""\
    ---
    type: corpus_template
    template_version: 1.0
    ---

    # Marketing Monthly Corpus Template

    ## Sections

    ```yaml
    sections:
      - id: weekly_sales
        name: Weekly Sales
        source: pff-mortgage-pipeline
        missing_data_behavior: hold-and-warn
      - id: campaigns
        name: Campaign Performance
        source: pff-campaign-extractor
        missing_data_behavior: default-empty
    ```
    """)

SAMPLE_OFF = dedent("""\
    ---
    name: monthly-board-memo
    medium: markdown
    title: "Monthly Memo — {period}"
    sections:
      - section: weekly_sales
        heading: Weekly Sales
      - section: campaigns
        heading: Campaign Performance
    ---
    """)


# ---------- Recognition ----------

class TestIsRuntimeCommand(unittest.TestCase):

    def test_recognizes_all_known_commands(self):
        for cmd in [
            "/instance", "/validate", "/render", "/queue", "/approve", "/deny",
            "/help", "/commands", "/maintenance", "/projects",
        ]:
            self.assertTrue(is_runtime_command(cmd), cmd)
            self.assertTrue(is_runtime_command(f"{cmd} foo bar"))

    def test_case_insensitive(self):
        self.assertTrue(is_runtime_command("/QUEUE"))
        self.assertTrue(is_runtime_command("/Instance template 2026-05"))

    def test_leading_whitespace_handled(self):
        self.assertTrue(is_runtime_command("   /queue"))
        self.assertTrue(is_runtime_command("\t/render foo bar"))

    def test_rejects_framework_command(self):
        # /framework belongs to milestone_executor, not the runtime dispatcher
        self.assertFalse(is_runtime_command("/framework cff design"))

    def test_rejects_unknown_slash_commands(self):
        self.assertFalse(is_runtime_command("/foo"))

    def test_browser_only_commands_not_runtime_commands(self):
        for cmd in [
            "/new", "/sidebar", "/frameworks", "/modes", "/mode",
            "/settings", "/review", "/image",
        ]:
            self.assertFalse(is_runtime_command(cmd), cmd)

    def test_rejects_plain_text(self):
        self.assertFalse(is_runtime_command("hello world"))
        self.assertFalse(is_runtime_command(""))
        self.assertFalse(is_runtime_command(None))  # type: ignore

    def test_rejects_substring_matches(self):
        # "/queueing" should NOT match /queue
        self.assertFalse(is_runtime_command("/queueing things"))


# ---------- Path resolution ----------

class TestResolveInputPath(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ora-slash-test-")
        self.cwd_orig = os.getcwd()

    def tearDown(self):
        os.chdir(self.cwd_orig)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_absolute_existing_file(self):
        f = os.path.join(self.tmp, "x.md")
        with open(f, "w") as fh:
            fh.write("hi")
        self.assertEqual(_resolve_input_path(f), f)

    def test_absolute_missing_file_returns_none(self):
        f = os.path.join(self.tmp, "does-not-exist.md")
        self.assertIsNone(_resolve_input_path(f))

    def test_relative_resolves_against_cwd(self):
        os.chdir(self.tmp)
        with open("relative.md", "w") as fh:
            fh.write("hi")
        resolved = _resolve_input_path("relative.md")
        self.assertIsNotNone(resolved)
        self.assertTrue(resolved.endswith("relative.md"))

    def test_returns_none_for_blank(self):
        self.assertIsNone(_resolve_input_path(""))


class TestResolveOutputDir(unittest.TestCase):

    def test_render_default_is_vault_root(self):
        self.assertEqual(
            slash_commands.DEFAULT_OUTPUT_DIR,
            os.path.normpath(slash_commands.VAULT_DIR),
        )

    def test_blank_returns_default(self):
        default = "/tmp/some-default"
        self.assertEqual(_resolve_output_dir("", default), default)

    def test_absolute_passes_through(self):
        self.assertEqual(_resolve_output_dir("/tmp/x", "/default"), "/tmp/x")

    def test_relative_resolves_against_vault(self):
        result = _resolve_output_dir("Outputs/Test", "/default")
        self.assertTrue(result.startswith(slash_commands.VAULT_DIR.rstrip("/")))
        self.assertTrue(result.endswith("Outputs/Test"))


# ---------- /queue ----------

class TestQueueCommand(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ora-queue-test-")
        # Patch the human-queue path used by redefinition_handler
        from oversight_actions import HUMAN_QUEUE_PATH as _orig
        self._orig_queue_path = _orig
        self.queue_path = os.path.join(self.tmp, "human-queue.jsonl")
        # redefinition_handler imports HUMAN_QUEUE_PATH at module load,
        # so patch the binding inside that module too.
        import oversight_actions
        import redefinition_handler
        self._patches = [
            mock.patch.object(oversight_actions, "HUMAN_QUEUE_PATH", self.queue_path),
            mock.patch.object(redefinition_handler, "HUMAN_QUEUE_PATH", self.queue_path),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_queue_empty(self):
        out = run_runtime_command("/queue")
        self.assertIn("Human queue is empty", out)

    def test_queue_lists_pending_redefinition(self):
        with open(self.queue_path, "w") as f:
            f.write(json.dumps({
                "queued_at": "2026-05-04T12:00:00+00:00",
                "event": {"project_nexus": "ora", "event_type": "MilestoneClaimed"},
                "verdict": {
                    "verdict": "ESCALATE",
                    "reasoning": "The claimed milestone reveals the underlying problem definition was wrong.",
                },
                "redefinition": True,
                "forced_reason": "",
            }) + "\n")
        out = run_runtime_command("/queue")
        self.assertIn("1 pending entry", out)
        self.assertIn("redefinition", out)
        self.assertIn("project `ora`", out)
        self.assertIn("[0]", out)
        self.assertIn("milestone", out.lower())  # reasoning excerpt rendered

    def test_queue_lists_non_redefinition_entries(self):
        with open(self.queue_path, "w") as f:
            f.write(json.dumps({
                "queued_at": "2026-05-04T12:00:00+00:00",
                "event": {"project_nexus": "ora"},
                "verdict": {"reasoning": "Hard block"},
                "redefinition": False,
            }) + "\n")
        out = run_runtime_command("/queue")
        self.assertIn("legacy untyped", out)
        self.assertNotIn("redefinition —", out)


# ---------- /instance ----------

class TestInstanceCommand(unittest.TestCase):

    def setUp(self):
        redirect_oversight_logs(self)
        self.tmp = tempfile.mkdtemp(prefix="ora-instance-test-")
        self.template = os.path.join(self.tmp, "template.md")
        with open(self.template, "w") as f:
            f.write(SAMPLE_TEMPLATE)
        self.out_dir = os.path.join(self.tmp, "instances")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_usage_when_no_args(self):
        out = run_runtime_command("/instance")
        self.assertIn("Usage:", out)
        self.assertIn("/instance", out)

    def test_usage_when_one_arg(self):
        out = run_runtime_command("/instance template.md")
        self.assertIn("Usage:", out)

    def test_template_not_found(self):
        out = run_runtime_command("/instance does-not-exist.md 2026-05")
        self.assertIn("Template not found", out)
        self.assertIn("does-not-exist.md", out)

    def test_creates_instance(self):
        cmd = f'/instance "{self.template}" 2026-05 "{self.out_dir}"'
        out = run_runtime_command(cmd)
        self.assertIn("Corpus instance created", out)
        self.assertIn("template.md", out)
        self.assertIn("2026-05", out)
        # Confirm a file landed in out_dir
        files = os.listdir(self.out_dir)
        self.assertTrue(any(f.endswith(".md") for f in files))


# ---------- /validate ----------

class TestValidateCommand(unittest.TestCase):

    def setUp(self):
        redirect_oversight_logs(self)
        self.tmp = tempfile.mkdtemp(prefix="ora-validate-test-")
        self.template = os.path.join(self.tmp, "template.md")
        with open(self.template, "w") as f:
            f.write(SAMPLE_TEMPLATE)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_usage_when_no_args(self):
        out = run_runtime_command("/validate")
        self.assertIn("Usage:", out)

    def test_instance_not_found(self):
        out = run_runtime_command("/validate /tmp/does-not-exist.md")
        self.assertIn("Instance not found", out)

    def test_validates_empty_instance(self):
        # Build an instance via c_instance, then validate without populating.
        from corpus_runtime import c_instance
        out_dir = os.path.join(self.tmp, "instances")
        result = c_instance(self.template, "2026-05", out_dir)
        self.assertTrue(result.success)
        cmd = f'/validate "{result.instance_path}" "{self.template}"'
        out = run_runtime_command(cmd)
        self.assertIn("Validation:", out)
        # An empty instance has no populated sections — overall is FAIL
        self.assertIn("FAIL", out)
        self.assertIn("weekly_sales", out)
        self.assertIn("campaigns", out)


# ---------- /render ----------

class TestRenderCommand(unittest.TestCase):

    def setUp(self):
        redirect_oversight_logs(self)
        self.tmp = tempfile.mkdtemp(prefix="ora-render-test-")
        self.template = os.path.join(self.tmp, "template.md")
        self.off_spec = os.path.join(self.tmp, "off.md")
        with open(self.template, "w") as f:
            f.write(SAMPLE_TEMPLATE)
        with open(self.off_spec, "w") as f:
            f.write(SAMPLE_OFF)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_usage_when_short(self):
        out = run_runtime_command("/render")
        self.assertIn("Usage:", out)

    def test_off_spec_not_found(self):
        out = run_runtime_command("/render /tmp/no.md /tmp/no.md /tmp/")
        self.assertIn("OFF spec not found", out)

    def test_renders_artifact(self):
        from corpus_runtime import c_instance
        instance_dir = os.path.join(self.tmp, "instances")
        out_dir = os.path.join(self.tmp, "outputs")
        ic = c_instance(self.template, "2026-05", instance_dir)
        self.assertTrue(ic.success)

        cmd = f'/render "{self.off_spec}" "{ic.instance_path}" "{out_dir}"'
        out = run_runtime_command(cmd)
        self.assertIn("Output rendered", out)
        self.assertIn("monthly-board-memo", out)
        self.assertIn(out_dir, out)


# ---------- /approve and /deny ----------

class TestApproveDenyCommand(unittest.TestCase):

    def setUp(self):
        redirect_oversight_logs(self)
        self.tmp = tempfile.mkdtemp(prefix="ora-approve-test-")
        self.queue_path = os.path.join(self.tmp, "human-queue.jsonl")
        import oversight_actions
        import redefinition_handler
        self._patches = [
            mock.patch.object(oversight_actions, "HUMAN_QUEUE_PATH", self.queue_path),
            mock.patch.object(redefinition_handler, "HUMAN_QUEUE_PATH", self.queue_path),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_approve_usage_when_no_args(self):
        out = run_runtime_command("/approve")
        self.assertIn("Usage:", out)

    def test_approve_non_numeric_index(self):
        out = run_runtime_command("/approve abc")
        self.assertIn("not a valid index", out)

    def test_approve_invalid_index(self):
        out = run_runtime_command("/approve 99")
        self.assertIn("Approval failed", out)

    def test_deny_usage_when_no_args(self):
        out = run_runtime_command("/deny")
        self.assertIn("Usage:", out)

    def test_deny_non_numeric_index(self):
        out = run_runtime_command("/deny xyz")
        self.assertIn("not a valid index", out)

    def test_deny_invalid_index(self):
        out = run_runtime_command("/deny 99")
        self.assertIn("Denial failed", out)

    def test_untyped_escalation_never_falls_into_ped_denial_handler(self):
        # A non-redefinition legacy escalation has no safe typed handler. It
        # must not fall through to the PED redefinition implementation.
        with open(self.queue_path, "w") as f:
            f.write(json.dumps({
                "queued_at": "2026-05-04T12:00:00+00:00",
                "event": {"project_nexus": "ora"},
                "verdict": {"reasoning": "any"},
                "redefinition": False,
            }) + "\n")
        out = run_runtime_command("/deny 0 \"not relevant\"")
        self.assertIn("legacy_untyped", out)
        self.assertIn("was not changed", out)
        with open(self.queue_path) as f:
            self.assertNotEqual(f.read().strip(), "")

    def _write_execution_gate(self):
        record = {
            "id": "gate-owned",
            "kind": "execution_gate",
            "discussion_conversation_id": "dialogue:owner",
            "event": {
                "action": "delete_file", "args_hash": "sha256:test",
                "conversation_id": "dialogue:origin",
                "principal_id": "principal:owner",
            },
        }
        with open(self.queue_path, "w") as stream:
            stream.write(json.dumps(record) + "\n")

    def test_gate_approval_rejects_foreign_dialogue_and_principal(self):
        self._write_execution_gate()
        with mock.patch("tool_events.resolve_gate_entry") as resolver:
            foreign_dialogue = run_runtime_command(
                "/approve 0", conversation_id="dialogue:foreign",
                principal_id="principal:owner",
            )
            foreign_principal = run_runtime_command(
                "/approve 0", conversation_id="dialogue:owner",
                principal_id="principal:attacker",
            )
        resolver.assert_not_called()
        self.assertIn("do not own", foreign_dialogue)
        self.assertIn("do not own", foreign_principal)
        with open(self.queue_path) as stream:
            self.assertNotEqual(stream.read().strip(), "")

    def test_gate_approval_exact_owner_resolves_and_removes(self):
        self._write_execution_gate()
        with mock.patch(
            "tool_events.resolve_gate_entry", return_value="approved",
        ) as resolver:
            result = run_runtime_command(
                "/approve 0", conversation_id="dialogue:owner",
                principal_id="principal:owner",
            )
        resolver.assert_called_once()
        self.assertEqual(result, "approved")
        with open(self.queue_path) as stream:
            self.assertEqual(stream.read().strip(), "")


# ---------- Generic dispatcher behavior ----------

class TestDispatcherBehavior(unittest.TestCase):

    def _project_registration_fixture(self):
        from orchestrator import project_registry as real_registry

        temporary = tempfile.TemporaryDirectory(prefix="ora-project-register-")
        root = Path(temporary.name)
        project_root = root / "project"
        project_root.mkdir()
        manifest = project_root / real_registry.MANIFEST_FILENAME
        manifest.write_text(json.dumps({
            "nexus": "registered-project",
            "name": "Registered Project",
            "tools": [],
            "slash_commands": [],
        }), encoding="utf-8")
        pointer_dir = root / "pointers"

        register = mock.Mock(side_effect=lambda project_path, *,
            expected_manifest_sha256=None: real_registry.register_project(
                project_path,
                pointer_dir=str(pointer_dir),
                expected_manifest_sha256=expected_manifest_sha256,
            ))
        registry = SimpleNamespace(
            MANIFEST_FILENAME=real_registry.MANIFEST_FILENAME,
            ManifestError=real_registry.ManifestError,
            load_project_snapshot=real_registry.load_project_snapshot,
            _pointer_path=lambda nexus: real_registry._pointer_path(
                nexus, pointer_dir=str(pointer_dir)),
            register_project=register,
        )
        return temporary, project_root, manifest, pointer_dir, registry, register

    def test_project_register_uses_one_authorized_manifest_snapshot(self):
        (temporary, project_root, manifest, pointer_dir,
         registry, register) = self._project_registration_fixture()
        self.addCleanup(temporary.cleanup)
        protection = SimpleNamespace(action="project_register")
        effect = mock.MagicMock()
        effect.__enter__.return_value = None
        effect.__exit__.return_value = False

        with mock.patch.object(slash_commands, "_project_registry",
                               return_value=registry), \
                mock.patch.object(slash_commands._sp, "authorize_server_action",
                                  return_value=protection) as authorize, \
                mock.patch.object(slash_commands._sp, "protected_effect",
                                  return_value=effect), \
                mock.patch.object(slash_commands._sp, "complete_execution") as complete:
            result = run_runtime_command(f"/project-register {project_root}")

        self.assertIn("Registered project **registered-project**", result)
        pointer = pointer_dir / "registered-project.json"
        pointer_data = json.loads(pointer.read_text(encoding="utf-8"))
        snapshot = registry.load_project_snapshot(project_root)
        self.assertEqual(pointer_data["manifest_sha256"], snapshot.manifest_sha256)
        register.assert_called_once_with(
            str(project_root), expected_manifest_sha256=snapshot.manifest_sha256,
        )
        authorization = authorize.call_args.kwargs
        self.assertEqual(authorization["params"]["manifest_sha256"],
                         snapshot.manifest_sha256)
        self.assertEqual(
            set(authorization["selectors"]),
            {
                slash_commands._sp.path_selector(pointer),
                slash_commands._sp.path_selector(manifest),
            },
        )
        self.assertEqual(len(authorization["pre_state"]), 2)
        complete.assert_called_once()
        self.assertTrue(complete.call_args.kwargs["ok"])

    def test_project_register_refuses_manifest_drift_after_authorization(self):
        (temporary, project_root, manifest, pointer_dir,
         registry, register) = self._project_registration_fixture()
        self.addCleanup(temporary.cleanup)
        protection = SimpleNamespace(action="project_register")

        @contextmanager
        def drift_after_authorization(_protection):
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["description"] = "changed after authorization"
            manifest.write_text(json.dumps(data), encoding="utf-8")
            yield

        with mock.patch.object(slash_commands, "_project_registry",
                               return_value=registry), \
                mock.patch.object(slash_commands._sp, "authorize_server_action",
                                  return_value=protection), \
                mock.patch.object(slash_commands._sp, "protected_effect",
                                  side_effect=drift_after_authorization), \
                mock.patch.object(slash_commands._sp, "complete_execution") as complete:
            result = run_runtime_command(f"/project-register {project_root}")

        self.assertIn("invalid project", result)
        self.assertIn("changed after authorization", result)
        self.assertFalse((pointer_dir / "registered-project.json").exists())
        register.assert_called_once()
        complete.assert_called_once()
        self.assertFalse(complete.call_args.kwargs["ok"])

    def test_help_lists_registered_commands(self):
        out = run_runtime_command("/help")
        self.assertIn("/framework", out)
        self.assertIn("/maintenance", out)
        self.assertIn("/settings", out)

    def test_help_for_specific_command(self):
        out = run_runtime_command("/commands /framework")
        self.assertIn("**/framework**", out)
        self.assertIn("cff", out)

    def test_help_for_category(self):
        out = run_runtime_command("/help maintenance")
        self.assertIn("/queue", out)
        self.assertIn("/cleaning", out)

    def test_maintenance_group_alias_routes_to_queue(self):
        with mock.patch("redefinition_handler.list_pending_escalations", return_value=[]):
            out = run_runtime_command("/maintenance queue")
        self.assertIn("Human queue is empty", out)

    def test_maint_group_alias_routes_to_cleaning_help(self):
        out = run_runtime_command("/maint cleaning help")
        self.assertIn("Engram Cleaning Framework", out)

    def test_projects_group_help_does_not_load_project_registry(self):
        out = run_runtime_command("/projects help")
        self.assertIn("/project-list", out)

    def test_unknown_slash_command_returns_string(self):
        # is_runtime_command should reject /unknown — but if we call
        # run_runtime_command directly with one, it should still return a
        # string, not raise.
        out = run_runtime_command("/unknown foo")
        self.assertIn("Unknown slash command", out)

    def test_empty_input_returns_string(self):
        self.assertIn("Empty", run_runtime_command(""))

    def test_handles_quoted_arguments(self):
        # If shlex parsing fails (e.g., unbalanced quote), we expect a
        # parse-error string back, not an exception.
        out = run_runtime_command('/deny 0 "unbalanced')
        self.assertIn("parse error", out.lower())


class TestSlashCommandRegistry(unittest.TestCase):

    def _fake_project(self, command_name="publish-cycle"):
        command = SimpleNamespace(
            name=command_name,
            description="Run a publication cycle",
            interface="argv-stdout-json",
        )
        return SimpleNamespace(
            nexus="main-street-independent",
            name="Main Street Independent",
            slash_commands={command_name: command},
        )

    def test_runtime_names_include_server_aliases_only(self):
        names = runtime_command_names()
        self.assertIn("/help", names)
        self.assertIn("/commands", names)
        self.assertIn("/maintenance", names)
        self.assertNotIn("/settings", names)
        self.assertNotIn("/review", names)
        self.assertNotIn("/framework", names)

    def test_find_command_resolves_alias(self):
        spec = find_command("/commands")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.command, "/help")

    def test_project_command_specs_are_project_specific(self):
        specs = project_command_specs([self._fake_project()])
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].command, "/publish-cycle")
        self.assertEqual(specs[0].category, "Project Commands")
        self.assertEqual(specs[0].status, "project-specific")
        self.assertIn("Main Street Independent", specs[0].notes)

    def test_project_command_help_is_dynamic(self):
        fake_registry = SimpleNamespace(
            list_projects=lambda: [self._fake_project()],
        )
        with mock.patch.object(slash_commands, "_project_registry", return_value=fake_registry):
            out = run_runtime_command("/help /publish-cycle")
        self.assertIn("**/publish-cycle**", out)
        self.assertIn("Run a publication cycle", out)
        self.assertIn("project-specific", out)

    def test_project_command_category_help_is_dynamic(self):
        fake_registry = SimpleNamespace(
            list_projects=lambda: [self._fake_project()],
        )
        with mock.patch.object(slash_commands, "_project_registry", return_value=fake_registry):
            out = run_runtime_command("/help Project Commands")
        self.assertIn("/publish-cycle", out)
