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
import json
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
        self.canonical_sources = (self.oracle.CORPUS_PATH, self.oracle.VAULT_MODES, self.oracle.RUNTIME_MODES)
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

    def structured(self, *, s1=None, s2=None, s3=None, fixture=None, variants=None):
        content = self.item(s1=json.dumps(s1 or {"kind": "pass"}),
                            s2=json.dumps(s2 or {"kind": "dispatch", "targets": ["example-mode"]}),
                            s3=json.dumps(s3 or {"kind": "complete"}))
        if fixture is not None:
            content += "**Fixture:** " + json.dumps(fixture) + "\n"
        if variants is not None:
            content += "**Variants:** " + json.dumps(variants) + "\n"
        self.source(content)
        cases, problems = self.oracle.admit_corpus(self.corpus, self.modes)
        self.assertEqual(problems, [])
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
        corpus, vault_modes, runtime_modes = self.canonical_sources
        with patch("builtins.__import__", self.guard_import), patch.object(self.oracle, "VAULT_MODES", vault_modes):
            cases, problems = self.oracle.admit_corpus(corpus, (vault_modes, runtime_modes))
        self.assertEqual(problems, [])
        self.assertEqual([case["index"] for case in cases], list(range(1, 221)))
        canonical = {case["index"]: case for case in cases}
        for index in (51, 191, 193):
            requirement = (canonical[index]["variants"][0]["turns"][0]["s2"] if index == 193
                           else canonical[index]["expectations"]["s2"])
            for text, expected in (
                ("Is the question about whether the argument holds together internally, or about the frame/lens it's using to see the issue, or about both at once?", True),
                ("Is the question about whether the argument holds together internally, or about the frame/lens it's using to see the issue?", False),
            ):
                with self.subTest(canonical_t1_question=index, question=text):
                    actual = self.routing(pause="stage2")
                    actual["pending_clarification"] = text
                    self.assertEqual(self.oracle.compare_requirement("s2", requirement, actual), (expected, False))
        for mode, tier, expected in (("domain-induction", 2, False),
                                     ("domain-induction", 3, True),
                                     ("full-induction", 3, False)):
            with self.subTest(induction_dispatch=mode, tier=tier):
                actual = self.routing(mode=mode)
                actual["triage_tier"] = tier
                self.assertEqual(self.oracle.compare_requirement(
                    "s2", canonical[41]["expectations"]["s2"], actual), (expected, False))
        for text, expected in (
            ("Which would you like: quick orientation, terrain mapping, or full induction?", True),
            ("Which would you like: quick orientation, terrain mapping, or domain induction?", True),
            ("Which would you like: quick orientation or terrain mapping?", False),
        ):
            with self.subTest(induction_choice=text):
                actual = self.routing(pause="stage2")
                actual["pending_clarification"] = text
                self.assertEqual(self.oracle.compare_requirement(
                    "s2", canonical[205]["expectations"]["s2"], actual), (expected, False))
        induction_offer = "Choose quick orientation at Tier 1 or terrain mapping at Tier 2, or full induction."
        for text, expected in (
            (induction_offer, False),
            (induction_offer + " All three methods still need the domain.", True),
            (induction_offer + " Each method requires a topic.", True),
            (induction_offer + " Full induction requires a domain.", False),
            (induction_offer + " Both choices need the domain.", False),
            (induction_offer + " All three methods need the domain. Quick orientation can proceed without it.", False),
        ):
            with self.subTest(induction_input=text):
                actual = self.routing(complete=False, missing=["domain_name"])
                actual["stage3_output"]["graceful_degradation_offer"] = text
                self.assertEqual(self.oracle.compare_requirement(
                    "s3", canonical[185]["expectations"]["s3"], actual), (expected, False))
        action_plan = self.routing(mode="pre-mortem-action")
        action_plan["territory"] = "T6-future-exploration"
        self.assertEqual(self.oracle.compare_requirement(
            "s2", canonical[141]["expectations"]["s2"], action_plan), (True, False))
        for index in (85, 95, 118, 130):
            requirement = canonical[index]["expectations"]["s3"]
            actual = self.routing()
            actual["stage3_output"].update(
                offered_mode_ids=requirement["offer_targets"],
                deferred_offer="Would you like another method?")
            self.assertEqual(self.oracle.compare_requirement("s3", requirement, actual), (False, False))
            actual["stage3_output"]["deferred_offer"] = "Choose " + " or ".join(requirement["offer_targets"])
            self.assertEqual(self.oracle.compare_requirement("s3", requirement, actual), (True, False))
        for index, missing_material in ((181, "problem description"), (186, "argument text"),
                                        (189, "negotiation context"), (190, "system description"),
                                        (202, "subject"), (204, "argument text")):
            requirement = canonical[index]["expectations"]["s3"]
            actual = self.routing(complete=False, missing=requirement["fields"])
            lighter = requirement["offer_targets"][0]
            tier = requirement["offer_tiers"][lighter]
            offer = f"Choose {lighter} at Tier {tier} or {requirement['heavier']}."
            for text, expected in (
                (offer, False),
                (f"{offer} Both still require the missing {missing_material}.", True),
                (f"Choose {lighter} at Tier {tier} or provide {missing_material} for {requirement['heavier']}.", False),
                (f"{requirement['heavier']} does not require {missing_material}; {lighter} (Tier-{tier}) does not require {missing_material}.", False),
                (f"{requirement['heavier']} requires {missing_material}; {lighter} (Tier-{tier}) requires {missing_material}.", True),
                (f"{offer} Both need {missing_material}. {lighter} can proceed without {missing_material}.", False),
            ):
                with self.subTest(shared_input=index, surfaced_offer=text):
                    actual["stage3_output"]["graceful_degradation_offer"] = text
                    self.assertEqual(self.oracle.compare_requirement("s3", requirement, actual), (expected, False))
        distinct_inputs = (
            (182, "Choose competing-hypotheses at Tier 2 or differential-diagnosis at Tier 1 or bayesian-hypothesis-network.",
             ["Bayesian-hypothesis-network needs the phenomenon, hypotheses, and priors.",
              "Competing-hypotheses needs the situation description.",
              "Differential-diagnosis needs the situation description and candidate explanations."],
             "Competing-hypotheses can proceed without priors."),
            (183, "Choose root-cause-analysis at Tier 2 or causal-dag.",
             ["Causal-dag needs variables and the outcome.", "Root-cause-analysis needs the observed failure."],
             "Root-cause-analysis does not require variables."),
            (184, "Choose paradigm-suspension at Tier 2 or frame-comparison at Tier 2 or worldview-cartography.",
             ["All three methods need the subject.", "Frame-comparison needs the perspectives."], ""),
            (187, "Choose consequences-and-sequel at Tier 2 or scenario-planning at Tier 2 or wicked-future.",
             ["All three methods need the subject.", "Wicked-future needs the horizon."],
             "Consequences-and-sequel can proceed without a horizon. Scenario-planning does not require a horizon."),
            (188, "Choose cui-bono together with stakeholder-mapping or decision-clarity.",
             ["All three methods need the decision context.", "Decision-clarity needs the decision maker."],
             "Cui-bono does not require the decision maker."),
        )
        for index, offer, necessary, optional in distinct_inputs:
            requirement = canonical[index]["expectations"]["s3"]
            honest = " ".join([offer, *necessary, optional])
            samples = [(honest, True), (offer, False)]
            samples.extend((" ".join([offer, *[clause for clause in necessary if clause != absent], optional]), False)
                           for absent in necessary)
            for text, expected in samples:
                with self.subTest(distinct_missing_inputs=index, surfaced_offer=text):
                    actual = self.routing(complete=False, missing=requirement["fields"])
                    actual["stage3_output"]["graceful_degradation_offer"] = text
                    self.assertEqual(self.oracle.compare_requirement("s3", requirement, actual), (expected, False))
        # This case already supplies the situation, hypotheses, and evidence;
        # its lighter method may truthfully run without the missing priors.
        actual = self.routing(complete=False, missing=["priors"])
        actual["stage3_output"]["graceful_degradation_offer"] = (
            "Choose competing-hypotheses at Tier 2 or bayesian-hypothesis-network. "
            "Competing-hypotheses can proceed without priors.")
        self.assertEqual(self.oracle.compare_requirement(
            "s3", canonical[194]["expectations"]["s3"], actual), (True, False))
        both = canonical[209]["expectations"]["s3"]
        actual = self.routing(complete=False, missing=["domain_or_situation_to_be_mapped", "situation_or_artifact"])
        self.assertEqual(self.oracle.compare_requirement("s3", both, actual), (False, True))
        actual["stage3_observations"] = [
            {"mode": "relationship-mapping", "result": {
                "inputs_complete": False, "missing_fields": ["domain_or_situation_to_be_mapped"]}},
            {"mode": "cui-bono", "result": {
                "inputs_complete": False, "missing_fields": ["situation_or_artifact"]}},
        ]
        self.assertEqual(self.oracle.compare_requirement("s3", both, actual), (True, False))
        actual["stage3_observations"].pop()
        self.assertEqual(self.oracle.compare_requirement("s3", both, actual), (False, True))
        branch_cases = {*range(81, 114), *range(115, 120), *range(121, 131)}
        for case in cases:
            if case["index"] in branch_cases:
                with self.subTest(question_branch=case["index"]):
                    branches = [variant for variant in case["variants"] if "question_prompt" in variant]
                    self.assertTrue(branches, "The ordinary prompt cannot replace its named question/answer branch")
                    for branch in branches:
                        self.assertEqual(branch["s2"]["kind"], "question")
                        self.assertTrue(branch["turns"][0]["after_question"])
        for index, question_id in ((100, "T4-Q1"), (104, "T5-Q1"), (115, "T9-Q1"),
                                   (119, "T10-Q1"), (124, "T13-Q1")):
            with self.subTest(default_answer=index):
                case = canonical[index]
                direct = [variant for variant in case["variants"] if "question_prompt" not in variant]
                defaults = [variant for variant in case["variants"] if "question_prompt" in variant]
                self.assertEqual(len(direct), 2 if index == 104 else 1)
                self.assertEqual(len(defaults), len(direct))
                for original, branch in zip(direct, defaults):
                    self.assertEqual(original["turns"], [])
                    self.assertEqual(branch["s2"]["id"], question_id)
                    self.assertNotEqual(branch["question_prompt"], self.oracle.unquote(case["prompt"]))
                    self.assertEqual(branch.get("context", {}), original.get("context", {}))
                    self.assertEqual(len(branch["turns"]), 1)
                    answer = branch["turns"][0]
                    self.assertEqual(answer["disambiguation_answer"], "I'm not sure.")
                    self.assertEqual(answer["s1"], case["expectations"]["s1"])
                    self.assertEqual(answer["s2"], {**case["expectations"]["s2"], "tier": 2})
                    self.assertEqual(answer["s3"], original.get("s3", case["expectations"]["s3"]))
        diagram = canonical[201]
        self.assertEqual(diagram["expectations"]["s2"],
                         {"kind": "dispatch", "targets": ["spatial-reasoning"]})
        self.assertEqual(diagram["expectations"]["s3"], {"kind": "complete"})
        self.assertTrue(all(not variant["turns"] for variant in diagram["variants"]))
        for requirement in (
            {"kind": "question", "id": "T1.Q1", "alternatives": []},
            {"kind": "question", "id": "T1.Q1", "alternatives": [["logic"]], "condition": "ignore missing artifact"},
            {"kind": "dispatch", "targets": ["not-an-active-mode"]},
            {"kind": "question", "id": "sequence", "alternatives": [["first"]], "offer_sequence": [["only one"]]},
            {"kind": "question", "id": "methods", "alternatives": [["choose"]],
             "offer_targets": ["example-mode"], "offer_names": {"example-mode": []}},
            {"kind": "question", "id": "methods", "alternatives": [["choose"]],
             "offer_targets": ["example-mode"], "offer_names": {"other-mode": ["another method"]}},
        ):
            with self.subTest(structured_requirement=requirement):
                self.source(self.item(s1='{"kind":"pass"}', s2=json.dumps(requirement), s3='{"kind":"complete"}'))
                self.assert_refused_without_effects("UNSUPPORTED MEASUREMENT")
        for requirement in (
            {"kind": "missing", "fields": [], "offer_targets": ["example-mode"], "offer_tiers": {"example-mode": 4}},
            {"kind": "missing", "fields": [], "offer_tiers": {"example-mode": 2}},
            {"kind": "missing", "fields": ["artifact"], "offer_targets": ["example-mode"], "offer_inputs": {}},
            {"kind": "missing", "fields": ["artifact"], "offer_targets": ["example-mode"], "offer_inputs": {"example-mode": []}},
            {"kind": "missing", "fields": ["artifact"], "offer_targets": ["example-mode"], "offer_inputs": {"unknown-mode": [["artifact"]]}},
            {"kind": "by_mode", "checks": []},
            {"kind": "by_mode", "checks": [{"targets": ["unknown-mode"], "requirement": {"kind": "complete"}}]},
            {"kind": "by_mode", "checks": [{"targets": ["example-mode"], "requirement": {"kind": "complete", "unmeasured": True}}]},
        ):
            with self.subTest(input_association=requirement):
                self.source(self.item(s1='{"kind":"pass"}', s2='{"kind":"dispatch","targets":["example-mode"]}', s3=json.dumps(requirement)))
                self.assert_refused_without_effects("UNSUPPORTED MEASUREMENT")
        self.source(self.item())
        with patch.dict(os.environ, {"ORA_HOME": "", "ORA_VAULT": ""}), \
                patch("builtins.__import__", self.guard_import):
            code, out, err = self.run_main()
            self.assertEqual((code, out), (2, ""))
            self.assertIn("no live-default fallback", err)
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
            {"s1": "PASS — output a greeting"},
            {"s1": "PASS — output “warning”"},
            {"s1": "PASS — strong analytical signal; output a greeting"},
            {"s1": "PASS — lookup a historical event"},
            {"s1": "PASS — query a probability"},
            {"s1": "PASS — file a query"},
            {"s1": "PASS — steelman a framework"},
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
        self.source(valid
                    + self.item(2, s1="PASS — red-team strong T15 signal")
                    + self.item(3, s1="PASS — “red-team” strong T15 signal")
                    + self.item(4, s1="BYPASS — greeting; no analytical signal.",
                                s2="N/A (filter blocked)", s3="N/A")
                    + self.item(5, s1="BYPASS — simple factual lookup.",
                                s2="N/A", s3="N/A"))
        with patch("builtins.__import__", self.guard_import), \
                patch.object(self.oracle, "evaluate_case") as evaluate, \
                patch.object(self.oracle, "aggregate") as aggregate, \
                patch.object(self.oracle, "write_report") as report:
            code, out, err = self.run_main(("--validate-only",))
            self.assertEqual((code, err), (0, ""))
            self.assertIn("Corpus admitted: 5 cases", out)
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
        named_fields = (
            ("and", ("and",)),
            ("and and artifact", ("and", "artifact")),
            ("artifact and and", ("artifact", "and")),
            ("first_field + and, second_field", ("first_field", "and", "second_field")),
            ('"and", first_field AND \'last_field\'', ("and", "first_field", "last_field")),
            ("first_field and `and` + second_field", ("first_field", "and", "second_field")),
        )
        for listing, required in named_fields:
            case = self.admitted(s3=f"missing-input={listing}")
            for absent in (None, *required):
                with self.subTest(listing=listing, absent=absent):
                    actual = self.routing(complete=False, missing=tuple(field for field in required if field != absent))
                    result = self.oracle.evaluate_case(case, Mock(return_value=actual))
                    self.assertIs(result["s3_pass"], absent is None)
        for listing in ("and artifact", "first_field and", "first_field + AND", "first_field + + second_field"):
            with self.subTest(unsupported_listing=listing):
                self.source(self.item(s3=f"missing-input={listing}"))
                self.assert_refused_without_effects("UNSUPPORTED MEASUREMENT", 1)
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
                self.assertIn(f"s{stage}", result["cascade_non_execution"])
        blocked = self.oracle.evaluate_case(case, Mock(return_value=self.routing(pause="stage2")))
        self.assertEqual(blocked["cascade_non_execution"], ["s3"])
        self.assertEqual(self.oracle.aggregate([blocked])["overall"]["s3"], {
            "accuracy": 0.0, "denominator": 1, "not_applicable": 0, "cascade_non_execution": 1})
        bypass_case = self.admitted(s1="BYPASS", s2="N/A", s3="N/A")
        unexpected_execution = self.oracle.evaluate_case(bypass_case, Mock(return_value=self.routing()))
        self.assertIs(unexpected_execution["s3_pass"], False)
        self.assertEqual(self.oracle.aggregate([blocked, unexpected_execution])["overall"]["s3"], {
            "accuracy": 0.0, "denominator": 1, "not_applicable": 1, "cascade_non_execution": 1})

        # Semantic alternatives are conjunctive: an arbitrary pause, or one
        # missing an offered branch, cannot pass the named question.
        question = {"kind": "question", "id": "T1.Q1",
                    "alternatives": [["internal logic", "soundness"], ["frame"], ["both"]]}
        conditional = {"kind": "after_dispatch", "requirement": {"kind": "missing", "fields": ["artifact"]}}
        for actual, expected in ((self.routing(pause="stage2"), None),
                                 (self.routing(complete=False, missing=["artifact"]), True),
                                 (self.routing(complete=True), False)):
            self.assertIs(self.oracle.compare_requirement("s3", conditional, actual)[0], expected)
        na = {"kind": "not_applicable", "reason": "Awaiting disambiguation answer"}
        case = self.structured(s2=question, s3=na)
        for text, correct in (("Which way?", False), ("Check the internal logic or frame?", False),
                              ("Check soundness, the frame, or both?", True)):
            actual = self.routing(pause="stage2")
            actual["pending_clarification"] = text
            result = self.oracle.evaluate_case(case, Mock(return_value=actual))
            self.assertIs(result["s2_pass"], correct)

        # Real answers/context are forwarded. Every required continuation is
        # graded, even when the initial question was wrong or never happened.
        answer = {"disambiguation_answer": "internal logic", "s1": {"kind": "pass"},
                  "s2": {"kind": "dispatch", "targets": ["example-mode"]},
                  "s3": {"kind": "missing", "fields": ["artifact"]}}
        supplied = {"completeness_answer": "The canal serves Cedar village, carrying drinking water uphill.",
                    "s1": {"kind": "pass"}, "s2": answer["s2"], "s3": {"kind": "complete"}}
        case = self.structured(s2=question, s3=na, fixture={"context": {"history": [{"role": "user", "content": "Earlier cedar-canal article"}]}},
                               variants=[{"name": "answer then supply", "turns": [answer, supplied]}])
        first = self.routing(pause="stage2")
        first["pending_clarification"] = "Internal logic, frame, or both?"
        pipeline = Mock(side_effect=[first, self.routing(complete=False, missing=["artifact"]), self.routing()])
        result = self.oracle.evaluate_case(case, pipeline)
        self.assertTrue(all(result[f"s{n}_pass"] for n in (1, 2, 3)))
        self.assertEqual(pipeline.call_count, 3)
        self.assertEqual(pipeline.call_args.kwargs["disambiguation_answer"], "internal logic")
        self.assertEqual(pipeline.call_args.kwargs["completeness_answer"], supplied["completeness_answer"])
        self.assertEqual(pipeline.call_args.kwargs["context"], case["fixture"]["context"])
        self.assertEqual(self.oracle.aggregate([result])["overall"]["s3"]["denominator"], 1)
        failing = self.oracle.evaluate_case(case, Mock(return_value=self.routing(bypass=True)))
        self.assertFalse(failing["s3_pass"])
        self.assertEqual(self.oracle.aggregate([failing])["overall"]["s3"]["denominator"], 1)

        # An already-answered original prompt and a separate named question
        # branch both run. An absent question cannot be rescued by its answer.
        branch_answer = {**answer, "after_question": True}
        case = self.structured(s3={"kind": "missing", "fields": ["artifact"]}, variants=[
            {"name": "direct", "turns": []},
            {"name": "question branch", "question_prompt": "Please help examine this claim.",
             "s2": question, "s3": na, "turns": [branch_answer]}])
        pipeline = Mock(side_effect=[self.routing(complete=False, missing=["artifact"]), first,
                                    self.routing(complete=False, missing=["artifact"])])
        result = self.oracle.evaluate_case(case, pipeline)
        self.assertTrue(result["s2_pass"])
        self.assertEqual([call.args[0] for call in pipeline.call_args_list],
                         ["Synthetic task", "Please help examine this claim.", "Please help examine this claim."])
        pipeline = Mock(return_value=self.routing(complete=False, missing=["artifact"]))
        result = self.oracle.evaluate_case(case, pipeline)
        self.assertEqual(pipeline.call_count, 2)
        self.assertFalse(result["s2_pass"])
        self.assertFalse(result["s3_pass"])
        self.assertEqual(result["checkpoints"][-1]["cascade_non_execution"], ["s1", "s2", "s3"])
        self.assertEqual(result["cascade_non_execution"], ["s1", "s2", "s3"])

        # A required plural sequence is compared with production's list, not
        # manufactured by running the expected modes independently.
        for directory in self.modes:
            (directory / "second-mode.md").write_text("# Synthetic second mode\n", encoding="utf-8")
        case = self.structured(s2={"kind": "dispatch", "targets": ["example-mode", "second-mode"], "ordered": True})
        for selected, correct in ((["example-mode"], False), (["second-mode", "example-mode"], False),
                                  (["example-mode", "second-mode"], True)):
            actual = self.routing()
            actual["dispatched_mode_ids"] = selected
            pipeline = Mock(return_value=actual)
            self.assertIs(self.oracle.evaluate_case(case, pipeline)["s2_pass"], correct)
            pipeline.assert_called_once()

        distinctive = "The cedar-canal article says the village operates three blue water gates."
        case = self.structured(s3={"kind": "complete", "validated": {
            "artifact": {"source": "prior_conversation", "value": distinctive}}})
        for validated, correct in (("present (detected from prompt or context)", False),
                                   ({"source": "prompt", "value": distinctive}, False),
                                   ({"source": "prior_conversation", "value": "wrong article"}, False),
                                   ({"source": "prior_conversation", "value": distinctive}, True)):
            actual = self.routing()
            actual["stage3_output"]["validated_inputs"] = {"artifact": validated}
            self.assertIs(self.oracle.evaluate_case(case, Mock(return_value=actual))["s3_pass"], correct)

        # The injected false bypass gets no classification credit, and the
        # unexecuted recovery stages remain denominator failures.
        fault = {"kind": "injected", "reason": "Injected erroneous bypass"}
        case = self.structured(s1=fault, s2=question, s3=na, fixture={"fault": "bypass"},
                               variants=[{"name": "recovery", "turns": [{
                                   "after_question": True, "disambiguation_answer": "Check the internal logic.",
                                   "s1": fault, "s2": {"kind": "dispatch", "targets": ["example-mode"]},
                                   "s3": {"kind": "complete"}}]}])
        with patch.object(self.oracle, "ManualObservation") as observation:
            injected = self.routing(bypass=True)
            injected["manual_handoff_mode"] = "simple"
            observation.return_value.run.return_value = injected
            result = self.oracle.evaluate_case(case, Mock(side_effect=AssertionError("fault must use server boundary")))
            observation.return_value.run.assert_called_once()
        aggregate = self.oracle.aggregate([result])["overall"]
        self.assertEqual(aggregate["s1"]["denominator"], 0)
        self.assertEqual(aggregate["s2"]["accuracy"], 0)
        self.assertEqual(aggregate["s3"]["accuracy"], 0)
        self.assertEqual(aggregate["s3"]["cascade_non_execution"], 1)
        self.assertEqual(result["checkpoints"][0]["cascade_non_execution"], ["s2"])
        self.assertEqual(result["checkpoints"][1]["cascade_non_execution"], ["s2", "s3"])
        asked = self.routing(pause="stage2")
        asked["pending_clarification"] = "Check soundness, the frame, or both?"
        with patch.object(self.oracle, "ManualObservation") as observation:
            observation.return_value.run.side_effect = [asked, self.routing()]
            result = self.oracle.evaluate_case(case, Mock(side_effect=AssertionError("must use actual server boundary")))
            self.assertEqual(observation.return_value.run.call_args_list[-1].args, ("Check the internal logic.",))
        self.assertTrue(result["s2_pass"])
        self.assertTrue(result["s3_pass"])

        # An actual saved analytical pick can prove dispatch preservation at
        # handoff, but cannot stand in for a required Stage 2 question.
        resumed = self.routing()
        resumed["stage2_output"] = None
        resumed["manual_handoff_mode"] = "example-mode"
        self.assertEqual(self.oracle.compare_requirement(
            "s2", {"kind": "dispatch", "targets": ["example-mode"]}, resumed), (True, False))
        self.assertEqual(self.oracle.compare_requirement("s2", question, resumed), (False, True))

        # Offers must be visible choices, with every named option, rather than
        # a nonempty pause or an internal sibling marker alone.
        requirement = {"kind": "missing", "fields": ["artifact"],
                       "offer_targets": ["second-mode"], "heavier": "example-mode",
                       "offer_names": {"second-mode": ["second mode", "lighter review"],
                                       "example-mode": ["example mode", "full review"]}}
        case = self.structured(s3=requirement)
        actual = self.routing(complete=False, missing=["artifact"])
        actual["stage3_output"]["lighter_sibling_mode_id"] = "second-mode"
        self.assertFalse(self.oracle.evaluate_case(case, Mock(return_value=actual))["s3_pass"])
        actual["stage3_output"]["graceful_degradation_offer"] = "Choose second mode or provide the artifact for example mode."
        self.assertTrue(self.oracle.evaluate_case(case, Mock(return_value=actual))["s3_pass"])
        for text, correct in (("Choose lighter review or provide the artifact for full review.", True),
                              ("Choose lighter review or provide the artifact for another method.", False)):
            actual["stage3_output"]["graceful_degradation_offer"] = text
            self.assertIs(self.oracle.evaluate_case(case, Mock(return_value=actual))["s3_pass"], correct)
        for stage, requirement, offer_key in (
            ("s2", {"kind": "question", "id": "methods", "alternatives": [["choose", "another"]],
                    "offer_targets": ["example-mode", "second-mode"]}, "pending_clarification"),
            ("s3", {"kind": "missing", "fields": ["artifact"],
                    "offer_targets": ["example-mode", "second-mode"]}, "graceful_degradation_offer"),
            ("s3", {"kind": "deferred_offer", "offer_targets": ["example-mode", "second-mode"]}, "deferred_offer"),
        ):
            requirement["offer_names"] = {"example-mode": ["example mode", "primary review"],
                                          "second-mode": ["second mode", "secondary review"]}
            for hidden in (
                {"offered_mode_ids": ["example-mode", "second-mode"]},
                {"lighter_sibling_mode_ids": ["example-mode", "second-mode"]},
                {"lighter_sibling_mode_id": "second-mode"},
                {},
            ):
                for text, expected in (("Would you like another method?", False),
                                       ("Choose example mode or another method.", False),
                                       ("Choose example mode or second mode.", True),
                                       ("Choose primary review or secondary review.", True)):
                    with self.subTest(offer_stage=stage, hidden=hidden, visible=text):
                        actual = self.routing(complete=False, missing=["artifact"], pause="stage2" if stage == "s2" else "stage3")
                        actual[f"stage{stage[-1]}_output"].update(hidden)
                        container = actual if stage == "s2" else actual["stage3_output"]
                        container[offer_key] = text
                        self.assertEqual(self.oracle.compare_requirement(stage, requirement, actual), (expected, False))

        # The offered order and depth are visible in the words themselves;
        # there need not be a hidden offered-mode list in Stage 2.
        ordered = {"kind": "question", "id": "sequence or balanced",
                   "alternatives": [["steelman", "strongest case"], ["red team", "adversarial"], ["balanced"]],
                   "offer_sequence": [["steelman", "strongest case"], ["red team", "adversarial"]]}
        case = self.structured(s2=ordered, s3=na)
        for text, correct in (
            ("Should I steelman first, then red-team, or give a balanced critique?", True),
            ("Should I give the strongest case first, then an adversarial review, or a balanced critique?", True),
            ("Should I red-team first, then steelman, or give a balanced critique?", False),
            ("Should I steelman after red-team, or give a balanced critique?", False),
            ("Should I steelman first, then red-team?", False),
        ):
            with self.subTest(ordered_offer=text):
                actual = self.routing(pause="stage2")
                actual["pending_clarification"] = text
                self.assertIs(self.oracle.evaluate_case(case, Mock(return_value=actual))["s2_pass"], correct)
        depth = {"kind": "missing", "fields": ["artifact"],
                 "offer_targets": ["example-mode", "second-mode"],
                 "offer_names": {"example-mode": ["example mode", "primary review"],
                                 "second-mode": ["second mode", "secondary review"]},
                 "offer_tiers": {"example-mode": 2, "second-mode": 1}}
        case = self.structured(s3=depth)
        for text, correct in (
            ("Choose example mode at Tier 2 or second mode at Tier 1.", True),
            ("Choose example mode at Tier 1 or second mode at Tier 2.", False),
            ("Choose example mode or second mode.", False),
            ("Choose primary review at Tier 2 or secondary review at Tier 1.", True),
            ("Choose primary review at Tier 1 or secondary review at Tier 2.", False),
        ):
            with self.subTest(offered_depth=text):
                actual = self.routing(complete=False, missing=["artifact"])
                actual["stage3_output"]["graceful_degradation_offer"] = text
                self.assertIs(self.oracle.evaluate_case(case, Mock(return_value=actual))["s3_pass"], correct)

        shared_input = {"kind": "missing", "fields": ["argument_text"],
                        "offer_targets": ["second-mode"], "heavier": "example-mode",
                        "offer_names": {"second-mode": ["lighter review"], "example-mode": ["full review"]},
                        "offer_tiers": {"second-mode": 2},
                        "offer_inputs": {"example-mode": [["argument text"]], "second-mode": [["argument text"]]}}
        case = self.structured(s3=shared_input)
        offer = "Choose lighter review at Tier 2 or full review."
        for text, correct in (
            (offer + " Both options still need the argument text.", True),
            (offer + " Both choices require the argument text.", True),
            (offer + " Both methods still require the argument text.", True),
            (offer + " Both analyses need the argument text.", True),
            ("Lighter review at Tier 2 needs argument text; full review also requires argument text.", True),
            (offer + " Either choice still requires argument text.", True),
            (offer + " Each method needs argument text.", True),
            (offer + " Both options still need more information.", False),
            ("Choose lighter review at Tier 2 or provide argument text for full review.", False),
            ("Lighter review at Tier 2 does not need argument text; full review does not require argument text.", False),
            ("Lighter review at Tier 2 needs argument text; full review doesn't require argument text.", False),
            (offer + " Both require no argument text.", False),
            (offer + " Both need argument text. Lighter review does not require argument text.", False),
            (offer + " Both need argument text. Argument text is not required for full review.", False),
            (offer + " Both need argument text. Lighter review can proceed without it.", False),
            (offer + " Both need argument text. Full review can run without argument text.", False),
        ):
            with self.subTest(shared_missing_material=text):
                actual = self.routing(complete=False, missing=["argument_text"])
                actual["stage3_output"]["graceful_degradation_offer"] = text
                self.assertIs(self.oracle.evaluate_case(case, Mock(return_value=actual))["s3_pass"], correct)

        # Completeness belongs to the observed selected work. An unbound
        # global result, the wrong mode, or reusing one call cannot pass.
        missing_artifact = {"kind": "missing", "fields": ["artifact"]}
        case = self.structured(s3={"kind": "by_mode", "checks": [
            {"targets": ["example-mode"], "requirement": missing_artifact},
            {"targets": ["second-mode"], "requirement": missing_artifact}]})
        for modes, correct in (([], False), (["example-mode"], False),
                               (["example-mode", "example-mode"], False),
                               (["example-mode", "second-mode"], True)):
            with self.subTest(completeness_modes=modes):
                actual = self.routing(complete=False, missing=["artifact"])
                actual["stage3_observations"] = [
                    {"mode": mode, "result": actual["stage3_output"]} for mode in modes]
                result = self.oracle.evaluate_case(case, Mock(return_value=actual))
                self.assertIs(result["s3_pass"], correct)
                self.assertEqual(result["cascade_non_execution"], [] if correct else ["s3"])
        for second_result, missing_call in ((None, True), ({"inputs_complete": True}, False)):
            actual = self.routing(complete=False, missing=["artifact"])
            actual["stage3_observations"] = [
                {"mode": "example-mode", "result": {"inputs_complete": True}},
                {"mode": "second-mode", "result": second_result},
                {"mode": "unrelated-mode", "result": actual["stage3_output"]},
            ]
            result = self.oracle.evaluate_case(case, Mock(return_value=actual))
            self.assertFalse(result["s3_pass"])
            self.assertEqual(result["cascade_non_execution"], ["s3"] if missing_call else [])
        articles = ["Cedar supports Sunday opening.", "Willow opposes Sunday opening."]
        case = self.structured(s3={"kind": "by_mode", "checks": [
            {"targets": ["example-mode"], "requirement": {"kind": "complete", "validated": {
                "argument_text": {"source": "attachment", "value": article}}}}
            for article in articles]})
        for values, correct in (([], False), ([articles[0]], False),
                                ([articles[0], articles[0]], False), (articles, True)):
            with self.subTest(assigned_articles=values):
                actual = self.routing()
                actual["stage3_observations"] = [{"mode": "example-mode", "result": {
                    "inputs_complete": True, "validated_inputs": {"argument_text": {
                        "source": "attachment", "value": value}}}} for value in values]
                result = self.oracle.evaluate_case(case, Mock(return_value=actual))
                self.assertIs(result["s3_pass"], correct)
                self.assertEqual(result["cascade_non_execution"], ["s3"] if len(values) < 2 else [])

    def test_reports_are_truthful_and_preserved(self):
        # The numeric-run boundary records calls the production pipeline
        # actually makes, including their mode/input links in the report.
        self.structured(s3={"kind": "by_mode", "checks": [{"targets": ["example-mode"],
                        "requirement": {"kind": "missing", "fields": ["artifact"]}}]})
        actual = self.routing(complete=False, missing=["artifact"])
        def routed(*args, **kwargs):
            boot.stage3_input_completeness_check("example-mode", args[0], context=kwargs.get("context"))
            return actual
        with patch.object(boot, "run_pre_routing_pipeline", side_effect=routed), \
                patch.object(boot, "stage3_input_completeness_check", return_value=actual["stage3_output"]) as completeness:
            code, out, err = self.run_main()
        self.assertEqual((code, err), (0, ""))
        completeness.assert_called_once()
        self.assertIn("Stage 3: 100.0%", out)
        report = self.report.read_text(encoding="utf-8")
        self.assertIn('"completeness_by_mode": [{"mode": "example-mode"', report)
        with patch.object(boot, "run_pre_routing_pipeline", return_value=actual):
            code, out, err = self.run_main()
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Stage 3: 0.0%", out)
        self.assertIn("Cascade non-execution (required stage did not run): S3", self.report.read_text(encoding="utf-8"))

        self.structured()
        actual = self.routing()
        actual["stage1_output"] = None
        with patch.object(boot, "run_pre_routing_pipeline", return_value=actual):
            code, out, err = self.run_main()
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Stage 1: 0.0% (measured denominator: 1; not applicable: 0; cascade non-execution: 1)", out)
        self.assertIn('"cascade_non_execution": ["s1"]', self.report.read_text(encoding="utf-8"))

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
                self.assertIn("Stage 4 is unmeasured", report)
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
        self.admitted()
        alternate = self.root / "explicit-report.md"
        with patch.object(boot, "run_pre_routing_pipeline", return_value=self.routing()):
            code, out, err = self.run_main(("--report", str(alternate)))
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Stage 3: 100.0%", alternate.read_text(encoding="utf-8"))
        sentinel = self.report.read_text(encoding="utf-8")
        def unexpected_write(*args, **kwargs):
            (self.root / "unexpected-effect").write_text("must refuse", encoding="utf-8")
            return self.routing()
        with patch.object(boot, "run_pre_routing_pipeline", side_effect=unexpected_write):
            code, out, err = self.run_main()
        self.assertEqual((code, out), (1, ""))
        self.assertIn("Unexpected effect", err)
        self.assertFalse((self.root / "unexpected-effect").exists())
        self.assertEqual(self.report.read_text(encoding="utf-8"), sentinel)


if __name__ == "__main__":
    unittest.main()
