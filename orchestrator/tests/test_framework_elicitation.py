"""Tests for the framework elicitation handler (orchestrator/framework_elicitation.py).

Covers:
  - Marker detection (positive + negative + multiple turns + non-assistant)
  - Marker placement on emitted messages
  - Summarizer response parsing (ELICITED / PENDING / ACTION / QUESTION)
  - Single-turn elicitation start (no query → first question + marker)
  - Multi-turn elicitation flow with mocked summarizer (3 turns → final deliverable)
  - Mechanical-mode redirect when an elicitation start lands on C-Instance
  - parse_framework_command's relaxed behavior (empty query allowed)
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = os.path.dirname(HERE)
if ORCH not in sys.path:
    sys.path.insert(0, ORCH)

import framework_elicitation  # noqa: E402
from framework_elicitation import (  # noqa: E402
    ContinuationContext,
    MARKER_PATTERN,
    MARKER_TEMPLATE,
    _parse_summary_response,
    _SummaryState,
    is_continuation,
)


# ---------- Marker detection ----------

class TestIsContinuation(unittest.TestCase):

    def test_no_history(self):
        self.assertIsNone(is_continuation([]))
        self.assertIsNone(is_continuation(None))  # type: ignore

    def test_no_marker_in_last_assistant_message(self):
        history = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello there"},
        ]
        self.assertIsNone(is_continuation(history))

    def test_marker_in_last_assistant_message(self):
        marker = MARKER_TEMPLATE.format(
            framework_id="corpus-formalization", mode="C-Design", state="eliciting"
        )
        history = [
            {"role": "user", "content": "/framework cff"},
            {"role": "assistant", "content": f"What workflow is this for?\n\n{marker}"},
        ]
        ctx = is_continuation(history)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.framework_id, "corpus-formalization")
        self.assertEqual(ctx.mode, "C-Design")
        self.assertEqual(ctx.state, "eliciting")

    def test_marker_only_on_older_assistant_message_does_not_count(self):
        marker = MARKER_TEMPLATE.format(
            framework_id="cff", mode="C-Design", state="eliciting"
        )
        history = [
            {"role": "user", "content": "/framework cff"},
            {"role": "assistant", "content": f"Q1?\n\n{marker}"},
            {"role": "user", "content": "answer"},
            {"role": "assistant", "content": "deliverable text without a marker"},
            {"role": "user", "content": "thanks"},
        ]
        # The most recent assistant message has no marker, so we're NOT mid-framework
        self.assertIsNone(is_continuation(history))

    def test_skips_user_and_system_when_finding_last_assistant(self):
        marker = MARKER_TEMPLATE.format(
            framework_id="problem-evolution", mode="PE-Init", state="eliciting"
        )
        history = [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": f"Q\n\n{marker}"},
            {"role": "user", "content": "u2 — answer"},
        ]
        ctx = is_continuation(history)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.framework_id, "problem-evolution")
        self.assertEqual(ctx.mode, "PE-Init")


class TestMarkerPlacement(unittest.TestCase):

    def test_wrap_appends_marker_on_its_own_line(self):
        wrapped = framework_elicitation._wrap_with_marker(
            "What workflow is this for?", "cff", "C-Design"
        )
        self.assertIn("What workflow is this for?", wrapped)
        self.assertTrue(MARKER_PATTERN.search(wrapped))
        # Marker is at the end (after a blank line)
        self.assertTrue(
            wrapped.rstrip().endswith(
                MARKER_TEMPLATE.format(
                    framework_id="cff", mode="C-Design", state="eliciting"
                )
            )
        )


# ---------- Summarizer response parsing ----------

class TestParseSummaryResponse(unittest.TestCase):

    def test_ask_next_with_full_structure(self):
        response = (
            "ELICITED:\n"
            "- Workflow is monthly board memos\n"
            "- Source PFFs are A and B\n"
            "\n"
            "PENDING:\n"
            "- Cadence (weekly vs monthly?)\n"
            "- Chain relationships\n"
            "\n"
            "ACTION: ASK_NEXT\n"
            "\n"
            "QUESTION: What cadence does this corpus need to be populated on?\n"
        )
        state = _parse_summary_response(response)
        self.assertIsNotNone(state)
        self.assertEqual(len(state.elicited_bullets), 2)
        self.assertEqual(len(state.pending_bullets), 2)
        self.assertEqual(state.action, "ASK_NEXT")
        self.assertIn("cadence", state.next_question.lower())

    def test_produce_deliverable_action(self):
        response = (
            "ELICITED:\n"
            "- everything\n"
            "\n"
            "PENDING:\n"
            "- (none)\n"
            "\n"
            "ACTION: PRODUCE_DELIVERABLE\n"
        )
        state = _parse_summary_response(response)
        self.assertIsNotNone(state)
        self.assertEqual(state.action, "PRODUCE_DELIVERABLE")
        self.assertEqual(len(state.elicited_bullets), 1)
        self.assertEqual(len(state.pending_bullets), 0)

    def test_filters_placeholder_bullets(self):
        response = (
            "ELICITED:\n"
            "- (none yet)\n"
            "\n"
            "PENDING:\n"
            "- workflow description\n"
            "\n"
            "ACTION: ASK_NEXT\n"
            "QUESTION: What workflow is this for?\n"
        )
        state = _parse_summary_response(response)
        self.assertEqual(state.elicited_bullets, [])
        self.assertEqual(len(state.pending_bullets), 1)

    def test_missing_action_returns_none(self):
        response = "ELICITED:\n- something\n\nPENDING:\n- stuff\n"
        state = _parse_summary_response(response)
        self.assertIsNone(state)

    def test_empty_response_returns_none(self):
        self.assertIsNone(_parse_summary_response(""))
        self.assertIsNone(_parse_summary_response(None))


# ---------- Conversation formatting ----------

class TestFormatConversation(unittest.TestCase):

    def test_strips_markers_from_prior_assistant_turns(self):
        marker = MARKER_TEMPLATE.format(
            framework_id="cff", mode="C-Design", state="eliciting"
        )
        history = [
            {"role": "user", "content": "/framework cff"},
            {"role": "assistant", "content": f"Q1?\n\n{marker}"},
            {"role": "user", "content": "answer 1"},
        ]
        text = framework_elicitation._format_conversation(history, "answer 2")
        self.assertNotIn("ora-framework:", text)
        self.assertIn("Q1?", text)
        self.assertIn("answer 1", text)
        self.assertIn("answer 2", text)

    def test_truncates_overlong_turns(self):
        long_content = "x" * 5000
        history = [{"role": "user", "content": long_content}]
        text = framework_elicitation._format_conversation(history, "")
        self.assertLess(len(text), 1700)


# ---------- start_elicitation flow ----------

class TestStartElicitation(unittest.TestCase):

    def test_unknown_framework_returns_error_string(self):
        text = framework_elicitation.start_elicitation(
            "no-such-framework", history=[], config={}
        )
        self.assertIn("not found", text.lower())

    def test_mechanical_mode_returns_redirect_not_marker(self):
        # Force the mode picker to land on C-Instance for CFF
        with mock.patch("milestone_executor.select_mode") as m_select:
            m_select.return_value = ("C-Instance", "test", "")
            text = framework_elicitation.start_elicitation(
                "corpus-formalization", history=[], config={},
                initial_user_message="C-Instance for May 2026",
            )
        self.assertIn("mechanical", text.lower())
        self.assertIn("/instance", text)
        # No marker — mechanical redirect does not enter elicitation
        self.assertIsNone(MARKER_PATTERN.search(text))

    def test_first_question_carries_marker(self):
        # Mock the summarizer to return a clean ASK_NEXT
        fake_summary = _SummaryState(
            elicited_bullets=[],
            pending_bullets=["workflow description"],
            action="ASK_NEXT",
            next_question="What workflow is this corpus for?",
        )
        with mock.patch.object(
            framework_elicitation, "_ask_summarizer", return_value=fake_summary
        ), mock.patch("milestone_executor.select_mode") as m_select:
            m_select.return_value = ("C-Design", "default", "")
            text = framework_elicitation.start_elicitation(
                "corpus-formalization", history=[], config={},
            )
        self.assertIn("What workflow", text)
        marker_match = MARKER_PATTERN.search(text)
        self.assertIsNotNone(marker_match)
        self.assertEqual(marker_match.group(2), "C-Design")


# ---------- continue_elicitation flow ----------

class TestContinueElicitation(unittest.TestCase):

    def test_ask_next_next_turn_carries_marker(self):
        ctx = ContinuationContext(
            framework_id="corpus-formalization",
            mode="C-Design",
            state="eliciting",
        )
        history = [
            {"role": "user", "content": "/framework cff"},
            {"role": "assistant", "content": "Q1?\n\n<!-- ora-framework: corpus-formalization/C-Design/eliciting -->"},
        ]
        fake_summary = _SummaryState(
            elicited_bullets=["Workflow is board memos"],
            pending_bullets=["Cadence"],
            action="ASK_NEXT",
            next_question="Weekly or monthly cadence?",
        )
        with mock.patch.object(
            framework_elicitation, "_ask_summarizer", return_value=fake_summary
        ):
            text = framework_elicitation.continue_elicitation(
                ctx, history, config={}, latest_user_text="It's for board memos.",
            )
        self.assertIn("Weekly or monthly", text)
        self.assertIn("So far I have", text)
        self.assertIsNotNone(MARKER_PATTERN.search(text))

    def test_produce_deliverable_calls_executor_and_drops_marker(self):
        ctx = ContinuationContext(
            framework_id="corpus-formalization",
            mode="C-Design",
            state="eliciting",
        )
        history = [
            {"role": "user", "content": "/framework cff"},
            {"role": "assistant", "content": "Q1?\n\n<!-- ora-framework: corpus-formalization/C-Design/eliciting -->"},
            {"role": "user", "content": "Board memos"},
            {"role": "assistant", "content": "Q2?\n\n<!-- ora-framework: corpus-formalization/C-Design/eliciting -->"},
        ]
        fake_summary = _SummaryState(
            elicited_bullets=["Workflow: board memos", "Cadence: monthly", "Sources: PFF-A, PFF-B"],
            pending_bullets=[],
            action="PRODUCE_DELIVERABLE",
            next_question="",
        )
        # Mock execute_framework so we don't actually run the gear pipeline
        from milestone_executor import FrameworkExecutionResult
        fake_result = FrameworkExecutionResult(
            framework_name="corpus-formalization",
            execution_id="exec-1",
            user_input="elicited",
            milestones=[],
            final_output="# The Corpus Template\n\nfinal content here",
            success=True,
            duration_seconds=2.0,
            mode="C-Design",
            mode_reasoning="elicitation",
        )
        with mock.patch.object(
            framework_elicitation, "_ask_summarizer", return_value=fake_summary
        ), mock.patch("milestone_executor.execute_framework", return_value=fake_result):
            text = framework_elicitation.continue_elicitation(
                ctx, history, config={}, latest_user_text="That's everything.",
            )
        self.assertIn("final content here", text)
        # Final turn drops the marker — signals back to normal chat
        self.assertIsNone(MARKER_PATTERN.search(text))

    def test_summarizer_failure_falls_back_gracefully_with_marker(self):
        ctx = ContinuationContext(
            framework_id="corpus-formalization",
            mode="C-Design",
            state="eliciting",
        )
        with mock.patch.object(
            framework_elicitation, "_ask_summarizer", return_value=None
        ):
            text = framework_elicitation.continue_elicitation(
                ctx, history=[], config={}, latest_user_text="some answer",
            )
        # Graceful fallback: an open question that asks for context
        self.assertIn("information", text.lower())
        # Marker still present so the next turn re-tries
        self.assertIsNotNone(MARKER_PATTERN.search(text))

    def test_lost_target_mode_returns_clean_error(self):
        ctx = ContinuationContext(
            framework_id="corpus-formalization",
            mode="DoesNotExist",
            state="eliciting",
        )
        text = framework_elicitation.continue_elicitation(
            ctx, history=[], config={}, latest_user_text="hi",
        )
        self.assertIn("no milestones", text.lower())


# ---------- parse_framework_command relaxation ----------

class TestParseFrameworkCommand(unittest.TestCase):

    def test_empty_query_now_allowed(self):
        from milestone_executor import parse_framework_command, framework_command_has_query
        name, query = parse_framework_command("/framework cff")
        self.assertEqual(name, "cff.md")
        self.assertEqual(query, "")
        self.assertFalse(framework_command_has_query("/framework cff"))

    def test_non_empty_query(self):
        from milestone_executor import parse_framework_command, framework_command_has_query
        name, query = parse_framework_command("/framework cff design a template for X")
        self.assertEqual(name, "cff.md")
        self.assertEqual(query, "design a template for X")
        self.assertTrue(framework_command_has_query("/framework cff design a template for X"))

    def test_missing_framework_name_still_errors(self):
        from milestone_executor import parse_framework_command
        with self.assertRaises(ValueError):
            parse_framework_command("/framework ")


if __name__ == "__main__":
    unittest.main()
