#!/usr/bin/env python3
"""Campaign runner (scripts/campaign_run.py) — offline unit tests.

Covers the corpus parser (all three section shapes), technique selection,
manifest resume semantics, visual-fence extraction, single-pass response
parsing (Anthropic + OpenRouter shapes), pricing math, and aggregation.
Live sweeps are exercised separately by the calibration run.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent

SPEC = importlib.util.spec_from_file_location(
    "campaign_run", REPO_ROOT / "scripts" / "campaign_run.py")
campaign = importlib.util.module_from_spec(SPEC)
# Register before exec: the script's @dataclass under
# `from __future__ import annotations` resolves its module via
# sys.modules at class-creation time.
sys.modules["campaign_run"] = campaign
SPEC.loader.exec_module(campaign)


MINI_CORPUS = """\
# Reference — Trigger Prompt Corpus

## Comparative Evaluation Campaign

### The five campaign lanes

Some prose. 1. not a prompt (no entry open).

## Modes (by territory)

### T1-territory

#### `argument-audit`

**Intended mode:** `argument-audit`
**Pages:** [x](https://x)

**Prime prompt (Point 2):**

1. Audit this argument about tariffs.

**Other examples (Point 6):**

2. Second prompt that must be ignored.

#### `cui-bono`

**Intended mode:** `cui-bono`

1. Who benefits from this policy?

## Visual tools

### `ach-matrix`

**Routes to:** `competing-hypotheses`

1. Make me an ACH matrix on three hypotheses.

### `shared-name`

**Routes to:** `root-cause-analysis`

1. Draw the visual version of the shared-name technique.

## Lenses

### T1-territory

#### `anchoring`

**Foregrounds lens:** `anchoring`  ·  mental-model
**Host mode:** `propaganda-audit`  ·  **Also loadable in:** `argument-audit`

1. Audit the anchoring tactic in this ad.
2. Ignored.

#### `shared-name`

**Foregrounds lens:** `shared-name`  ·  mental-model
**Host mode:** `root-cause-analysis`

1. Apply the lens version of the shared-name technique.
"""


class TestRunnerRoot(unittest.TestCase):
    def test_default_root_is_the_checkout_containing_the_runner(self):
        self.assertEqual(campaign.ORA_HOME, REPO_ROOT.resolve())

    def test_default_corpus_uses_active_projects_ora_path(self):
        self.assertEqual(
            campaign.DEFAULT_CORPUS,
            Path.home() / "Documents" / "vault" / "Projects" / "Ora"
            / "Reference — Trigger Prompt Corpus.md",
        )

    def test_campaign_source_prefers_local_then_historical_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            checkout = root / "accepted"
            historical = root / "ora" / "data" / "campaign"
            historical.mkdir(parents=True)
            (historical / "campaign-manifest.jsonl").write_text("\n")
            self.assertEqual(
                campaign.resolve_campaign_dir(
                    checkout, user_home=root, env={}),
                historical.resolve(),
            )
            local = checkout / "data" / "campaign"
            local.mkdir(parents=True)
            (local / "campaign-manifest.jsonl").write_text("\n")
            self.assertEqual(
                campaign.resolve_campaign_dir(
                    checkout, user_home=root, env={}),
                local.resolve(),
            )

    def test_explicit_campaign_source_wins(self):
        with tempfile.TemporaryDirectory() as td:
            explicit = Path(td) / "evidence"
            self.assertEqual(
                campaign.resolve_campaign_dir(
                    REPO_ROOT, env={"ORA_CAMPAIGN_DIR": str(explicit)}),
                explicit.resolve(),
            )


class TestParseCorpus(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
        tmp.write(MINI_CORPUS)
        tmp.close()
        self.path = Path(tmp.name)
        self.addCleanup(lambda: self.path.unlink(missing_ok=True))

    def test_counts_and_kinds(self):
        techs = campaign.parse_corpus(self.path)
        self.assertEqual(len(techs), 6)
        kinds = {t.id: t.kind for t in techs}
        self.assertEqual(kinds["argument-audit"], "mode")
        self.assertEqual(kinds["ach-matrix"], "visual")
        self.assertEqual(kinds["anchoring"], "lens")

    def test_mode_lines_resolve_per_section(self):
        techs = {t.id: t for t in campaign.parse_corpus(self.path)}
        self.assertEqual(techs["argument-audit"].intended_mode, "argument-audit")
        self.assertEqual(techs["ach-matrix"].intended_mode, "competing-hypotheses")
        self.assertEqual(techs["anchoring"].intended_mode, "propaganda-audit")

    def test_prompt_is_first_numbered_item_only(self):
        techs = {t.id: t for t in campaign.parse_corpus(self.path)}
        self.assertEqual(techs["argument-audit"].prompt,
                         "Audit this argument about tariffs.")
        self.assertEqual(techs["anchoring"].prompt,
                         "Audit the anchoring tactic in this ad.")

    def test_campaign_section_does_not_leak_entries(self):
        techs = campaign.parse_corpus(self.path)
        self.assertNotIn("The five campaign lanes", [t.id for t in techs])

    def test_select_all_some_and_ids(self):
        techs = campaign.parse_corpus(self.path)
        self.assertEqual(len(campaign.select_techniques(techs, "all")), 6)
        picked = campaign.select_techniques(techs, "cui-bono,anchoring")
        self.assertEqual([t.id for t in picked], ["cui-bono", "anchoring"])
        with self.assertRaises(SystemExit):
            campaign.select_techniques(techs, "no-such-technique")

    def test_duplicate_ids_get_kind_qualified_keys(self):
        techs = campaign.parse_corpus(self.path)
        shared = [t for t in techs if t.id == "shared-name"]
        self.assertEqual([t.key for t in shared],
                         ["visual:shared-name", "lens:shared-name"])
        self.assertEqual([t.capture_slug for t in shared],
                         ["visual-shared-name", "lens-shared-name"])

    def test_bare_duplicate_selection_is_rejected(self):
        techs = campaign.parse_corpus(self.path)
        with self.assertRaises(SystemExit) as cm:
            campaign.select_techniques(techs, "shared-name")
        self.assertIn("visual:shared-name", str(cm.exception))
        picked = campaign.select_techniques(techs, "lens:shared-name")
        self.assertEqual([(t.kind, t.id) for t in picked],
                         [("lens", "shared-name")])


class TestRealCorpus(unittest.TestCase):
    """Against the live vault corpus when present (machine-specific)."""

    def setUp(self):
        if not campaign.DEFAULT_CORPUS.exists():
            self.skipTest("vault corpus not present on this machine")

    def test_full_counts(self):
        techs = campaign.parse_corpus(campaign.DEFAULT_CORPUS)
        by_kind: dict = {}
        for t in techs:
            by_kind.setdefault(t.kind, []).append(t)
        self.assertEqual(len(by_kind["mode"]), 60)
        self.assertEqual(len(by_kind["visual"]), 22)
        self.assertEqual(len(by_kind["lens"]), 116)
        self.assertEqual(len(techs), 198)

    def test_duplicate_public_ids_are_kind_qualified(self):
        techs = campaign.parse_corpus(campaign.DEFAULT_CORPUS)
        by_id: dict = {}
        for tech in techs:
            by_id.setdefault(tech.id, []).append(tech)
        duplicates = {k: v for k, v in by_id.items() if len(v) > 1}
        self.assertEqual(set(duplicates), {"causal-dag", "fishbone-diagram"})
        self.assertEqual(
            sorted(t.key for t in duplicates["causal-dag"]),
            ["mode:causal-dag", "visual:causal-dag"],
        )
        self.assertEqual(
            sorted(t.capture_slug for t in duplicates["fishbone-diagram"]),
            ["lens-fishbone-diagram", "visual-fishbone-diagram"],
        )

    def test_some_subset_resolves(self):
        techs = campaign.parse_corpus(campaign.DEFAULT_CORPUS)
        picked = campaign.select_techniques(techs, "some")
        self.assertEqual(len(picked), len(campaign.SOME_SUBSET))
        kinds = {t.kind for t in picked}
        self.assertEqual(kinds, {"mode", "visual", "lens"})


class TestManifest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._orig = (campaign.CAMPAIGN_DIR, campaign.MANIFEST_PATH)
        campaign.CAMPAIGN_DIR = Path(self.tmp.name)
        campaign.MANIFEST_PATH = Path(self.tmp.name) / "campaign-manifest.jsonl"
        self.addCleanup(self._restore)

    def _restore(self):
        campaign.CAMPAIGN_DIR, campaign.MANIFEST_PATH = self._orig

    def test_latest_record_wins_and_failed_reruns(self):
        campaign.append_manifest({"technique": "a", "kind": "mode",
                                  "pipeline": "premium",
                                  "status": "failed"})
        campaign.append_manifest({"technique": "a", "kind": "mode",
                                  "pipeline": "premium",
                                  "status": "ok"})
        campaign.append_manifest({"technique": "b", "kind": "lens",
                                  "pipeline": "premium",
                                  "status": "failed"})
        done = campaign.load_manifest()
        self.assertEqual(done[("mode:a", "premium")]["status"], "ok")
        self.assertEqual(done[("lens:b", "premium")]["status"], "failed")

    def test_manifest_keeps_duplicate_ids_separate(self):
        campaign.append_manifest({"technique": "shared", "kind": "visual",
                                  "pipeline": "premium", "status": "ok"})
        campaign.append_manifest({"technique": "shared", "kind": "lens",
                                  "pipeline": "premium", "status": "failed"})
        campaign.append_manifest({"technique": "shared",
                                  "technique_key": "lens:shared",
                                  "pipeline": "premium", "status": "ok"})
        done = campaign.load_manifest()
        self.assertEqual(done[("visual:shared", "premium")]["status"], "ok")
        self.assertEqual(done[("lens:shared", "premium")]["status"], "ok")

    def test_malformed_lines_skipped(self):
        campaign.MANIFEST_PATH.write_text('not json\n{"technique":"a"}\n'
                                          '{"technique":"a","pipeline":"x","status":"ok"}\n')
        done = campaign.load_manifest()
        self.assertEqual(list(done.keys()), [("a", "x")])


class TestCampaignAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.corpus_path = self.root / "mini-corpus.md"
        self.corpus_path.write_text(MINI_CORPUS)
        self._orig = (campaign.CAMPAIGN_DIR, campaign.MANIFEST_PATH)
        campaign.CAMPAIGN_DIR = self.root / "campaign"
        campaign.MANIFEST_PATH = campaign.CAMPAIGN_DIR / "campaign-manifest.jsonl"
        campaign.CAMPAIGN_DIR.mkdir()
        self.addCleanup(self._restore)

    def _restore(self):
        campaign.CAMPAIGN_DIR, campaign.MANIFEST_PATH = self._orig

    def _trace(self, name, contingencies):
        trace = self.root / name
        trace.mkdir()
        (trace / "step-health.json").write_text(json.dumps({
            "contingencies_fired": contingencies,
        }))
        return str(trace)

    def test_audit_completeness_and_trace_health(self):
        clean = self._trace("trace-clean", [])
        broken = self._trace("trace-broken", [
            "step6-cycle1-depth-verifier-BROKEN-not-verified",
        ])
        campaign.append_manifest({
            "technique": "argument-audit", "kind": "mode",
            "pipeline": "premium", "status": "failed",
        })
        campaign.append_manifest({
            "technique": "argument-audit", "kind": "mode",
            "technique_key": "mode:argument-audit",
            "pipeline": "premium", "status": "ok",
            "trace_dir": clean,
        })
        campaign.append_manifest({
            "technique": "cui-bono", "kind": "mode",
            "pipeline": "premium", "status": "ok",
            "trace_dir": broken,
        })
        campaign.append_manifest({
            "technique": "cui-bono", "kind": "mode",
            "pipeline": "single-pass", "status": "ok",
        })
        campaign.append_manifest({
            "technique": "anchoring", "kind": "lens",
            "pipeline": "premium", "status": "failed",
            "error": "model quota exhausted",
        })
        campaign.append_manifest({
            "technique": "old-tech", "kind": "mode",
            "pipeline": "premium", "status": "ok",
        })

        summary = campaign.audit_campaign(
            self.corpus_path, pipelines=["premium", "single-pass"])
        self.assertEqual(summary["corpus"]["entries"], 6)
        self.assertEqual(summary["corpus"]["duplicate_public_ids"], {
            "shared-name": ["visual:shared-name", "lens:shared-name"],
        })
        self.assertEqual(
            summary["completeness"]["per_pipeline"]["premium"],
            {"ok": 2, "failed": 1, "missing": 3, "total": 6},
        )
        self.assertEqual(summary["completeness"]["complete_selected"], 1)
        health = summary["accepted_trace_health"]
        self.assertEqual(health["accepted_trace_count"], 2)
        self.assertEqual(health["accepted_trace_with_health"], 2)
        self.assertEqual(health["bare_control_records_excluded"], 1)
        self.assertEqual(health["severity_counts"]["clean"], 1)
        self.assertEqual(health["severity_counts"]["verification_gap"], 1)
        self.assertEqual(health["category_counts"]["verification_gap"], 1)
        self.assertEqual(summary["stale_manifest_keys"], ["mode:old-tech"])

    def test_both_bare_controls_are_excluded_from_trace_health(self):
        clean = self._trace("trace-clean", [])
        for pipe, trace in (
            ("premium", clean),
            ("single-pass", None),
            ("single-pass-9b", None),
        ):
            campaign.append_manifest({
                "technique": "argument-audit",
                "kind": "mode",
                "pipeline": pipe,
                "status": "ok",
                "trace_dir": trace,
                "at": "2026-07-20T03:27:14+00:00",
            })
        summary = campaign.audit_campaign(
            self.corpus_path,
            pipelines=["premium", "single-pass", "single-pass-9b"],
        )
        health = summary["accepted_trace_health"]
        self.assertEqual(health["accepted_trace_count"], 1)
        self.assertEqual(health["accepted_trace_with_health"], 1)
        self.assertEqual(health["bare_control_records_excluded"], 2)
        self.assertEqual(health["accepted_trace_missing_health"], [])

    def test_missing_manifest_fails_closed(self):
        with self.assertRaisesRegex(
                FileNotFoundError, "authoritative campaign manifest not found"):
            campaign.audit_campaign(
                self.corpus_path,
                campaign_dir=self.root / "missing-campaign",
            )

    def test_write_campaign_audit_outputs_json_and_markdown(self):
        campaign.append_manifest({
            "technique": "argument-audit", "kind": "mode",
            "pipeline": "premium", "status": "ok",
            "trace_dir": self._trace("trace-clean", []),
        })
        summary = campaign.audit_campaign(self.corpus_path, pipelines=["premium"])
        json_path, md_path = campaign.write_campaign_audit(summary)
        self.assertTrue(json_path.exists())
        self.assertTrue(md_path.exists())
        self.assertIn("Premium Resume Selector", md_path.read_text())
        self.assertIn("Historical Coverage Limitation", md_path.read_text())
        self.assertIn("Campaign-row completeness and trace-health coverage are separate", md_path.read_text())
        self.assertEqual(json.loads(json_path.read_text())["corpus"]["entries"], 6)
        self.assertEqual(
            json.loads(json_path.read_text())["source"]["manifest_path"],
            str(campaign.MANIFEST_PATH.resolve()),
        )


    def test_audit_refuses_to_overwrite_accepted_evidence(self):
        """outputs/ holds finished records; a re-run replaces, never refreshes.

        The audit reads pipeline traces and a campaign manifest that are
        git-ignored and swept after 30 days, so re-running it against an
        accepted record cannot reproduce the recorded numbers — it can only
        write today's. outputs/g1-2 was overwritten exactly this way on
        2026-08-19 and had to be restored from git.
        """
        campaign.append_manifest({
            "technique": "argument-audit", "kind": "mode",
            "pipeline": "premium", "status": "ok",
            "trace_dir": self._trace("trace-clean", []),
        })
        summary = campaign.audit_campaign(self.corpus_path, pipelines=["premium"])
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(campaign, "ACCEPTED_EVIDENCE_ROOT", Path(td)):
                target = Path(td) / "g1-2"
                with self.assertRaisesRegex(
                        SystemExit, "refusing to overwrite accepted"):
                    campaign.write_campaign_audit(summary, output_dir=target)
                self.assertFalse(
                    target.exists(),
                    "refused after creating the directory; it must refuse first")

    def test_accepted_evidence_check_is_boundary_anchored(self):
        """A sibling directory that merely shares the prefix is not inside it."""
        root = campaign.ACCEPTED_EVIDENCE_ROOT
        self.assertTrue(campaign.is_accepted_evidence_dir(root))
        self.assertTrue(campaign.is_accepted_evidence_dir(root / "g1-2"))
        self.assertFalse(
            campaign.is_accepted_evidence_dir(root.parent / "outputs-scratch"))
        self.assertFalse(campaign.is_accepted_evidence_dir(Path(self.root)))

    def test_explicit_override_still_writes_into_accepted_evidence(self):
        """The refusal is a guard, not a wall — you can still mean it."""
        campaign.append_manifest({
            "technique": "argument-audit", "kind": "mode",
            "pipeline": "premium", "status": "ok",
            "trace_dir": self._trace("trace-clean", []),
        })
        summary = campaign.audit_campaign(self.corpus_path, pipelines=["premium"])
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(campaign, "ACCEPTED_EVIDENCE_ROOT", Path(td)):
                target = Path(td) / "g1-2"
                json_path, md_path = campaign.write_campaign_audit(
                    summary, output_dir=target, allow_accepted_overwrite=True)
                self.assertTrue(json_path.exists())
                self.assertTrue(md_path.exists())


class TestVisualExtraction(unittest.TestCase):
    def test_fence_extracted_and_placeholder_left(self):
        text = ("Intro prose.\n\n```ora-visual\n{\"type\": \"concept_map\"}\n```\n\n"
                "Closing prose.")
        prose, envs = campaign.extract_visuals(text)
        self.assertEqual(envs, ['{"type": "concept_map"}'])
        self.assertNotIn("ora-visual", prose)
        self.assertIn("Intro prose.", prose)
        self.assertIn("Closing prose.", prose)
        self.assertIn("visual rendered", prose)

    def test_no_fence_is_noop(self):
        prose, envs = campaign.extract_visuals("Just prose.")
        self.assertEqual(envs, [])
        self.assertEqual(prose, "Just prose.")

    def test_multiple_fences(self):
        text = "A\n```ora-visual\n{1}\n```\nB\n```ora-visual\n{2}\n```\nC"
        prose, envs = campaign.extract_visuals(text)
        self.assertEqual(len(envs), 2)


class TestBannerStripping(unittest.TestCase):
    BANNERED = (
        "> ⚠️ **Meta-layer oversight: degraded**\n"
        "> - ped_watcher: last heartbeat 1h ago (expected within 60s)\n"
        "> \n"
        "> The oversight daemon may not be running.\n"
        "\n---\n\n"
        "> ℹ️ **Meta-layer oversight: simulated**\n"
        "> - Oversight is running in simulated mode.\n"
        "\n---\n"
        "The actual answer starts here.\n\n> A real blockquote in the answer."
    )

    def test_strips_stacked_oversight_banners(self):
        out = campaign.strip_system_banners(self.BANNERED)
        self.assertTrue(out.startswith("The actual answer starts here."))
        self.assertIn("> A real blockquote in the answer.", out)

    def test_plain_answer_untouched(self):
        self.assertEqual(campaign.strip_system_banners("Just an answer."),
                         "Just an answer.")

    def test_degradation_signals_kept(self):
        # Pipeline degradation notes describe the run — they must survive.
        text = "> ⚠️ degraded: breadth fell back\n\n---\n\nAnswer."
        self.assertEqual(campaign.strip_system_banners(text), text)


class TestSinglePass(unittest.TestCase):
    def test_anthropic_response_parsing(self):
        fake = {"content": [{"type": "text", "text": "Answer."}],
                "usage": {"input_tokens": 120, "output_tokens": 850}}
        ep = {"service": "claude", "model_id": "claude-opus-4-8",
              "id": "anthropic/claude-opus-4.8"}
        with mock.patch.object(campaign, "_keyring_get", return_value="k"), \
             mock.patch.object(campaign.urllib.request, "urlopen") as uo:
            uo.return_value.__enter__.return_value.read.return_value = \
                json.dumps(fake).encode()
            rec = campaign.single_pass_call(ep, "prompt")
        self.assertEqual(rec["text"], "Answer.")
        self.assertEqual(rec["prompt_tokens"], 120)
        self.assertEqual(rec["completion_tokens"], 850)
        self.assertEqual(rec["via"], "anthropic-direct")

    def test_openrouter_response_parsing(self):
        fake = {"choices": [{"message": {"content": "Answer."}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 500}}
        ep = {"service": "openrouter", "id": "qwen/qwen3.5-9b",
              "openrouter_fallback_model_id": "qwen/qwen3.5-9b"}
        with mock.patch.object(campaign, "_keyring_get", return_value="k"), \
             mock.patch.object(
                 campaign.network_policy, "openrouter_request_bytes",
                 return_value=(json.dumps(fake).encode(), mock.sentinel.destination),
             ) as request:
            rec = campaign.single_pass_call(ep, "prompt")
        self.assertEqual(rec["via"], "openrouter")
        self.assertEqual(rec["completion_tokens"], 500)
        self.assertEqual(
            request.call_args.args[0],
            "https://openrouter.ai/api/v1/chat/completions",
        )

    def test_pricing_math(self):
        rec = {"prompt_tokens": 1_000_000, "completion_tokens": 500_000}
        pricing = {"input_per_million_usd": 5.0, "output_per_million_usd": 25.0}
        self.assertEqual(campaign.price_single_pass(rec, pricing), 17.5)
        self.assertIsNone(campaign.price_single_pass(rec, None))
        self.assertIsNone(campaign.price_single_pass(
            rec, {"input_per_million_usd": None, "output_per_million_usd": None}))


class TestFidelityGate(unittest.TestCase):
    """Trace audit: only configured primaries may execute; silent step
    failures and finish-reason anomalies must surface."""

    EXPECTED = {"anthropic/claude-opus-4.8", "openai/gpt-5.5",
                "openai/gpt-5.4-mini"}

    def _trace(self, usage_records, step_files=None, call_records=None):
        tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        Path(tmp, "usage.jsonl").write_text(
            "\n".join(json.dumps(r) for r in usage_records))
        if call_records is not None:
            Path(tmp, "model-call-config.jsonl").write_text(
                "\n".join(json.dumps(r) for r in call_records))
        for name, body in (step_files or {}).items():
            Path(tmp, name).write_text(json.dumps(body))
        return tmp

    @staticmethod
    def _rec(eid, finish="stop", hint="analyst"):
        return {"endpoint_id": eid, "model_id": eid.split("/")[-1],
                "service": "openrouter", "step_hint": hint,
                "finish_reason": finish, "prompt_tokens": 10,
                "completion_tokens": 20}

    def test_clean_run_passes(self):
        t = self._trace([self._rec("anthropic/claude-opus-4.8"),
                         self._rec("openai/gpt-5.5", finish="end_turn")])
        res = campaign.verify_trace_fidelity(t, self.EXPECTED)
        self.assertTrue(res["ok"])
        self.assertEqual(res["executed"]["anthropic/claude-opus-4.8"], 1)

    def test_fallback_model_execution_fails(self):
        # The 429-cascade case: a fallback (gemini) served instead of a
        # configured primary.
        t = self._trace([self._rec("anthropic/claude-opus-4.8"),
                         self._rec("google/gemini-3.1-pro-preview")])
        res = campaign.verify_trace_fidelity(t, self.EXPECTED)
        self.assertFalse(res["ok"])
        kinds = {v["kind"] for v in res["violations"]}
        self.assertIn("unexpected_model", kinds)

    def test_silent_step_failure_fails(self):
        t = self._trace([self._rec("openai/gpt-5.5")],
                        {"step4-eval-of-depth.json":
                         {"ok": False, "reason": "endpoint timeout"}})
        res = campaign.verify_trace_fidelity(t, self.EXPECTED)
        self.assertFalse(res["ok"])
        self.assertIn("step_failed", {v["kind"] for v in res["violations"]})

    def test_unreleased_quality_gate_fails(self):
        t = self._trace(
            [self._rec("openai/gpt-5.5")],
            {"step6_5-quality-gate.json": {
                "verdict_resolved": "BROKEN",
                "released": False,
            }},
        )
        res = campaign.verify_trace_fidelity(t, self.EXPECTED)
        self.assertFalse(res["ok"])
        self.assertIn("quality_gate_not_passed",
                      {v["kind"] for v in res["violations"]})

    def test_corrected_gear3_quality_gate_uses_terminal_summary(self):
        t = self._trace(
            [self._rec("openai/gpt-5.5")],
            {
                "step6_5-quality-gate-pass-1.json": {
                    "verdict_resolved": "FAIL",
                    "released": None,
                },
                "step6_5-quality-gate-pass-2.json": {
                    "verdict_resolved": "PASS",
                    "released": None,
                },
                "step6_5-quality-gate.json": {
                    "verdict_resolved": "PASS",
                    "released": True,
                },
            },
        )
        self.assertTrue(campaign.verify_trace_fidelity(t, self.EXPECTED)["ok"])

    def test_corrected_gear4_quality_gate_uses_last_numbered_pass(self):
        t = self._trace(
            [self._rec("openai/gpt-5.5")],
            {
                "step8_6-quality-gate-pass-1.json": {
                    "verdict_resolved": "FAIL",
                },
                "step8_6-quality-gate-pass-2.json": {
                    "verdict_resolved": "PASS",
                },
            },
        )
        self.assertTrue(campaign.verify_trace_fidelity(t, self.EXPECTED)["ok"])

    def test_last_numbered_quality_gate_failure_is_terminal(self):
        t = self._trace(
            [self._rec("openai/gpt-5.5")],
            {
                "step8_6-quality-gate-pass-1.json": {
                    "verdict_resolved": "PASS",
                },
                "step8_6-quality-gate-pass-2.json": {
                    "verdict_resolved": "BROKEN",
                },
            },
        )
        res = campaign.verify_trace_fidelity(t, self.EXPECTED)
        self.assertFalse(res["ok"])
        self.assertIn("quality_gate_not_passed",
                      {v["kind"] for v in res["violations"]})

    def test_ok_true_step_and_no_ok_key_pass(self):
        t = self._trace([self._rec("openai/gpt-5.5")],
                        {"step3-depth.json": {"ok": True},
                         "step-visual-hook.json": {"status": "ok"}})
        self.assertTrue(campaign.verify_trace_fidelity(t, self.EXPECTED)["ok"])

    def test_finish_reason_anomaly_warns_but_passes(self):
        t = self._trace([self._rec("openai/gpt-5.5", finish="length")])
        res = campaign.verify_trace_fidelity(t, self.EXPECTED)
        self.assertTrue(res["ok"])
        self.assertEqual(res["warnings"][0]["finish_reason"], "length")

    def test_wrapper_finish_reason_shapes_all_pass(self):
        # OpenAI 'stop', Anthropic 'end_turn', Gemini enum repr
        # 'FinishReason.STOP' — all normal terminations, no warnings.
        t = self._trace([self._rec("openai/gpt-5.5", finish="stop"),
                         self._rec("anthropic/claude-opus-4.8", finish="end_turn"),
                         self._rec("openai/gpt-5.4-mini", finish="FinishReason.STOP")])
        res = campaign.verify_trace_fidelity(t, self.EXPECTED)
        self.assertTrue(res["ok"])
        self.assertEqual(res["warnings"], [])

    def test_missing_trace_or_usage_fails(self):
        res = campaign.verify_trace_fidelity(None, self.EXPECTED)
        self.assertFalse(res["ok"])
        tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        res2 = campaign.verify_trace_fidelity(tmp, self.EXPECTED)
        self.assertIn("no_usage", {v["kind"] for v in res2["violations"]})

    def test_missing_subscription_primary_fails(self):
        # optimum-plus class of drift: a throttled subscription consolidator
        # falls back to a model that is a LEGITIMATE primary elsewhere in
        # the config — invisible to the unexpected-model check. The
        # subscription primary's absence from the census must reject.
        expected = {"qwen/big", "google/big2", "claude-code:claude-opus-4.8"}
        t = self._trace([self._rec("qwen/big"), self._rec("google/big2")])
        res = campaign.verify_trace_fidelity(t, expected)
        self.assertFalse(res["ok"])
        self.assertIn("required_model_missing",
                      {v["kind"] for v in res["violations"]})

    def test_present_subscription_primary_passes(self):
        expected = {"qwen/big", "claude-code:claude-opus-4.8"}
        t = self._trace([self._rec("qwen/big"),
                         self._rec("claude-code:claude-opus-4.8")])
        self.assertTrue(campaign.verify_trace_fidelity(t, expected)["ok"])

    def test_path_legal_run_does_not_require_unused_subscription_cell(self):
        expected = {"qwen/big", "minimax/reviewer",
                    "claude-code:claude-opus-4.8"}
        contract = {
            "config_name": "campaign-optimum-plus",
            "cells": {
                "analysis": {"gear3": {
                    "depth": {"primary": "qwen/big"},
                    "breadth": {"primary": "minimax/reviewer"},
                }},
                "post_analysis": {"consolidation": {
                    "primary": "claude-code:claude-opus-4.8",
                }},
            },
        }
        calls = [
            {"physical_attempt": True, "endpoint_id": "qwen/big",
             "config_name": "campaign-optimum-plus", "slot": "depth",
             "gear": 3, "step": "analyst"},
            {"physical_attempt": True, "endpoint_id": "minimax/reviewer",
             "config_name": "campaign-optimum-plus", "slot": "breadth",
             "gear": 3, "step": "evaluator"},
        ]
        t = self._trace(
            [self._rec("qwen/big"), self._rec("minimax/reviewer")],
            call_records=calls,
        )
        self.assertTrue(
            campaign.verify_trace_fidelity(t, expected, contract)["ok"])

    def test_same_config_primary_in_wrong_cell_fails(self):
        expected = {"qwen/big", "claude-code:claude-opus-4.8"}
        contract = {
            "config_name": "campaign-optimum-plus",
            "cells": {
                "analysis": {"gear4": {
                    "depth": {"primary": "qwen/big"},
                }},
                "post_analysis": {"consolidation": {
                    "primary": "claude-code:claude-opus-4.8",
                }},
            },
        }
        calls = [{
            "physical_attempt": True,
            "endpoint_id": "qwen/big",
            "config_name": "campaign-optimum-plus",
            "slot": "consolidation",
            "gear": 4,
            "step": "consolidator",
        }]
        t = self._trace([self._rec("qwen/big")], call_records=calls)
        result = campaign.verify_trace_fidelity(t, expected, contract)
        self.assertFalse(result["ok"])
        self.assertIn("cell_primary_mismatch",
                      {v["kind"] for v in result["violations"]})

    def test_physical_call_with_wrong_configuration_fails(self):
        expected = {"qwen/big"}
        contract = {
            "config_name": "campaign-optimum-plus",
            "cells": {"analysis": {"gear3": {
                "depth": {"primary": "qwen/big"},
            }}},
        }
        calls = [{
            "physical_attempt": True,
            "endpoint_id": "qwen/big",
            "config_name": None,
            "slot": "depth",
            "gear": 3,
            "step": "analyst",
        }]
        t = self._trace([self._rec("qwen/big")], call_records=calls)
        result = campaign.verify_trace_fidelity(t, expected, contract)
        self.assertFalse(result["ok"])
        self.assertIn("configuration_identity_mismatch",
                      {v["kind"] for v in result["violations"]})

    def test_expected_primaries_collects_all_cells(self):
        with mock.patch.object(campaign, "CONFIGURATIONS_DIR",
                               Path(tempfile.mkdtemp())) as _:
            cfg = {"cells": {
                "utility": {"step1_cleanup": {"primary": "a/x", "fallback": ["a/fb"]}},
                "analysis": {"gear4": {"depth": {"primary": "b/y"},
                                       "breadth": None}},
            }}
            campaign.CONFIGURATIONS_DIR.mkdir(parents=True, exist_ok=True)
            (campaign.CONFIGURATIONS_DIR / "c.json").write_text(json.dumps(cfg))
            exp = campaign.load_expected_primaries("c")
        self.assertEqual(exp, {"a/x", "b/y"})  # fallbacks excluded


class TestSubscriptionPathPacing(unittest.TestCase):
    def _tech(self, mode="structured-output"):
        return campaign.Technique(
            id=mode,
            kind="mode",
            intended_mode=mode,
            prompt="test",
            key=f"mode:{mode}",
            capture_slug=mode,
        )

    def test_gear2_capture_probes_haiku_not_unreachable_opus(self):
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(campaign, "ORA_HOME", Path(td)):
            modes = Path(td, "modes")
            modes.mkdir()
            Path(modes, "structured-output.md").write_text(
                "## DEFAULT GEAR\n\nGear 2\n")
            contract = {"cells": {
                "utility": {"gear2_rag_lookup": {
                    "primary": campaign.CLAUDE_CODE_HAIKU,
                }},
                "analysis": {"gear4": {"depth": {
                    "primary": campaign.CLAUDE_CODE_OPUS,
                }}},
            }}
            selected = campaign._subscription_probe_endpoint(
                self._tech(), contract)
        self.assertEqual(selected, campaign.CLAUDE_CODE_HAIKU)

    def test_gear4_capture_probes_opus(self):
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(campaign, "ORA_HOME", Path(td)):
            modes = Path(td, "modes")
            modes.mkdir()
            Path(modes, "deep-mode.md").write_text(
                "## DEFAULT GEAR\n\nGear 4\n")
            contract = {"cells": {"analysis": {"gear4": {
                "depth": {"primary": campaign.CLAUDE_CODE_OPUS},
            }}}}
            selected = campaign._subscription_probe_endpoint(
                self._tech("deep-mode"), contract)
        self.assertEqual(selected, campaign.CLAUDE_CODE_OPUS)

    def test_subscription_auth_failure_fails_fast_without_sleep(self):
        result = mock.Mock(
            returncode=1,
            stdout="",
            stderr="Not logged in · Please run /login\n",
        )
        with mock.patch("subprocess.run", return_value=result), \
             mock.patch("time.sleep") as sleep:
            with self.assertRaisesRegex(
                    RuntimeError, "subscription authentication unavailable"):
                campaign._wait_for_subscription_window(
                    campaign.CLAUDE_CODE_HAIKU, max_wait_s=900)
        sleep.assert_not_called()

    def test_subscription_rate_limit_waits_and_reprobes(self):
        closed = mock.Mock(
            returncode=1,
            stdout="",
            stderr="Usage limit reached; try again later",
        )
        opened = mock.Mock(returncode=0, stdout="OK\n", stderr="")
        with mock.patch("subprocess.run", side_effect=[closed, opened]), \
             mock.patch("time.sleep") as sleep:
            campaign._wait_for_subscription_window(
                campaign.CLAUDE_CODE_HAIKU, max_wait_s=900)
        sleep.assert_called_once_with(900)


class TestOraPipelineConversationBinding(unittest.TestCase):
    class _Response:
        def __init__(self, body):
            self.body = json.dumps(body).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return self.body

    def test_waits_for_new_assistant_and_uses_its_exact_trace(self):
        old = {"role": "assistant", "content": "old", "trace_ref": "c/old"}
        new = {"role": "assistant", "content": "new result",
               "trace_ref": "c/new"}
        responses = [
            self._Response({"messages": [old]}),
            self._Response({"status": "ok"}),
            self._Response({"messages": [old]}),
            self._Response({"messages": [old, new]}),
        ]
        tech = campaign.Technique(
            id="x", kind="mode", intended_mode="x", prompt="test")
        with mock.patch.object(campaign.urllib.request, "urlopen",
                               side_effect=responses), \
             mock.patch.object(campaign.time, "sleep"):
            result = campaign.run_ora_pipeline(
                "http://server", "campaign-optimum", tech, "c")
        self.assertEqual(result["text"], "new result")
        self.assertEqual(result["trace_dir"],
                         str(campaign.TRACES_DIR / "c/new"))


class TestOptimumPlus(unittest.TestCase):
    OPTIMUM = {
        "name": "campaign-optimum",
        "cells": {
            "utility": {"step1_cleanup": {"primary": "a/small", "fallback": ["a/fb"]}},
            "analysis": {"gear4": {"depth": {"primary": "a/big", "fallback": []},
                                   "breadth": {"primary": "b/big", "fallback": []}}},
            "post_analysis": {
                "consolidation": {"primary": "a/big", "fallback": ["a/fb"]},
                "verification": {"primary": "a/big", "fallback": []},
                "formatter": {"primary": "a/big", "fallback": []},
            },
        },
    }

    def test_single_field_diff_with_fallbacks_preserved(self):
        plus = campaign.build_optimum_plus(self.OPTIMUM, "claude-code:claude-opus-4.8")
        # Exact duplicate: ONLY the consolidation primary changes; the
        # fallback chain is preserved (user spec 2026-06-12).
        self.assertEqual(plus["cells"]["post_analysis"]["consolidation"],
                         {"primary": "claude-code:claude-opus-4.8",
                          "fallback": ["a/fb"]})
        self.assertEqual(plus["cells"]["post_analysis"]["verification"],
                         self.OPTIMUM["cells"]["post_analysis"]["verification"])
        self.assertEqual(plus["cells"]["analysis"], self.OPTIMUM["cells"]["analysis"])
        self.assertEqual(plus["cells"]["utility"], self.OPTIMUM["cells"]["utility"])

    def test_source_config_not_mutated(self):
        before = json.dumps(self.OPTIMUM, sort_keys=True)
        campaign.build_optimum_plus(self.OPTIMUM, "x/y")
        self.assertEqual(json.dumps(self.OPTIMUM, sort_keys=True), before)

    def test_lane_registered(self):
        self.assertEqual(campaign.ORA_PIPELINES.get("optimum-plus"),
                         "campaign-optimum-plus")
        self.assertIn("optimum-plus", campaign.ALL_PIPELINES)
        self.assertIn("optimum-plus",
                      [p for p, _ in campaign.DOC_PIPELINE_ORDER])


class TestSinglePassClaudeCode(unittest.TestCase):
    EP = {"id": "claude-code:claude-opus-4.8", "service": "claude-code",
          "model_id": "claude-opus-4-8"}

    def _cli(self, stdout, returncode=0, stderr=""):
        m = mock.Mock()
        m.stdout, m.returncode, m.stderr = stdout, returncode, stderr
        return m

    def test_subscription_single_pass_parses_and_verifies(self):
        payload = json.dumps({
            "result": "Answer.", "is_error": False,
            "usage": {"input_tokens": 999, "output_tokens": 999},
            "modelUsage": {
                "claude-opus-4-8-20260301": {"inputTokens": 120,
                                             "outputTokens": 800},
                "claude-haiku-4-5-20251001": {"inputTokens": 30,
                                              "outputTokens": 4}}})
        captured = {}

        def fake_run(cmd, **kw):
            captured["cmd"], captured["kw"] = cmd, kw
            return self._cli(payload)

        with mock.patch.object(campaign.subprocess, "run",
                               side_effect=fake_run), \
             mock.patch.dict(campaign.os.environ,
                             {"ANTHROPIC_API_KEY": "sk-x"}):
            rec = campaign.single_pass_call(dict(self.EP), "prompt")
        self.assertEqual(rec["via"], "claude-code-subscription")
        # Requested model's entry, not the helper's, not the total.
        self.assertEqual(rec["prompt_tokens"], 120)
        self.assertEqual(rec["completion_tokens"], 800)
        self.assertEqual(rec["served_model"], "claude-opus-4-8-20260301")
        self.assertNotIn("ANTHROPIC_API_KEY", captured["kw"]["env"])
        self.assertIn("--tools", captured["cmd"])

    def test_substituted_model_raises(self):
        payload = json.dumps({"result": "x", "is_error": False,
                              "modelUsage": {"claude-sonnet-4-6": {}}})
        with mock.patch.object(campaign.subprocess, "run",
                               return_value=self._cli(payload)):
            with self.assertRaises(RuntimeError):
                campaign.single_pass_call(dict(self.EP), "prompt")

    def test_rate_limit_marks_error(self):
        with mock.patch.object(campaign.subprocess, "run",
                               return_value=self._cli(
                                   "", returncode=1,
                                   stderr="usage limit reached")):
            with self.assertRaises(RuntimeError) as cm:
                campaign.single_pass_call(dict(self.EP), "prompt")
        self.assertIn("rate-limited", str(cm.exception))


class TestSinglePassFidelity(unittest.TestCase):
    def test_substituted_model_raises(self):
        fake = {"choices": [{"message": {"content": "x"}}],
                "usage": {}, "model": "some/other-model"}
        ep = {"service": "openrouter", "id": "qwen/qwen3.5-9b",
              "openrouter_fallback_model_id": "qwen/qwen3.5-9b"}
        with mock.patch.object(campaign, "_keyring_get", return_value="k"), \
             mock.patch.object(
                 campaign.network_policy, "openrouter_request_bytes",
                 return_value=(json.dumps(fake).encode(), mock.sentinel.destination),
             ):
            with self.assertRaises(RuntimeError):
                campaign.single_pass_call(ep, "prompt")

    def test_dated_anthropic_variant_passes(self):
        fake = {"content": [{"type": "text", "text": "x"}],
                "usage": {"input_tokens": 1, "output_tokens": 2},
                "model": "claude-opus-4-8-20260301"}
        ep = {"service": "claude", "model_id": "claude-opus-4-8",
              "id": "anthropic/claude-opus-4.8"}
        with mock.patch.object(campaign, "_keyring_get", return_value="k"), \
             mock.patch.object(campaign.urllib.request, "urlopen") as uo:
            uo.return_value.__enter__.return_value.read.return_value = \
                json.dumps(fake).encode()
            rec = campaign.single_pass_call(ep, "prompt")
        self.assertEqual(rec["served_model"], "claude-opus-4-8-20260301")


class TestAggregation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._orig = (campaign.CAMPAIGN_DIR, campaign.MANIFEST_PATH,
                      campaign.SNAPSHOT_PATH)
        campaign.CAMPAIGN_DIR = Path(self.tmp.name)
        campaign.MANIFEST_PATH = Path(self.tmp.name) / "campaign-manifest.jsonl"
        campaign.SNAPSHOT_PATH = Path(self.tmp.name) / "campaign-configs-snapshot.json"
        self.addCleanup(self._restore)

    def _restore(self):
        (campaign.CAMPAIGN_DIR, campaign.MANIFEST_PATH,
         campaign.SNAPSHOT_PATH) = self._orig

    def test_totals_roll_up_and_failed_excluded(self):
        campaign.append_manifest({"technique": "a", "pipeline": "premium",
                                  "status": "ok", "cost_usd": 1.5,
                                  "prompt_tokens": 1000, "completion_tokens": 2000,
                                  "visuals": 1, "wall_seconds": 60})
        campaign.append_manifest({"technique": "b", "pipeline": "premium",
                                  "status": "ok", "cost_usd": 0.5,
                                  "prompt_tokens": 500, "completion_tokens": 700,
                                  "visuals": 0, "wall_seconds": 30})
        campaign.append_manifest({"technique": "c", "pipeline": "premium",
                                  "status": "failed", "cost_usd": 9.9})
        campaign.append_manifest({"technique": "a", "pipeline": "single-pass",
                                  "status": "ok", "cost_usd": None,
                                  "prompt_tokens": 10, "completion_tokens": 20,
                                  "visuals": 0, "wall_seconds": 5})
        summary = campaign.aggregate()
        prem = summary["per_pipeline"]["premium"]
        self.assertEqual(prem["runs"], 2)
        self.assertAlmostEqual(prem["cost_usd"], 2.0)
        sp = summary["per_pipeline"]["single-pass"]
        self.assertEqual(sp["unpriced_runs"], 1)
        self.assertEqual(summary["grand_total"]["runs"], 3)
        self.assertTrue((campaign.CAMPAIGN_DIR / "cost-summary.md").exists())


if __name__ == "__main__":
    unittest.main()
