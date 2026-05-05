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
from textwrap import dedent
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = os.path.dirname(HERE)
if ORCH not in sys.path:
    sys.path.insert(0, ORCH)

import slash_commands  # noqa: E402
from slash_commands import (  # noqa: E402
    is_runtime_command,
    run_runtime_command,
    _resolve_input_path,
    _resolve_output_dir,
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
        for cmd in ["/instance", "/validate", "/render", "/queue", "/approve", "/deny"]:
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
        self.assertFalse(is_runtime_command("/help"))

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
        self.assertIn("escalation", out)
        self.assertNotIn("redefinition —", out)


# ---------- /instance ----------

class TestInstanceCommand(unittest.TestCase):

    def setUp(self):
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

    def test_deny_removes_queue_entry(self):
        # Seed a non-redefinition escalation; deny should still remove it
        with open(self.queue_path, "w") as f:
            f.write(json.dumps({
                "queued_at": "2026-05-04T12:00:00+00:00",
                "event": {"project_nexus": "ora"},
                "verdict": {"reasoning": "any"},
                "redefinition": False,
            }) + "\n")
        out = run_runtime_command("/deny 0 \"not relevant\"")
        self.assertIn("Denial recorded", out)
        self.assertIn("not relevant", out)
        # Queue file should now be empty
        with open(self.queue_path) as f:
            self.assertEqual(f.read().strip(), "")


# ---------- Generic dispatcher behavior ----------

class TestDispatcherBehavior(unittest.TestCase):

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


if __name__ == "__main__":
    unittest.main()
