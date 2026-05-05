"""Tests for multi-mode framework dispatch (orchestrator/milestone_executor.py).

Covers:
  - select_mode priority: explicit prefix → in-input mention → LLM fallback → default
  - Single-mode frameworks always return ("all", ...).
  - LLM-classifier response parsing: valid mode, out-of-list mode, missing MODE line.
  - execute_framework with a multi-mode framework runs only the selected mode's
    milestones and emits oversight events with the mode tag.
  - format_execution_result surfaces the selected mode.
"""
from __future__ import annotations

import os
import sys
import unittest
from textwrap import dedent
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = os.path.dirname(HERE)
if ORCH not in sys.path:
    sys.path.insert(0, ORCH)

from framework_parser import parse_framework_text  # noqa: E402
from milestone_executor import (  # noqa: E402
    FrameworkExecutionResult,
    MilestoneResult,
    _build_mode_catalog,
    _parse_mode_response,
    format_execution_result,
    select_mode,
)


# A small synthetic multi-mode framework. Uses the same inline-property
# schema the parser expects. Two modes (X-Alpha, X-Beta), each with one
# milestone covering one layer. Includes an M0: Routing block.
SYNTHETIC_MULTIMODE = dedent("""\
    # Synthetic Multi-Mode Framework

    ## LAYER 1: Setup

    Setup body for layer 1.

    ## LAYER 2: Execution

    Execution body for layer 2.

    ## MILESTONES DELIVERED

    ### M0: Routing

    - **Function:** Pick X-Alpha for greenfield work and X-Beta for refinement work.
    - **Layers covered:** 1
    - **Output:** Confirmed mode + brief context.

    ### Milestones for Mode X-Alpha

    #### Milestone 1: Alpha Deliverable

    - **Mode:** X-Alpha
    - **Endpoint produced:** A new alpha artifact.
    - **Verification criterion:** The artifact is a fresh creation.
    - **Layers covered:** 2
    - **Required prior milestones:** None
    - **Gear:** 4
    - **Output format:** Markdown.
    - **Drift check question:** Is the alpha artifact a fresh creation rather than a refinement?

    ### Milestones for Mode X-Beta

    #### Milestone 1: Beta Deliverable

    - **Mode:** X-Beta
    - **Endpoint produced:** A refined beta artifact.
    - **Verification criterion:** The artifact refines an existing one.
    - **Layers covered:** 2
    - **Required prior milestones:** None
    - **Gear:** 4
    - **Output format:** Markdown.
    - **Drift check question:** Does the refined artifact preserve the prior structure?
    """)


SYNTHETIC_SINGLEMODE = dedent("""\
    # Synthetic Single-Mode Framework

    ## LAYER 1: Only

    Only layer.

    ## MILESTONES DELIVERED

    ### Milestone 1: The One Deliverable

    - **Endpoint produced:** A single deliverable.
    - **Verification criterion:** It exists.
    - **Layers covered:** 1
    - **Required prior milestones:** None
    - **Gear:** 4
    - **Output format:** Markdown.
    - **Drift check question:** Is the deliverable on-topic?
    """)


def _build_multimode_fw():
    return parse_framework_text(SYNTHETIC_MULTIMODE, path="synthetic-multimode.md")


def _build_singlemode_fw():
    return parse_framework_text(SYNTHETIC_SINGLEMODE, path="synthetic-singlemode.md")


# ---------- select_mode priority ----------

class TestSelectModePriority(unittest.TestCase):

    def setUp(self):
        self.fw = _build_multimode_fw()
        self.cfg = {}  # empty config disables the LLM fallback path

    def test_explicit_prefix_consumes_token(self):
        mode, reason, eff = select_mode(self.fw, "X-Alpha build me a thing", self.cfg)
        self.assertEqual(mode, "X-Alpha")
        self.assertIn("explicit prefix", reason)
        self.assertEqual(eff, "build me a thing")

    def test_explicit_prefix_case_insensitive(self):
        mode, _, eff = select_mode(self.fw, "x-beta refine the existing", self.cfg)
        self.assertEqual(mode, "X-Beta")
        self.assertEqual(eff, "refine the existing")

    def test_explicit_prefix_with_no_remainder(self):
        mode, _, eff = select_mode(self.fw, "X-Alpha", self.cfg)
        self.assertEqual(mode, "X-Alpha")
        self.assertEqual(eff, "")

    def test_in_input_mention_detected(self):
        mode, reason, eff = select_mode(
            self.fw, "I want to run X-Beta on my draft", self.cfg
        )
        self.assertEqual(mode, "X-Beta")
        self.assertIn("mentioned", reason)
        # Original input preserved when it's an in-input mention
        self.assertEqual(eff, "I want to run X-Beta on my draft")

    def test_no_signal_falls_back_to_first_mode(self):
        # With LLM classifier disabled, the default-to-first branch fires.
        with mock.patch("milestone_executor._llm_select_mode") as m_llm:
            m_llm.return_value = None
            mode, reason, eff = select_mode(
                self.fw, "do something useful for me", self.cfg
            )
            self.assertEqual(mode, "X-Alpha")  # first declared
            self.assertIn("defaulting to first", reason)
            self.assertEqual(eff, "do something useful for me")

    def test_single_mode_framework_returns_all(self):
        sm = _build_singlemode_fw()
        mode, reason, eff = select_mode(sm, "anything", self.cfg)
        self.assertEqual(mode, "all")
        self.assertIn("single-mode", reason)
        self.assertEqual(eff, "anything")

    def test_explicit_prefix_takes_priority_over_in_input_mention(self):
        # X-Alpha is the prefix; X-Beta also appears in the body
        mode, _, eff = select_mode(
            self.fw, "X-Alpha but also mention X-Beta later", self.cfg
        )
        self.assertEqual(mode, "X-Alpha")
        self.assertEqual(eff, "but also mention X-Beta later")


# ---------- LLM fallback path ----------

class TestLLMFallback(unittest.TestCase):

    def setUp(self):
        self.fw = _build_multimode_fw()

    def test_llm_picks_valid_mode(self):
        cfg = {"endpoints": [{"name": "fake"}]}  # non-empty so endpoints lookup runs
        with mock.patch("milestone_executor._llm_select_mode") as m_llm:
            m_llm.return_value = ("X-Beta", "model picked beta because…")
            mode, reason, eff = select_mode(
                self.fw, "ambiguous prompt with no explicit signal", cfg
            )
            self.assertEqual(mode, "X-Beta")
            self.assertIn("model picked beta", reason)

    def test_llm_returns_none_falls_through_to_default(self):
        cfg = {"endpoints": [{"name": "fake"}]}
        with mock.patch("milestone_executor._llm_select_mode") as m_llm:
            m_llm.return_value = None
            mode, reason, _ = select_mode(self.fw, "ambiguous", cfg)
            self.assertEqual(mode, "X-Alpha")  # first declared
            self.assertIn("defaulting", reason)


# ---------- Mode response parsing ----------

class TestParseModeResponse(unittest.TestCase):

    def test_valid_mode_with_reasoning(self):
        valid = ["X-Alpha", "X-Beta"]
        result = _parse_mode_response(
            "MODE: X-Beta\nREASONING: refinement task\n", valid
        )
        self.assertIsNotNone(result)
        mode, reasoning = result
        self.assertEqual(mode, "X-Beta")
        self.assertIn("refinement task", reasoning)

    def test_valid_mode_case_insensitive(self):
        valid = ["X-Alpha", "X-Beta"]
        result = _parse_mode_response("MODE: x-alpha\nREASONING: anything", valid)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "X-Alpha")

    def test_strips_trailing_punctuation(self):
        valid = ["X-Alpha", "X-Beta"]
        result = _parse_mode_response("MODE: X-Alpha.\nREASONING: ok.", valid)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "X-Alpha")

    def test_invalid_mode_returns_none(self):
        valid = ["X-Alpha", "X-Beta"]
        result = _parse_mode_response("MODE: X-Gamma\nREASONING: nope", valid)
        self.assertIsNone(result)

    def test_missing_mode_line_returns_none(self):
        valid = ["X-Alpha", "X-Beta"]
        result = _parse_mode_response("just some prose with no MODE label", valid)
        self.assertIsNone(result)

    def test_missing_reasoning_uses_placeholder(self):
        valid = ["X-Alpha", "X-Beta"]
        result = _parse_mode_response("MODE: X-Alpha\n", valid)
        self.assertIsNotNone(result)
        # Should still return — reasoning falls back to "selected by routing classifier"
        self.assertIn("X-Alpha", result[0])


# ---------- Catalog construction ----------

class TestBuildModeCatalog(unittest.TestCase):

    def test_includes_m0_routing_function(self):
        fw = _build_multimode_fw()
        catalog = _build_mode_catalog(fw)
        self.assertIn("Routing function:", catalog)
        self.assertIn("greenfield", catalog)

    def test_lists_each_mode_with_first_milestone_name(self):
        fw = _build_multimode_fw()
        catalog = _build_mode_catalog(fw)
        self.assertIn("X-Alpha: Alpha Deliverable", catalog)
        self.assertIn("X-Beta: Beta Deliverable", catalog)


# ---------- format_execution_result mode display ----------

class TestFormatExecutionResultMode(unittest.TestCase):

    def _make_result(self, mode="all", mode_reasoning="", success=True):
        return FrameworkExecutionResult(
            framework_name="synthetic",
            execution_id="exec-1",
            user_input="anything",
            milestones=[
                MilestoneResult(
                    milestone_id="M1",
                    name="Demo",
                    deliverable="output content",
                    drift_status="IN_SCOPE",
                    drift_reasoning="",
                    attempts=1,
                ),
            ],
            final_output="output content",
            success=success,
            failure_reason=None if success else "boom",
            duration_seconds=1.5,
            mode=mode,
            mode_reasoning=mode_reasoning,
        )

    def test_single_mode_omits_mode_suffix(self):
        text = format_execution_result(self._make_result(mode="all"))
        self.assertNotIn("/ mode", text)

    def test_multi_mode_includes_mode_suffix(self):
        text = format_execution_result(
            self._make_result(mode="X-Beta", mode_reasoning="user said so")
        )
        self.assertIn("/ mode X-Beta", text)
        self.assertIn("Mode selection: user said so", text)

    def test_failure_includes_mode_suffix(self):
        text = format_execution_result(
            self._make_result(mode="X-Alpha", mode_reasoning="explicit", success=False)
        )
        self.assertIn("/ mode X-Alpha", text)
        self.assertIn("failed", text)


# ---------- End-to-end execute_framework with mocked gear pipeline ----------

class TestExecuteFrameworkMultiMode(unittest.TestCase):

    def setUp(self):
        # Write the synthetic framework to a temp path so parse_framework_file
        # can load it from disk
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="ora-mm-test-")
        self.fw_path = os.path.join(self.tmp, "synthetic-multimode.md")
        with open(self.fw_path, "w") as f:
            f.write(SYNTHETIC_MULTIMODE)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_explicit_prefix_runs_only_selected_mode(self):
        # Mock the gear pipeline — every milestone returns a sentinel deliverable
        with mock.patch("milestone_executor._run_through_gear_pipeline") as m_gear, \
             mock.patch("milestone_executor._run_drift_check") as m_drift:
            m_gear.return_value = "synthetic milestone output"
            m_drift.return_value = ("IN_SCOPE", "ok")

            from milestone_executor import execute_framework
            result = execute_framework(
                self.fw_path,
                "X-Beta refine the artifact",
                config={},
            )
            self.assertTrue(result.success)
            self.assertEqual(result.mode, "X-Beta")
            self.assertIn("explicit prefix", result.mode_reasoning)
            # X-Beta has exactly one milestone — confirm only it ran
            self.assertEqual(len(result.milestones), 1)
            self.assertEqual(result.milestones[0].name, "Beta Deliverable")
            # Effective input had the prefix consumed
            self.assertEqual(result.user_input, "refine the artifact")

    def test_default_falls_back_to_first_mode(self):
        with mock.patch("milestone_executor._run_through_gear_pipeline") as m_gear, \
             mock.patch("milestone_executor._run_drift_check") as m_drift, \
             mock.patch("milestone_executor._llm_select_mode") as m_llm:
            m_gear.return_value = "out"
            m_drift.return_value = ("IN_SCOPE", "ok")
            m_llm.return_value = None  # force the default-to-first branch

            from milestone_executor import execute_framework
            result = execute_framework(
                self.fw_path, "ambiguous request", config={}
            )
            self.assertTrue(result.success)
            self.assertEqual(result.mode, "X-Alpha")  # first declared
            self.assertEqual(len(result.milestones), 1)
            self.assertEqual(result.milestones[0].name, "Alpha Deliverable")

    def test_mechanical_mode_returns_redirect_without_running_gear_pipeline(self):
        # Use a synthetic framework whose first mode is one of the mechanical
        # mode names, so the redirect path triggers regardless of routing.
        mechanical_synthetic = SYNTHETIC_MULTIMODE.replace(
            "X-Alpha", "C-Instance"
        ).replace("X-Beta", "C-Validate")
        path = os.path.join(self.tmp, "mechanical-synthetic.md")
        with open(path, "w") as f:
            f.write(mechanical_synthetic)

        with mock.patch("milestone_executor._run_through_gear_pipeline") as m_gear:
            from milestone_executor import execute_framework
            result = execute_framework(path, "C-Instance run it", config={})

        # Gear pipeline must NOT have been called — mechanical short-circuit
        m_gear.assert_not_called()
        self.assertTrue(result.success)
        self.assertEqual(result.mode, "C-Instance")
        self.assertEqual(result.milestones, [])
        self.assertIn("mechanical", result.final_output.lower())
        self.assertIn("/instance", result.final_output)

    def test_real_cff_parses_with_four_modes(self):
        # Smoke test: the canonical CFF file in ~/ora/frameworks/book/ now
        # parses and declares all four modes
        from framework_parser import parse_framework_file
        fw = parse_framework_file("corpus-formalization.md")
        self.assertTrue(fw.is_multi_mode)
        self.assertEqual(
            sorted(fw.modes),
            sorted(["C-Design", "C-Modify", "C-Instance", "C-Validate"]),
        )

    def test_real_off_parses_with_four_modes(self):
        from framework_parser import parse_framework_file
        fw = parse_framework_file("output-formalization.md")
        self.assertTrue(fw.is_multi_mode)
        self.assertEqual(
            sorted(fw.modes),
            sorted(["O-Design", "O-Modify", "O-Render", "O-Audit"]),
        )

    def test_real_cff_c_instance_redirects(self):
        # End-to-end: invoke real CFF with a C-Instance prefix; expect a
        # redirect message to /instance, with no gear pipeline call.
        from framework_parser import FRAMEWORKS_DIR
        path = os.path.join(FRAMEWORKS_DIR, "corpus-formalization.md")
        with mock.patch("milestone_executor._run_through_gear_pipeline") as m_gear:
            from milestone_executor import execute_framework
            result = execute_framework(
                path, "C-Instance for May 2026", config={}
            )
        m_gear.assert_not_called()
        self.assertEqual(result.mode, "C-Instance")
        self.assertIn("/instance", result.final_output)

    def test_oversight_events_carry_mode(self):
        from oversight_events import register_handler, clear_handlers
        clear_handlers()
        events: list[dict] = []
        register_handler(lambda e: events.append(e))

        with mock.patch("milestone_executor._run_through_gear_pipeline") as m_gear, \
             mock.patch("milestone_executor._run_drift_check") as m_drift:
            m_gear.return_value = "out"
            m_drift.return_value = ("IN_SCOPE", "ok")

            from milestone_executor import execute_framework
            execute_framework(self.fw_path, "X-Alpha go", config={})

        # FrameworkStarted, MilestoneComplete, FrameworkComplete should all
        # carry mode="X-Alpha"
        types_with_mode = [e for e in events if "mode" in e]
        self.assertGreaterEqual(len(types_with_mode), 3)
        for e in types_with_mode:
            self.assertEqual(e["mode"], "X-Alpha")

        clear_handlers()


if __name__ == "__main__":
    unittest.main()
