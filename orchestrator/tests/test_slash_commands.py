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


# ---------- /render-article-figures --patch frontmatter write-back ----------

SAMPLE_ARTICLE_FRONTMATTER = dedent("""\
    ---
    headline: Test article on the May jobs report
    lede: |
      The U.S. economy added a stronger-than-expected
      number of jobs in May, while the unemployment
      rate ticked up to 4.0%.
    nut_graf: |
      Payroll growth rebounded but the household
      survey told a softer story.
    publish_date: 2026-05-12
    sources:
      - id: src_001
        url: https://www.bls.gov/news.release/empsit.nr0.htm
        outlet: BLS
        outlet_class: government_release
        publication_date: 2026-05-09
        title: Employment Situation Summary
        access_date: 2026-05-12
        reliability_tier: 1
        originating_or_republishing: true
    atomic_claims:
      - claim_id: c_001
        text: Payrolls grew by 250k in May.
        claim_type: reported_claim
        subject_entities: ["Q_United_States"]
        predicate: payrolls_grew_by
        source_ids: [src_001]
        hedge: reported
        corroboration_level: primary_document
    ---

    The U.S. economy added a stronger-than-expected number of jobs
    in May, according to data released by the Bureau of Labor
    Statistics on Friday.

    [Body content continues here.]
""")


SAMPLE_FIGURES = [
    {
        "url": "/figures/2026-05-jobs/payems_first_diff.svg",
        "alt": "Monthly change in nonfarm payrolls, 2021-2026",
        "caption": "Payrolls grew 250k in May, near trend.",
        "credit": "Main Street Independent (algorithmic)",
        "source": "FRED, All Employees: Total Nonfarm (PAYEMS)",
        "source_url": "https://fred.stlouisfed.org/series/PAYEMS",
        "source_retrieval_date": "2026-05-12",
        "license": "https://creativecommons.org/publicdomain/zero/1.0/",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "chart_type": "timeseries",
        "data_window": "2021-01 to 2026-05",
        "transformation": "first_diff",
        "ai_authored": True,
        "ai_model": "msi-data-viz-pipeline-v1",
    },
    {
        "url": "/figures/2026-05-jobs/unrate_raw.svg",
        "alt": "U-3 unemployment rate, 2021-2026",
        "caption": "U-3 ticked up to 4.0% in May.",
        "credit": "Main Street Independent (algorithmic)",
        "source": "FRED, Unemployment Rate (UNRATE)",
        "source_url": "https://fred.stlouisfed.org/series/UNRATE",
        "source_retrieval_date": "2026-05-12",
        "license": "https://creativecommons.org/publicdomain/zero/1.0/",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "chart_type": "timeseries",
        "data_window": "2021-01 to 2026-05",
        "transformation": "raw",
        "ai_authored": True,
        "ai_model": "msi-data-viz-pipeline-v1",
    },
]


class TestPatchArticleFrontmatterFigures(unittest.TestCase):
    """Tests for slash_commands._patch_article_frontmatter_figures —
    the helper that mutates an article .md file by splicing in (or
    replacing) the `figures` array in YAML frontmatter."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.article_path = os.path.join(self.tmpdir, "test-article.md")
        with open(self.article_path, "w", encoding="utf-8") as f:
            f.write(SAMPLE_ARTICLE_FRONTMATTER)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _read_back(self) -> tuple[dict, str]:
        """Return (parsed_frontmatter_dict, body_text) from disk."""
        import yaml
        with open(self.article_path, "r", encoding="utf-8") as f:
            content = f.read()
        end_marker = content.find("\n---", 4)
        fm_text = content[3:end_marker].strip()
        body = content[end_marker + len("\n---"):]
        if body.startswith("\n"):
            body = body[1:]
        return yaml.safe_load(fm_text) or {}, body

    def test_inserts_figures_when_absent(self):
        slash_commands._patch_article_frontmatter_figures(
            self.article_path, SAMPLE_FIGURES,
        )
        fm, _body = self._read_back()
        self.assertIn("figures", fm)
        self.assertEqual(len(fm["figures"]), 2)
        self.assertEqual(
            fm["figures"][0]["url"],
            "/figures/2026-05-jobs/payems_first_diff.svg",
        )
        self.assertEqual(fm["figures"][1]["transformation"], "raw")

    def test_preserves_existing_fields(self):
        slash_commands._patch_article_frontmatter_figures(
            self.article_path, SAMPLE_FIGURES,
        )
        fm, _body = self._read_back()
        # All pre-existing top-level fields must still be present
        for required_key in (
            "headline", "lede", "nut_graf", "publish_date",
            "sources", "atomic_claims",
        ):
            self.assertIn(required_key, fm,
                          f"`{required_key}` should be preserved")
        self.assertEqual(
            fm["headline"],
            "Test article on the May jobs report",
        )
        self.assertEqual(len(fm["sources"]), 1)
        self.assertEqual(fm["sources"][0]["outlet"], "BLS")
        self.assertEqual(len(fm["atomic_claims"]), 1)
        self.assertEqual(fm["atomic_claims"][0]["claim_id"], "c_001")
        # Multi-line scalars survive the round-trip
        self.assertIn("stronger-than-expected", fm["lede"])

    def test_preserves_body_content(self):
        slash_commands._patch_article_frontmatter_figures(
            self.article_path, SAMPLE_FIGURES,
        )
        _fm, body = self._read_back()
        self.assertIn("stronger-than-expected number of jobs", body)
        self.assertIn("[Body content continues here.]", body)

    def test_replaces_existing_figures_key(self):
        # Patch once, then patch again with a different list. The second
        # call must replace, not concatenate or duplicate.
        slash_commands._patch_article_frontmatter_figures(
            self.article_path, SAMPLE_FIGURES,
        )
        new_figures = [{
            "url": "/figures/replacement.svg",
            "alt": "replacement",
            "caption": "new",
            "credit": "x", "source": "y",
            "chart_type": "timeseries", "transformation": "raw",
            "ai_authored": True,
        }]
        slash_commands._patch_article_frontmatter_figures(
            self.article_path, new_figures,
        )
        fm, _body = self._read_back()
        self.assertEqual(len(fm["figures"]), 1)
        self.assertEqual(fm["figures"][0]["url"], "/figures/replacement.svg")

    def test_raises_on_missing_frontmatter(self):
        bad_path = os.path.join(self.tmpdir, "bare.md")
        with open(bad_path, "w", encoding="utf-8") as f:
            f.write("# Just a body, no frontmatter\n\nText.\n")
        with self.assertRaises(ValueError):
            slash_commands._patch_article_frontmatter_figures(
                bad_path, SAMPLE_FIGURES,
            )

    def test_roundtrip_field_ordering_first_field_preserved(self):
        # PyYAML with sort_keys=False preserves dict insertion order.
        # The original frontmatter starts with `headline` — after a
        # round-trip, the rebuilt YAML should still start with `headline:`
        # (i.e. the first non-empty content line after the opening ---).
        slash_commands._patch_article_frontmatter_figures(
            self.article_path, SAMPLE_FIGURES,
        )
        with open(self.article_path, "r", encoding="utf-8") as f:
            text = f.read()
        # First line is `---`; second line should begin with `headline:`
        lines = text.splitlines()
        self.assertEqual(lines[0], "---")
        self.assertTrue(
            lines[1].startswith("headline:"),
            f"Expected `headline:` first; got `{lines[1]}`",
        )


class TestRenderArticleFiguresPatchFlag(unittest.TestCase):
    """End-to-end tests for /render-article-figures --patch.

    Mocks the classifier + render layer so we exercise only the slash
    command's flag-handling and frontmatter-write path.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.article_path = os.path.join(self.tmpdir, "2026-05-jobs.md")
        with open(self.article_path, "w", encoding="utf-8") as f:
            f.write(SAMPLE_ARTICLE_FRONTMATTER)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_fake_render_result(self):
        # Mirrors what render_figures_for_article returns on success
        from collections import namedtuple
        FakeAnalysis = namedtuple(
            "FakeAnalysis", ["warrants_charts", "opportunities", "error"],
        )
        FakeFigResult = namedtuple(
            "FakeFigResult", ["success", "figure_schema", "url",
                              "error_code", "error_message"],
        )
        FakeResult = namedtuple(
            "FakeResult",
            ["success", "figures", "analysis", "figure_results", "error"],
        )
        analysis = FakeAnalysis(
            warrants_charts=True,
            opportunities=[mock.MagicMock(), mock.MagicMock()],
            error="",
        )
        per_fig = [
            FakeFigResult(
                success=True, figure_schema=fs, url=fs["url"],
                error_code="", error_message="",
            )
            for fs in SAMPLE_FIGURES
        ]
        return FakeResult(
            success=True,
            figures=SAMPLE_FIGURES,
            analysis=analysis,
            figure_results=per_fig,
            error="",
        )

    def _invoke(self, *flags):
        # We bypass the real article_data_viz module by patching the
        # symbols the command imports lazily.
        fake_module = mock.MagicMock()
        fake_module.parse_article_file.return_value = {
            "headline": "Test article on the May jobs report",
        }
        fake_module.render_figures_for_article.return_value = (
            self._make_fake_render_result()
        )
        fake_module.analyze_article_for_data_viz.return_value = (
            self._make_fake_render_result().analysis
        )

        fake_boot = mock.MagicMock()
        fake_boot.call_model = mock.MagicMock()
        fake_boot.load_endpoints.return_value = {}
        fake_boot.get_slot_endpoint.return_value = {"slot": "sidebar"}

        with mock.patch.dict(sys.modules, {
            "article_data_viz": fake_module,
            "boot": fake_boot,
        }):
            return run_runtime_command(
                f"/render-article-figures {self.article_path} "
                + " ".join(flags)
            )

    def test_patch_writes_figures_into_frontmatter(self):
        out = self._invoke("--patch")
        self.assertIn("Frontmatter patched", out)

        # Verify on disk
        import yaml
        with open(self.article_path, "r", encoding="utf-8") as f:
            content = f.read()
        end_marker = content.find("\n---", 4)
        fm = yaml.safe_load(content[3:end_marker].strip())
        self.assertIn("figures", fm)
        self.assertEqual(len(fm["figures"]), 2)
        # Pre-existing fields preserved
        self.assertIn("headline", fm)
        self.assertIn("sources", fm)

    def test_no_patch_flag_leaves_frontmatter_untouched(self):
        # Without --patch, the file must be byte-for-byte unchanged
        with open(self.article_path, "r", encoding="utf-8") as f:
            before = f.read()
        out = self._invoke()
        with open(self.article_path, "r", encoding="utf-8") as f:
            after = f.read()
        self.assertEqual(before, after)
        self.assertNotIn("Frontmatter patched", out)


if __name__ == "__main__":
    unittest.main()
