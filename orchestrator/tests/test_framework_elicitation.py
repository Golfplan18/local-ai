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

import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
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

    def test_image_payloads_are_absent_and_marker_context_is_bounded(self):
        large_base64 = "A" * (10 * 1024 * 1024)
        marker = framework_elicitation.elicitation_marker(
            "corpus-formalization",
            "C-Design",
            execution_context={
                "style_context": {"privacy": {"mode": "private"}},
                "input_context": {
                    "image_path": "/outside/owned/session.png",
                    "nested": {"base64": large_base64},
                },
                "images": [{"name": "large.png", "base64": large_base64}],
            },
        )

        self.assertNotIn(large_base64, marker)
        self.assertNotIn("base64", marker)
        self.assertNotIn("image_path", marker)
        self.assertLess(len(marker), 20_000)
        ctx = is_continuation([{"role": "assistant", "content": marker}])
        self.assertIsNotNone(ctx)
        self.assertNotIn("images", ctx.execution_context or {})


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

    def test_does_not_apply_a_fixed_character_cap(self):
        long_content = "x" * 5000
        history = [{"role": "user", "content": long_content}]
        text = framework_elicitation._format_conversation(history, "")
        self.assertIn(long_content, text)

    def test_summarizer_packs_long_history_as_whole_units_to_endpoint_capacity(self):
        import boot

        history = []
        for index in range(12):
            history.extend([
                {
                    "role": "user",
                    "content": (
                        f"FW-U{index:02d}-START " + ("u" * 1800)
                        + f" FW-U{index:02d}-END"
                    ),
                    "_ora_history_segment": "local",
                },
                {
                    "role": "assistant",
                    "content": (
                        f"FW-A{index:02d}-START " + ("a" * 1800)
                        + f" FW-A{index:02d}-END"
                    ),
                    "_ora_history_segment": "local",
                },
            ])
        endpoint = {
            "id": "framework-bounded", "type": "api",
            "context_window": 22_000, "max_tokens": 2_000,
            "_disable_truncation_retry": True,
        }
        captured = []

        def summarizer(messages, _endpoint, images=None):
            captured.append(messages)
            return (
                "ELICITED:\n- Current answer recorded\n\n"
                "PENDING:\n- One detail\n\n"
                "ACTION: ASK_NEXT\n\nQUESTION: What detail?\n"
            )

        fw = types.SimpleNamespace(name="Capacity Framework")
        milestone = types.SimpleNamespace(
            endpoint_produced="A complete bounded artifact",
            verification_criterion="Every required field is present",
            output_format="Markdown",
        )
        with (
            mock.patch.object(boot, "get_slot_endpoint", return_value=endpoint),
            mock.patch.object(boot, "get_active_endpoint", return_value=None),
            mock.patch.object(boot, "call_model", side_effect=summarizer),
        ):
            state = framework_elicitation._ask_summarizer(
                fw,
                "C-Design",
                milestone,
                history,
                "FW-LATEST-CURRENT",
                {},
            )

        self.assertIsNotNone(state)
        messages = captured[0]
        rendered = "\n".join(message["content"] for message in messages)
        safe_capacity = (
            endpoint["context_window"]
            - boot._endpoint_output_reserve(
                endpoint, endpoint["context_window"],
            )
            - 128
        )
        self.assertLessEqual(
            boot.estimate_message_tokens(messages, endpoint), safe_capacity,
        )
        self.assertEqual(rendered.count("FW-LATEST-CURRENT"), 1)
        selected = 0
        for index in range(12):
            user_present = f"FW-U{index:02d}-START" in rendered
            assistant_present = f"FW-A{index:02d}-START" in rendered
            self.assertEqual(user_present, assistant_present)
            if user_present:
                selected += 1
                self.assertIn(f"FW-U{index:02d}-END", rendered)
                self.assertIn(f"FW-A{index:02d}-END", rendered)
                self.assertEqual(
                    rendered.count(f"FW-U{index:02d}-START"), 1,
                )
        self.assertGreater(selected, 0)
        self.assertLess(selected, 12)

    def test_current_reply_remains_required_when_history_allowance_is_zero(self):
        import boot

        fw = types.SimpleNamespace(name="Tight Capacity Framework")
        milestone = types.SimpleNamespace(
            endpoint_produced="A complete artifact",
            verification_criterion="All required facts are present",
            output_format="Markdown",
        )
        latest = "FW-TIGHT-CURRENT " + ("answer " * 30)
        endpoint = {
            "id": "framework-tight", "type": "api",
            "max_tokens": 1_000, "_disable_truncation_retry": True,
        }
        required_messages = [
            {"role": "system",
             "content": "You are a careful elicitation summarizer."},
            {"role": "user", "content": framework_elicitation._build_summarizer_prompt(
                fw, "C-Design", milestone, "", latest,
            )},
        ]
        endpoint["context_window"] = (
            boot.estimate_message_tokens(required_messages, endpoint)
            + endpoint["max_tokens"]
            + 128
        )
        captured = []

        with (
            mock.patch.object(boot, "get_slot_endpoint", return_value=endpoint),
            mock.patch.object(boot, "get_active_endpoint", return_value=None),
            mock.patch.object(
                boot,
                "call_model",
                side_effect=lambda messages, _endpoint, images=None: (
                    captured.append(messages)
                    or "ELICITED:\n- Current answer recorded\n\n"
                    "PENDING:\n- One detail\n\nACTION: ASK_NEXT\n\n"
                    "QUESTION: What detail?\n"
                ),
            ),
        ):
            state = framework_elicitation._ask_summarizer(
                fw,
                "C-Design",
                milestone,
                [{"role": "user", "content": "FW-OPTIONAL-OLD-HISTORY"}],
                latest,
                {},
            )

        self.assertIsNotNone(state)
        rendered = "\n".join(message["content"] for message in captured[0])
        self.assertEqual(rendered.count("FW-TIGHT-CURRENT"), 1)
        self.assertNotIn("FW-OPTIONAL-OLD-HISTORY", rendered)
        self.assertLessEqual(
            boot.estimate_message_tokens(captured[0], endpoint),
            endpoint["context_window"] - endpoint["max_tokens"] - 128,
        )


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

    def test_produce_deliverable_preserves_current_turn_style_context(self):
        ctx = ContinuationContext(
            framework_id="corpus-formalization",
            mode="C-Design",
            state="eliciting",
        )
        fake_summary = _SummaryState(
            elicited_bullets=["Workflow: board memos"],
            pending_bullets=[],
            action="PRODUCE_DELIVERABLE",
            next_question="",
        )
        from milestone_executor import FrameworkExecutionResult
        fake_result = FrameworkExecutionResult(
            framework_name="corpus-formalization",
            execution_id="exec-style",
            user_input="elicited",
            milestones=[],
            final_output="styled deliverable",
            success=True,
            mode="C-Design",
            mode_reasoning="elicitation",
        )
        contexts = {
            "slash style": {"style_id": "academic"},
            "slash style off": {"style_id": ""},
            "project interaction style": {"style_id": "conversational"},
            "honne audience resolution": {
                "style_id": "conversational",
                "style_register": "written",
                "style_deltas": {"elaboration": 2},
            },
        }
        for label, style_context in contexts.items():
            with self.subTest(label=label), mock.patch.object(
                framework_elicitation, "_ask_summarizer",
                return_value=fake_summary,
            ), mock.patch(
                "milestone_executor.execute_framework", return_value=fake_result,
            ) as execute:
                text = framework_elicitation.continue_elicitation(
                    ctx, [], config={}, latest_user_text="finish",
                    style_context=style_context,
                )
            self.assertIn("styled deliverable", text)
            self.assertIs(
                execute.call_args.kwargs["style_context"], style_context,
            )

    def test_produce_deliverable_rehydrates_existing_submission_attachment(self):
        first_style = {"style_id": "academic", "conversation_tag": "private"}
        conversation_id = "first-conversation"
        submission_id = "20260823T130000000000Z-abcd1234"
        first_input = {"privacy": {"mode": "private"}}

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            raw_root = temp_root / "raw"
            processed_root = raw_root / "processed"
            processed_root.mkdir(parents=True)
            session_root = temp_root / "sessions" / conversation_id
            upload_root = session_root / "uploads"
            canvas_root = session_root / "canvas"
            upload_root.mkdir(parents=True)
            canvas_root.mkdir(parents=True)
            upload_path = upload_root / "upload.png"
            canvas_path = canvas_root / "checkpoint.preview.png"
            upload_path.write_bytes(b"first-upload")
            canvas_path.write_bytes(b"first-canvas")
            (processed_root / f"{submission_id}.json").write_text(
                json.dumps({
                    "submission_id": submission_id,
                    "conversation_id": conversation_id,
                    "image_path": str(upload_path),
                    "image_mime": "image/png",
                    "canvas_preview_path": str(canvas_path),
                    "visual_checkpoint_id": "checkpoint-first",
                    "spatial_raw": json.dumps({"objects": [{"id": "first"}]}),
                    "annotations_raw": json.dumps([{"kind": "sticky"}]),
                }),
                encoding="utf-8",
            )
            marker = framework_elicitation.elicitation_marker(
                "corpus-formalization", "C-Design", "first-project", "profile-a",
                execution_context={
                    "style_context": first_style,
                    "input_context": {
                        **first_input,
                        "_framework_submission_id": submission_id,
                        "conversation_id": conversation_id,
                        "image_path": "/untrusted/path.png",
                    },
                    "images": [{"name": "large.png", "base64": "A" * 1000000}],
                    "attachment_state": {
                        "submission_id": submission_id,
                        "conversation_id": conversation_id,
                    },
                    "conversation_tag": "private",
                },
            )
            self.assertNotIn("A" * 1000000, marker)
            self.assertLess(len(marker), 20_000)
            ctx = is_continuation([
                {"role": "assistant", "content": "Q1?\n\n" + marker},
            ])
            self.assertIsNotNone(ctx)

            fake_summary = _SummaryState(
                elicited_bullets=["Workflow: board memos"],
                pending_bullets=[],
                action="PRODUCE_DELIVERABLE",
                next_question="",
            )
            from milestone_executor import FrameworkExecutionResult
            fake_result = FrameworkExecutionResult(
                framework_name="corpus-formalization",
                execution_id="exec-context",
                user_input="elicited",
                milestones=[],
                final_output="context-preserved deliverable",
                success=True,
                mode="C-Design",
                mode_reasoning="elicitation",
            )
            with (
                mock.patch.object(
                    framework_elicitation, "_raw_submission_root",
                    return_value=raw_root,
                ),
                mock.patch.object(
                    framework_elicitation, "_session_root_for_conversation",
                    return_value=session_root,
                ),
                mock.patch.object(
                    framework_elicitation, "_ask_summarizer", return_value=fake_summary,
                ),
                mock.patch(
                    "milestone_executor.execute_framework", return_value=fake_result,
                ) as execute,
            ):
                text = framework_elicitation.continue_elicitation(
                    ctx, [], config={}, latest_user_text="finish",
                    conversation_id=conversation_id,
                    current_project_nexus="first-project",
                    style_context={"style_id": "current"},
                    input_context={"visual_checkpoint_id": "current"},
                    images=[{"name": "current.png", "base64": "Y3VycmVudA=="}],
                    conversation_tag="",
                )

        self.assertIn("context-preserved deliverable", text)
        kwargs = execute.call_args.kwargs
        self.assertEqual(kwargs["style_context"], first_style)
        self.assertEqual(kwargs["input_context"]["privacy"], first_input["privacy"])
        self.assertEqual(kwargs["input_context"]["visual_checkpoint_id"], "checkpoint-first")
        self.assertEqual(
            kwargs["input_context"]["spatial_representation"],
            {"objects": [{"id": "first"}]},
        )
        self.assertEqual(kwargs["input_context"]["annotations"], {"annotations": [{"kind": "sticky"}]})
        self.assertEqual(
            [image["base64"] for image in kwargs["images"]],
            ["Zmlyc3QtdXBsb2Fk", "Zmlyc3QtY2FudmFz"],
        )

    def test_unavailable_submission_reference_keeps_non_image_context(self):
        submission_id = "20260823T130000000000Z-deadbeef"
        marker = framework_elicitation.elicitation_marker(
            "corpus-formalization", "C-Design",
            execution_context={
                "style_context": {"style_id": "academic"},
                "input_context": {
                    "privacy": {"mode": "private"},
                    "_framework_submission_id": submission_id,
                },
                "attachment_state": {"submission_id": submission_id},
            },
        )
        ctx = is_continuation([{"role": "assistant", "content": marker}])
        self.assertIsNotNone(ctx)
        fake_summary = _SummaryState(
            elicited_bullets=["Workflow: board memos"],
            pending_bullets=[],
            action="PRODUCE_DELIVERABLE",
            next_question="",
        )
        from milestone_executor import FrameworkExecutionResult
        fake_result = FrameworkExecutionResult(
            framework_name="corpus-formalization",
            execution_id="exec-missing-attachment",
            user_input="elicited",
            milestones=[],
            final_output="non-image context survived",
            success=True,
            mode="C-Design",
            mode_reasoning="elicitation",
        )
        with (
            mock.patch.object(
                framework_elicitation, "_raw_submission_root",
                return_value=Path(tempfile.gettempdir()) / "missing-item10-submissions",
            ),
            mock.patch.object(
                framework_elicitation, "_ask_summarizer", return_value=fake_summary,
            ),
            mock.patch(
                "milestone_executor.execute_framework", return_value=fake_result,
            ) as execute,
        ):
            text = framework_elicitation.continue_elicitation(
                ctx, [], config={}, latest_user_text="finish",
                current_project_nexus=None,
            )
        self.assertIn("non-image context survived", text)
        self.assertEqual(
            execute.call_args.kwargs["input_context"]["privacy"],
            {"mode": "private"},
        )

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
        name, query, config_name = parse_framework_command("/framework cff")
        self.assertEqual(name, "corpus-formalization.md")
        self.assertEqual(query, "")
        self.assertIsNone(config_name)
        self.assertFalse(framework_command_has_query("/framework cff"))

    def test_framework_aliases_resolve_to_canonical_files(self):
        from milestone_executor import parse_framework_command
        cases = {
            "/framework cff": "corpus-formalization.md",
            "/framework pff": "process-formalization.md",
            "/framework off": "output-formalization.md",
        }
        for command, expected_name in cases.items():
            name, query, config_name = parse_framework_command(command)
            self.assertEqual(name, expected_name)
            self.assertEqual(query, "")
            self.assertIsNone(config_name)

    def test_non_empty_query(self):
        from milestone_executor import parse_framework_command, framework_command_has_query
        name, query, config_name = parse_framework_command("/framework cff design a template for X")
        self.assertEqual(name, "corpus-formalization.md")
        self.assertEqual(query, "design a template for X")
        self.assertIsNone(config_name)
        self.assertTrue(framework_command_has_query("/framework cff design a template for X"))

    def test_pff_mode_query_is_preserved(self):
        from milestone_executor import parse_framework_command
        name, query, config_name = parse_framework_command(
            "/framework pff F-Design create a framework for onboarding"
        )
        self.assertEqual(name, "process-formalization.md")
        self.assertEqual(query, "F-Design create a framework for onboarding")
        self.assertIsNone(config_name)

    def test_internal_f_stage_is_rejected(self):
        from milestone_executor import parse_framework_command
        with self.assertRaisesRegex(
            ValueError,
            "internal Gear 4 F-\\* pipeline stage spec",
        ):
            parse_framework_command("/framework f-evaluate check this")

    def test_unregistered_framework_is_rejected(self):
        from milestone_executor import parse_framework_command
        with self.assertRaisesRegex(ValueError, "not registered"):
            parse_framework_command("/framework invented-framework do work")

    def test_pickable_non_milestone_framework_is_not_slash_invocable(self):
        from milestone_executor import parse_framework_command
        with self.assertRaisesRegex(ValueError, "not registered"):
            parse_framework_command("/framework document-processing summarize this")

    def test_missing_framework_name_still_errors(self):
        from milestone_executor import parse_framework_command
        with self.assertRaises(ValueError):
            parse_framework_command("/framework ")

    def test_config_flag_extracted_after_framework_name(self):
        # install Chunk 3: --config <name> flag is position-agnostic in body
        from milestone_executor import parse_framework_command
        name, query, config_name = parse_framework_command(
            "/framework cff --config premium design a template for X"
        )
        self.assertEqual(name, "corpus-formalization.md")
        self.assertEqual(config_name, "premium")
        self.assertEqual(query, "design a template for X")

    def test_config_flag_extracted_at_end(self):
        from milestone_executor import parse_framework_command
        name, query, config_name = parse_framework_command(
            "/framework cff design a template for X --config budget"
        )
        self.assertEqual(name, "corpus-formalization.md")
        self.assertEqual(config_name, "budget")
        self.assertEqual(query, "design a template for X")

    def test_config_flag_without_value_falls_through(self):
        # --config with no value just stays as part of the query
        from milestone_executor import parse_framework_command
        name, query, config_name = parse_framework_command(
            "/framework cff trailing --config"
        )
        self.assertEqual(name, "corpus-formalization.md")
        # No value to consume; --config stays in the query as a literal token
        self.assertIn("--config", query)
        self.assertIsNone(config_name)


if __name__ == "__main__":
    unittest.main()
