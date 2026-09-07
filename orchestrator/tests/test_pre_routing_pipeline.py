"""Tests for the Phase 9 four-stage pre-routing pipeline.

Covers Stage 1 (pre-analysis filter), Stage 2 (sufficiency analyzer),
Stage 3 (input completeness check), the dispatch-announcement helper,
and the orchestrating run_pre_routing_pipeline entry point.
"""
from __future__ import annotations

import os
import sys
import unittest
import builtins
import importlib.util
import io
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator"))

import boot  # noqa: E402


class TestStage1PreAnalysisFilter(unittest.TestCase):
    def test_greeting_is_bypassed(self):
        r = boot.stage1_pre_analysis_filter("Hi there!")
        self.assertTrue(r["bypass_to_direct_response"])
        self.assertEqual(r["visual_exception"], "greeting_or_acknowledgement")

    def test_thanks_is_bypassed(self):
        r = boot.stage1_pre_analysis_filter("Thanks, that was helpful.")
        self.assertTrue(r["bypass_to_direct_response"])

    def test_factual_lookup_is_bypassed(self):
        r = boot.stage1_pre_analysis_filter("What time is it in Tokyo?")
        self.assertTrue(r["bypass_to_direct_response"])
        self.assertNotIn("visual_exception", r)

    def test_translation_is_bypassed(self):
        r = boot.stage1_pre_analysis_filter("Translate this paragraph into French.")
        self.assertTrue(r["bypass_to_direct_response"])
        self.assertNotIn("visual_exception", r)

    def test_explicit_opt_out_wins_over_translation_bypass(self):
        r = boot.stage1_pre_analysis_filter(
            "Translate this paragraph into French. No analysis."
        )
        self.assertTrue(r["bypass_to_direct_response"])
        self.assertEqual(r["visual_exception"], "explicit_opt_out")

    def test_negation_bypasses_analytical_signal(self):
        r = boot.stage1_pre_analysis_filter("Don't analyze this; just summarize.")
        self.assertTrue(r["bypass_to_direct_response"])
        self.assertEqual(r["visual_exception"], "explicit_opt_out")

    def test_strong_signal_passes_filter(self):
        r = boot.stage1_pre_analysis_filter("Run an ACH on these explanations.")
        self.assertFalse(r["bypass_to_direct_response"])
        self.assertGreater(len(r["matches"]), 0)

    def test_steelman_signal_matches(self):
        r = boot.stage1_pre_analysis_filter("Steelman this op-ed quickly.")
        self.assertFalse(r["bypass_to_direct_response"])
        modes = {m["mode"] for m in r["matches"]}
        self.assertIn("steelman-construction", modes)

    def test_word_boundary_blocks_short_signal_collision(self):
        # Signal "Ma" (T19 ma-reading) must NOT match inside "Make"
        r = boot.stage1_pre_analysis_filter("Make some coffee for the meeting.")
        modes = {m["mode"] for m in r["matches"]}
        self.assertNotIn("ma-reading", modes)


class TestStage2SufficiencyAnalyzer(unittest.TestCase):
    def test_strong_dispatch_steelman(self):
        prompt = "Steelman this argument."
        s1 = boot.stage1_pre_analysis_filter(prompt)
        s2 = boot.stage2_sufficiency_analyzer(prompt, s1)
        self.assertEqual(s2["dispatched_mode_id"], "steelman-construction")
        self.assertEqual(s2["disambiguation_questions_asked"], [])

    def test_strong_dispatch_cui_bono(self):
        prompt = "Who benefits from this zoning amendment?"
        s1 = boot.stage1_pre_analysis_filter(prompt)
        s2 = boot.stage2_sufficiency_analyzer(prompt, s1)
        self.assertEqual(s2["dispatched_mode_id"], "cui-bono")

    def test_conflict_surfaces_question(self):
        prompt = "Quick deep-dive on this argument."
        s1 = boot.stage1_pre_analysis_filter(prompt)
        s2 = boot.stage2_sufficiency_analyzer(prompt, s1)
        self.assertIsNone(s2["dispatched_mode_id"])
        self.assertGreater(len(s2["disambiguation_questions_asked"]), 0)

    def test_no_strong_signals_falls_back_to_pattern_a(self):
        prompt = "tell me something interesting"
        s1 = boot.stage1_pre_analysis_filter(prompt)
        s2 = boot.stage2_sufficiency_analyzer(prompt, s1)
        self.assertIsNone(s2["dispatched_mode_id"])
        # Pattern-A canonical question stem
        joined = " ".join(s2["disambiguation_questions_asked"])
        self.assertIn("Quick check", joined)


class TestStage3InputCompletenessCheck(unittest.TestCase):
    def test_cui_bono_with_short_prompt_missing_input(self):
        r = boot.stage3_input_completeness_check(
            "cui-bono", "who benefits", {}
        )
        self.assertFalse(r["inputs_complete"])
        self.assertGreater(len(r["missing_fields"]), 0)
        self.assertIsNotNone(r["completeness_question"])

    def test_unknown_mode_passes_through_safely(self):
        r = boot.stage3_input_completeness_check(
            "definitely-not-a-real-mode", "anything", {}
        )
        self.assertTrue(r["inputs_complete"])

    def test_long_situation_satisfies_situation_field(self):
        prompt = (
            "Who benefits from this new municipal zoning amendment that "
            "the city council passed last week reducing setback requirements "
            "for multi-family housing in transit-rich corridors near downtown?"
        )
        r = boot.stage3_input_completeness_check("cui-bono", prompt, {})
        # Long, substantive prompt should satisfy situation_or_artifact
        self.assertTrue(r["inputs_complete"])

    def test_competing_hypotheses_selected_contract_controls_list_requirement(self):
        accessible = boot.stage3_input_completeness_check(
            "competing-hypotheses",
            (
                "Our warehouse has started missing same-day shipping targets "
                "even though order volume and staffing have not changed. "
                "Generate plausible competing hypotheses and weigh them against "
                "what we know."
            ),
            {},
        )
        self.assertEqual(accessible["contract_version"], "accessible_mode")
        self.assertTrue(accessible["inputs_complete"])
        self.assertEqual(accessible["missing_fields"], [])

        expert = boot.stage3_input_completeness_check(
            "competing-hypotheses",
            (
                "Build an ACH matrix using Heuer's diagnosticity method for "
                "our warehouse shipping delays."
            ),
            {},
        )
        self.assertEqual(expert["contract_version"], "expert_mode")
        self.assertFalse(expert["inputs_complete"])
        self.assertEqual(
            expert["missing_fields"],
            ["hypothesis_set", "evidence_inventory"],
        )
        self.assertIsNotNone(expert["completeness_question"])


class TestDispatchAnnouncement(unittest.TestCase):
    def test_format_has_italic_parenthetical(self):
        s = boot.format_dispatch_announcement("plain language", "named technique")
        self.assertEqual(s, "plain language *(named technique)*")

    def test_compose_for_steelman(self):
        s = boot.compose_dispatch_announcement(
            "steelman-construction", "Steelman this op-ed."
        )
        self.assertIn("strongest case", s.lower())
        self.assertIn("*(", s)
        self.assertIn(")*", s)

    def test_compose_falls_back_for_unknown_mode(self):
        # Even an unknown mode should produce some announcement (no crash)
        s = boot.compose_dispatch_announcement("unknown-mode", "anything")
        self.assertIn("*(", s)
        self.assertIn(")*", s)


class TestRunPreRoutingPipeline(unittest.TestCase):
    def test_bypass_path(self):
        r = boot.run_pre_routing_pipeline("Hi there!")
        self.assertTrue(r["bypass_to_direct_response"])
        self.assertIsNone(r["dispatched_mode_id"])
        self.assertEqual(r["visual_exception"], "greeting_or_acknowledgement")

    def test_strong_dispatch_no_clarification(self):
        r = boot.run_pre_routing_pipeline(
            "Steelman this argument: people should be allowed to drive any "
            "car they want without restrictions whatsoever, because freedom."
        )
        self.assertEqual(r["dispatched_mode_id"], "steelman-construction")
        self.assertIsNotNone(r["dispatch_announcement"])

    def test_weak_signal_returns_disambiguation_question(self):
        r = boot.run_pre_routing_pipeline("Look at this op-ed.")
        # Could be Stage 2 disambiguation or Stage 3 missing input
        self.assertIsNotNone(r["pending_clarification"])

class TestRoutingCorpusOracle(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="routing-oracle-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.corpus = self.root / "corpus.md"
        self.report = self.root / "report.md"
        self.modes = (self.root / "vault-modes", self.root / "runtime-modes")
        for directory in self.modes:
            directory.mkdir()
            (directory / "example-mode.md").write_text("# Synthetic mode\n", encoding="utf-8")
        self.imports = []
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name == "boot":
                self.imports.append(name)
                raise AssertionError("Runtime imported before admission")
            return original_import(name, *args, **kwargs)

        self.guard_import = guarded_import
        spec = importlib.util.spec_from_file_location(
            "routing_corpus_oracle", Path(WORKSPACE) / "scripts/run-corpus-routing-test.py")
        self.oracle = importlib.util.module_from_spec(spec)
        with patch("builtins.__import__", self.guard_import):
            spec.loader.exec_module(self.oracle)
        for name, value in (("CORPUS_PATH", self.corpus), ("DEFAULT_REPORT", self.report),
                            ("VAULT_MODES", self.modes[0]), ("RUNTIME_MODES", self.modes[1])):
            setattr(self.oracle, name, value)

    def item(self, index=1, s1="PASS", s2="dispatch=`example-mode`", s3="complete", s4="execute", prompt='"Synthetic task"'):
        return (f"### Prompt {index}\n**Prompt:** {prompt}\n"
                f"**Expected Stage 1:** {s1}\n**Expected Stage 2:** {s2}\n"
                f"**Expected Stage 3:** {s3}\n**Expected Stage 4:** {s4}\n"
                "**Notes:** Original requirement retained.\n\n")

    def source(self, content):
        self.corpus.write_text("## Sub-corpus 1 — Synthetic\n\n" + content, encoding="utf-8")

    def admitted(self, **kwargs):
        self.source(self.item(**kwargs))
        cases, problems = self.oracle.admit_corpus(self.corpus, self.modes)
        self.assertEqual(problems, [])
        self.assertEqual(len(cases), 1)
        return cases[0]

    def routing(self, bypass=False, mode="example-mode", complete=True, missing=(), pause=None):
        return {"stage1_output": {}, "stage2_output": None if bypass else {},
                "stage3_output": None if bypass or pause == "stage2" else {
                    "inputs_complete": complete, "missing_fields": list(missing)},
                "bypass_to_direct_response": bypass,
                "dispatched_mode_id": None if bypass or pause == "stage2" else mode,
                "pending_clarification_stage": pause,
                "pending_clarification": "A question" if pause else None}

    def run_main(self, args=()):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.oracle.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def assert_refused_without_effects(self, category, prompt=None):
        self.report.write_text("existing report sentinel", encoding="utf-8")
        with patch("builtins.__import__", self.guard_import), \
                patch.object(self.oracle, "evaluate_case") as evaluate, \
                patch.object(self.oracle, "aggregate") as aggregate, \
                patch.object(self.oracle, "write_report") as report:
            for args in ((), ("--validate-only",)):
                code, out, err = self.run_main(args)
                self.assertEqual(code, 2, err)
                self.assertIn(category, err)
                if prompt is not None:
                    self.assertIn(f"Prompt {prompt}", err)
                self.assertEqual(out, "")
                self.assertNotRegex(err, r"Stage [123]: [\d.]+%")
            evaluate.assert_not_called()
            aggregate.assert_not_called()
            report.assert_not_called()
        self.assertEqual(self.imports, [])
        self.assertEqual(self.report.read_text(encoding="utf-8"), "existing report sentinel")
        return err

    def test_corpus_admission_precedes_effects(self):
        valid = self.item()
        malformed = (
            "", valid + self.item(), valid.replace("**Prompt:**", "**No prompt:**"),
            valid.replace("**Expected Stage 3:** complete\n", "") + self.item(2),
            valid.replace("**Expected Stage 4:** execute", "**Expected Stage 4:** "),
            valid + "### Prompt broken\n**Prompt:** Neighbor\n",
            valid.replace("**Expected Stage 2:**", "**Expected Stage 1:** PASS\n**Expected Stage 2:**"),
        )
        for content in malformed:
            with self.subTest(content=content):
                self.source(content)
                self.assert_refused_without_effects("INVALID CORPUS")
        self.corpus.write_text(valid, encoding="utf-8")
        self.assert_refused_without_effects("INVALID CORPUS", 1)
        # A missing field cannot be borrowed from the following complete item.
        broken = valid.replace("**Expected Stage 3:** complete\n", "")
        self.source(broken + self.item(2))
        cases, problems = self.oracle.parse_corpus(self.corpus)
        self.assertEqual([case["index"] for case in cases], [2])
        self.assertEqual(problems[0]["original"], broken)
        self.assertEqual(problems[0]["line"], 3)
        for problem_source in ("absent", "undecodable"):
            with self.subTest(problem_source=problem_source):
                if problem_source == "absent":
                    self.corpus.unlink()
                else:
                    self.corpus.write_bytes(b"\xff")
                self.assert_refused_without_effects("INACCESSIBLE SOURCE")
        self.source(valid)
        for source_index in (0, 1):
            for shape in ("missing", "file", "empty", "nested"):
                with self.subTest(source_index=source_index, shape=shape):
                    bad = self.root / f"source-{source_index}-{shape}"
                    if shape == "file":
                        bad.write_text("not a directory", encoding="utf-8")
                    elif shape in ("empty", "nested"):
                        bad.mkdir()
                        if shape == "nested":
                            (bad / "Modes").mkdir()
                            (bad / "Modes/example-mode.md").write_text("mode", encoding="utf-8")
                    name = ("VAULT_MODES", "RUNTIME_MODES")[source_index]
                    with patch.object(self.oracle, name, bad):
                        err = self.assert_refused_without_effects("INACCESSIBLE SOURCE")
                        self.assertNotIn("STALE OR INVALID TARGET", err)
        with patch.object(Path, "iterdir", side_effect=PermissionError("source enumeration denied")):
            self.assert_refused_without_effects("INACCESSIBLE SOURCE")
        with patch.object(Path, "read_text", side_effect=PermissionError("source read denied")):
            # Sentinel comparison is outside this mock so refusal remains tested.
            with patch("builtins.__import__", self.guard_import):
                code, out, err = self.run_main()
                self.assertEqual((code, out), (2, ""))
                self.assertIn("INACCESSIBLE SOURCE", err)
                self.assertNotIn("STALE OR INVALID TARGET", err)
        mode_file = self.modes[1] / "example-mode.md"
        mode_file.write_bytes(b"\xff")
        self.assert_refused_without_effects("INACCESSIBLE SOURCE")
        mode_file.write_text("mode", encoding="utf-8")
        for target in ("red-team", "index", "INDEX", "Example-mode", "example_mode"):
            with self.subTest(target=target):
                self.source(valid + self.item(10, s2=f"dispatch=`{target}`"))
                category = "STALE OR INVALID TARGET"
                err = self.assert_refused_without_effects(category, 10)
                self.assertIn(self.item(10, s2=f"dispatch=`{target}`"), err)
                if category == "STALE OR INVALID TARGET":
                    self.assertIn("does not exist as an exact regular mode file", err)
                    self.assertIn("Stage 2", err)
        unsupported = (
            {"s1": "PASS or BYPASS"}, {"s1": "PASS — if attached"},
            {"s1": "PASS — record a warning"},
            {"s2": "dispatch=`example-mode` or `another-mode`"},
            {"s2": "dispatch=`example-mode` (T7 framing wins; action-plan parse)"},
            {"s2": "ask Q1; answer A → dispatch=`example-mode`"},
            {"s2": "disambiguate=T3 territory question"}, {"s2": "mask the task"},
            {"s2": "dispatch=`example-mode` at Tier-2"}, {"s3": "complete if attached"},
            {"s3": "complete via prior context"}, {"s3": "complete (PDF attached)"},
            {"s3": "complete enough for context-gathering"}, {"s3": "complete (with a warning)"},
            {"s3": "missing-input=`artifact` if not pasted"},
            {"s3": "missing-input=`artifact` or `subject`"},
            {"s3": "missing-input (`first_field` and `second_field`)"},
            {"s3": "missing-input (parties, BATNA)"},
            {"s3": "complete (record success in a log)"},
            {"s3": "missing-input=`artifact`; graceful-degrade to `example-mode`"},
            {"s3": "flag deferred; offer another mode"}, {"s3": "resumed"},
            {"s2": "ask", "s3": "complete"}, {"s1": "BYPASS", "s2": "dispatch=`example-mode`", "s3": "N/A"},
        )
        for fields in unsupported:
            with self.subTest(fields=fields):
                original = self.item(2, **fields)
                self.source(valid + original)
                err = self.assert_refused_without_effects("UNSUPPORTED MEASUREMENT", 2)
                self.assertIn(original, err)
                self.assertNotIn("INVALID CORPUS", err)
        self.source(valid)
        with patch("builtins.__import__", self.guard_import), \
                patch.object(self.oracle, "evaluate_case") as evaluate, \
                patch.object(self.oracle, "aggregate") as aggregate, \
                patch.object(self.oracle, "write_report") as report:
            code, out, err = self.run_main(("--validate-only",))
            self.assertEqual((code, err), (0, ""))
            self.assertIn("Corpus admitted: 1 cases", out)
            evaluate.assert_not_called()
            aggregate.assert_not_called()
            report.assert_not_called()

    def test_supported_measurements_are_truthful(self):
        samples = (
            ({"s1": "BYPASS — greeting; no analytical signal.", "s2": "N/A (filter blocked)", "s3": "N/A"}, self.routing(bypass=True), (True, None, None)),
            ({"s1": "PASS — red-team strong T15 signal", "s3": "complete (situation described in prompt)"}, self.routing(), (True, True, True)),
            ({"s1": "PASS!", "s2": 'dispatch: “example-mode”', "s3": "missing-input=`first_field` + `second_field`"}, self.routing(complete=False, missing=("first_field", "second_field")), (True, True, True)),
            ({"s2": "dispatch='example-mode'", "s3": "missing-input=first_field AND second_field"}, self.routing(complete=False, missing=("first_field",)), (True, True, False)),
            ({"s3": "missing-input=`artifact` (no policy text in prompt)"}, self.routing(complete=False, missing=("artifact",), pause="stage3"), (True, True, True)),
            ({"s3": "underspecified"}, self.routing(complete=False), (True, True, True)),
            ({"s3": "incomplete"}, self.routing(complete=True), (True, True, False)),
            ({"s3": "missing-input"}, self.routing(complete=True, pause="stage3"), (True, True, False)),
            ({"s2": "ask a disambiguation question", "s3": "N/A until answered"}, self.routing(pause="stage2"), (True, True, None)),
            ({"s2": "disambiguate", "s3": "N/A"}, self.routing(), (True, False, False)),
            ({}, self.routing(mode="wrong-mode"), (True, False, True)),
            ({}, self.routing(bypass=True), (False, False, False)),
            ({}, self.routing(pause="stage2"), (True, False, False)),
            ({}, self.routing(complete=False), (True, True, False)),
        )
        for fields, actual, expected in samples:
            with self.subTest(fields=fields, actual=actual):
                case = self.admitted(**fields)
                result = self.oracle.evaluate_case(case, Mock(return_value=actual))
                self.assertEqual(tuple(result[f"s{s}_pass"] for s in (1, 2, 3)), expected)
        case = self.admitted(prompt='“Preserve the whole task, including ‘quotes’.”', s4="deferred Stage 4 requirement stays unmeasured")
        pipeline = Mock(return_value=self.routing())
        self.oracle.evaluate_case(case, pipeline)
        pipeline.assert_called_once_with("Preserve the whole task, including ‘quotes’.")
        self.assertEqual(case["expected_stage4"], "deferred Stage 4 requirement stays unmeasured")
        for stage in (1, 2, 3):
            with self.subTest(absent_stage=stage):
                actual = self.routing()
                actual[f"stage{stage}_output"] = None
                result = self.oracle.evaluate_case(case, Mock(return_value=actual))
                self.assertIs(result[f"s{stage}_pass"], False)
        blocked = self.oracle.evaluate_case(case, Mock(return_value=self.routing(pause="stage2")))
        self.assertEqual(blocked["cascade_non_execution"], ["s3"])
        self.assertEqual(self.oracle.aggregate([blocked])["overall"]["s3"], {
            "accuracy": 0.0, "denominator": 1, "not_applicable": 0, "cascade_non_execution": 1})
        bypass_case = self.admitted(s1="BYPASS", s2="N/A", s3="N/A")
        unexpected_execution = self.oracle.evaluate_case(bypass_case, Mock(return_value=self.routing()))
        self.assertIs(unexpected_execution["s3_pass"], False)
        self.assertEqual(self.oracle.aggregate([blocked, unexpected_execution])["overall"]["s3"], {
            "accuracy": 0.0, "denominator": 1, "not_applicable": 1, "cascade_non_execution": 1})

    def test_reports_are_truthful_and_preserved(self):
        self.admitted()
        for actual, expected in ((self.routing(), "100.0%"), (self.routing(bypass=True), "0.0%")):
            with self.subTest(expected=expected), patch.object(boot, "run_pre_routing_pipeline", return_value=actual):
                self.report.write_text("old report", encoding="utf-8")
                code, out, err = self.run_main()
                self.assertEqual((code, err), (0, ""))
                report = self.report.read_text(encoding="utf-8")
                self.assertIn(f"Stage 3: {expected}", out)
                self.assertIn(f"Stage 3: {expected}", report)
                self.assertIn("measured denominator: 1", report)
                self.assertIn("Stage 4 and targeted-question semantics are unmeasured", report)
                for historical in ("95.0%", "92.3%", "83.3%", "All three stages now meet"):
                    self.assertNotIn(historical, report)
                if expected == "0.0%":
                    self.assertIn("cascade non-execution: 1", report)
                    self.assertIn("Cascade non-execution (required stage did not run): S2, S3", report)
                    self.assertIn(self.item().rstrip(), report)
        self.report.write_text("preserve me", encoding="utf-8")
        unrelated = self.root / ".report.md.other.tmp"
        unrelated.write_text("not this writer's file", encoding="utf-8")
        with patch.object(boot, "run_pre_routing_pipeline", return_value=self.routing()), \
                patch.object(self.oracle._rp.os, "replace", side_effect=OSError("replacement denied")):
            code, out, err = self.run_main()
            self.assertEqual((code, out), (1, ""))
            self.assertIn("replacement denied", err)
        self.assertEqual(self.report.read_text(encoding="utf-8"), "preserve me")
        self.assertEqual(list(self.root.glob(".report.md.*.tmp")), [unrelated])
        with patch.object(boot, "run_pre_routing_pipeline", side_effect=RuntimeError("evaluation failed")):
            code, out, err = self.run_main()
            self.assertEqual((code, out), (1, ""))
            self.assertIn("evaluation failed", err)
        self.assertEqual(self.report.read_text(encoding="utf-8"), "preserve me")
        with self.assertRaisesRegex(ValueError, "empty result set"):
            self.oracle.aggregate([])
        self.admitted(s1="BYPASS", s2="N/A", s3="N/A")
        with patch.object(boot, "run_pre_routing_pipeline", return_value=self.routing(bypass=True)):
            code, out, err = self.run_main()
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Stage 1: 100.0%", out)
        for stage in (2, 3):
            self.assertIn(f"Stage {stage}: not measured (measured denominator: 0; not applicable: 1", out)
            self.assertNotRegex(out, rf"Stage {stage}: [\d.]+%")
        self.assertIn("Stage 3: not measured", self.report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
