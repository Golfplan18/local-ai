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

### The four configurations

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

## Lenses

### T1-territory

#### `anchoring`

**Foregrounds lens:** `anchoring`  ·  mental-model
**Host mode:** `propaganda-audit`  ·  **Also loadable in:** `argument-audit`

1. Audit the anchoring tactic in this ad.
2. Ignored.
"""


class TestParseCorpus(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
        tmp.write(MINI_CORPUS)
        tmp.close()
        self.path = Path(tmp.name)
        self.addCleanup(lambda: self.path.unlink(missing_ok=True))

    def test_counts_and_kinds(self):
        techs = campaign.parse_corpus(self.path)
        self.assertEqual(len(techs), 4)
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
        self.assertNotIn("The four configurations", [t.id for t in techs])

    def test_select_all_some_and_ids(self):
        techs = campaign.parse_corpus(self.path)
        self.assertEqual(len(campaign.select_techniques(techs, "all")), 4)
        picked = campaign.select_techniques(techs, "cui-bono,anchoring")
        self.assertEqual([t.id for t in picked], ["cui-bono", "anchoring"])
        with self.assertRaises(SystemExit):
            campaign.select_techniques(techs, "no-such-technique")


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
        campaign.append_manifest({"technique": "a", "pipeline": "premium",
                                  "status": "failed"})
        campaign.append_manifest({"technique": "a", "pipeline": "premium",
                                  "status": "ok"})
        campaign.append_manifest({"technique": "b", "pipeline": "premium",
                                  "status": "failed"})
        done = campaign.load_manifest()
        self.assertEqual(done[("a", "premium")]["status"], "ok")
        self.assertEqual(done[("b", "premium")]["status"], "failed")

    def test_malformed_lines_skipped(self):
        campaign.MANIFEST_PATH.write_text('not json\n{"technique":"a"}\n'
                                          '{"technique":"a","pipeline":"x","status":"ok"}\n')
        done = campaign.load_manifest()
        self.assertEqual(list(done.keys()), [("a", "x")])


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
             mock.patch.object(campaign.urllib.request, "urlopen") as uo:
            uo.return_value.__enter__.return_value.read.return_value = \
                json.dumps(fake).encode()
            rec = campaign.single_pass_call(ep, "prompt")
        self.assertEqual(rec["via"], "openrouter")
        self.assertEqual(rec["completion_tokens"], 500)

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

    def _trace(self, usage_records, step_files=None):
        tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        Path(tmp, "usage.jsonl").write_text(
            "\n".join(json.dumps(r) for r in usage_records))
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
             mock.patch.object(campaign.urllib.request, "urlopen") as uo:
            uo.return_value.__enter__.return_value.read.return_value = \
                json.dumps(fake).encode()
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
