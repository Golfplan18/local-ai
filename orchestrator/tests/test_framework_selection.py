#!/usr/bin/env python3
"""Landing 2 coverage for the shared framework picker execution seam."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "orchestrator"))
sys.path.insert(0, os.path.join(ROOT, "server"))

from boot import list_pickable_frameworks  # noqa: E402
from framework_invocability import resolve_user_invocable_framework  # noqa: E402
from server import app as server  # noqa: E402


PUBLIC_IDS = {row["id"] for row in list_pickable_frameworks()}
DEDICATED_ONLY_IDS = {
    "api-key-setup",
    "document-processing",
    "engram-cleaning",
    "news-supersession",
    "periodic-maintenance",
    "video-editing-suggestions",
}


def _event_payloads(chunks):
    return [
        json.loads(chunk[6:])
        for chunk in chunks
        if chunk.startswith("data: ")
    ]


class TestFrameworkSelection(unittest.TestCase):
    def _run_picker(self, framework_id, user_input="selected input", **kwargs):
        turn_state = {
            "trace_dir": None,
            "kind": "unknown",
            "status": None,
            "mode": None,
            "gear": None,
            "parent_ref": None,
        }
        with (
            mock.patch.object(server, "_begin_visual_outcome"),
            mock.patch.object(server, "load_config", return_value={"ok": True}),
            mock.patch.object(
                server, "get_endpoint",
                return_value={"name": "fake", "context_window": 4096},
            ),
            mock.patch.object(server, "_framework_project_nexus", return_value="project-a"),
        ):
            return list(server._pipeline_stream_impl(
                user_input,
                [],
                panel_id="framework-selection-test",
                images=kwargs.pop("images", None),
                extra_context=kwargs.pop("extra_context", None),
                framework_selected=framework_id,
                config_name=kwargs.pop("config_name", "profile-a"),
                conversation_tag="private",
                turn_state=turn_state,
            ))

    def test_picker_endpoint_is_exactly_the_public_row_shape(self):
        response = server.app.test_client().get("/api/frameworks/picker")
        self.assertEqual(response.status_code, 200)
        rows = response.get_json()["frameworks"]
        self.assertEqual({row["id"] for row in rows}, PUBLIC_IDS)
        for row in rows:
            self.assertEqual(
                set(row), {"id", "display_name", "display_description"},
            )

    def test_invalid_picker_id_is_rejected_before_model_work(self):
        called = mock.Mock()
        with mock.patch.object(server, "_begin_visual_outcome"), \
             mock.patch("milestone_executor.run_framework_command", called):
            events = list(server._pipeline_stream_impl(
                "input", [], panel_id="invalid-framework-test",
                framework_selected="api-key-setup",
                turn_state={"kind": "unknown", "status": None},
            ))
        payloads = _event_payloads(events)
        self.assertEqual(payloads[-1]["type"], "error")
        self.assertIn("invalid framework selection", payloads[-1]["text"])
        called.assert_not_called()

    def test_each_retained_picker_row_executes_once_with_context(self):
        images = [{"name": "attached.png", "base64": "AA=="}]
        extra_context = {
            "style_id": "academic",
            "model_profile_project_nexus": "project-a",
            "model_profile_locks": {"project_nexus": "project-a"},
            "image_path": "/tmp/canvas.png",
            "spatial_representation": {"objects": []},
            "visual_checkpoint_id": "checkpoint-1",
        }
        with mock.patch(
            "milestone_executor.run_framework_command",
            return_value="framework result",
        ) as run:
            for framework_id in sorted(PUBLIC_IDS):
                with self.subTest(framework_id=framework_id):
                    run.reset_mock()
                    events = self._run_picker(
                        framework_id, user_input="answer with setup context",
                        images=images, extra_context=extra_context,
                    )
                    run.assert_called_once()
                    command = run.call_args.args[0]
                    internal_id = os.path.splitext(
                        resolve_user_invocable_framework(framework_id)
                    )[0]
                    self.assertEqual(
                        command,
                        f"/framework {internal_id} answer with setup context",
                    )
                    kwargs = run.call_args.kwargs
                    self.assertEqual(kwargs["project_nexus"], "project-a")
                    self.assertEqual(kwargs["one_run_profile"], "profile-a")
                    self.assertEqual(kwargs["conversation_tag"], "private")
                    self.assertEqual(kwargs["images"], images)
                    self.assertIs(kwargs["input_context"], kwargs["style_context"])
                    self.assertEqual(
                        kwargs["input_context"]["visual_checkpoint_id"],
                        "checkpoint-1",
                    )
                    self.assertEqual(
                        _event_payloads(events)[-1]["text"], "framework result",
                    )

    def test_picker_result_uses_typed_visual_hook_and_outcome_copy(self):
        def hook(text, context):
            context["_visual_outcome"] = {
                "state": "published",
                "origin": "picker-test",
            }
            return f"hooked: {text}"

        with (
            mock.patch(
                "milestone_executor.run_framework_command",
                return_value="framework result",
            ),
            mock.patch("boot._run_visual_hook", side_effect=hook) as visual_hook,
            mock.patch.object(
                server,
                "_copy_visual_outcome_context",
                wraps=server._copy_visual_outcome_context,
            ) as copy_outcome,
        ):
            events = self._run_picker("terrain-mapping")

        visual_hook.assert_called_once()
        self.assertEqual(visual_hook.call_args.args[0], "framework result")
        self.assertEqual(
            visual_hook.call_args.args[1]["cleaned_prompt"],
            "/framework terrain-mapping selected input",
        )
        copy_outcome.assert_called_once()
        self.assertEqual(
            copy_outcome.call_args.args[0]["_visual_outcome"]["state"],
            "published",
        )
        self.assertEqual(_event_payloads(events)[-1]["text"], "hooked: framework result")

    def test_picker_one_shot_records_risk_route_with_shared_turn_context(self):
        with (
            mock.patch("risk_gate.now_ts", return_value="picker-turn-ts"),
            mock.patch(
                "risk_gate.assign_tier",
                return_value={"risk_tier": "high-risk"},
            ),
            mock.patch("risk_gate.evaluate_hold", return_value=(None, "fp")),
            mock.patch("risk_gate.record_route_observed") as record_route,
            mock.patch("tool_events.set_turn_context") as set_turn_context,
            mock.patch(
                "milestone_executor.run_framework_command",
                return_value="picker result",
            ),
        ):
            events = self._run_picker("terrain-mapping")

        set_turn_context.assert_called_once_with(
            conversation_id="framework-selection-test",
            surface="chat",
            stealth=False,
            risk_tier="high-risk",
        )
        record_route.assert_called_once_with(
            ("framework-selection-test", "picker-turn-ts"),
            risk_tier="high-risk",
            output_text="picker result",
        )
        self.assertEqual(_event_payloads(events)[-1]["text"], "picker result")

        with (
            mock.patch("risk_gate.now_ts", return_value="failed-picker-ts"),
            mock.patch(
                "risk_gate.assign_tier",
                return_value={"risk_tier": "high-risk"},
            ),
            mock.patch("risk_gate.evaluate_hold", return_value=(None, "fp")),
            mock.patch("risk_gate.record_route_observed") as record_route,
            mock.patch("tool_events.set_turn_context"),
            mock.patch(
                "milestone_executor.run_framework_command",
                side_effect=RuntimeError("picker failed"),
            ),
        ):
            events = self._run_picker("terrain-mapping")

        record_route.assert_called_once_with(
            ("framework-selection-test", "failed-picker-ts"),
            risk_tier="high-risk",
        )
        self.assertEqual(_event_payloads(events)[-1]["type"], "error")

    def test_setup_answers_are_sent_as_one_executor_input(self):
        with mock.patch(
            "milestone_executor.run_framework_command",
            return_value="done",
        ) as run:
            self._run_picker(
                "terrain-mapping",
                user_input=(
                    "research the problem\n\n"
                    "[Response to: Current problem space]\n"
                    "The city budget is the problem."
                ),
            )
        self.assertEqual(run.call_count, 1)
        self.assertIn(
            "The city budget is the problem.", run.call_args.args[0],
        )

    def test_empty_picker_input_uses_guided_elicitation_once(self):
        with (
            mock.patch(
                "framework_elicitation.start_elicitation",
                return_value="question",
            ) as start,
            mock.patch(
                "milestone_executor.run_framework_command",
                side_effect=AssertionError("empty picker input must elicit"),
            ),
        ):
            events = self._run_picker(
                "terrain-mapping", user_input="",
                extra_context={"visual_checkpoint_id": "checkpoint-1"},
            )
        start.assert_called_once()
        self.assertEqual(start.call_args.args[0], "terrain-mapping")
        self.assertEqual(start.call_args.kwargs["input_context"]["visual_checkpoint_id"], "checkpoint-1")
        self.assertEqual(_event_payloads(events)[-1]["text"], "question")

    def test_multipart_empty_picker_submission_reaches_guided_branch(self):
        client = server.app.test_client()
        with (
            mock.patch.object(server, "_log_pending_submission", return_value="submission-1"),
            mock.patch.object(
                server,
                "_invoke_pipeline",
                return_value=(json.dumps({"status": "ok"}), 200),
            ) as invoke,
        ):
            response = client.post(
                "/chat/multipart",
                data={
                    "message": "",
                    "conversation_id": "empty-picker-test",
                    "panel_id": "empty-picker-test",
                    "framework_selected": "deep-research",
                },
            )

        self.assertEqual(response.status_code, 200)
        invoke.assert_called_once()
        self.assertEqual(
            invoke.call_args.kwargs["framework_selected"],
            "deep-research-protocol",
        )

        ordinary_empty = client.post(
            "/chat/multipart",
            data={
                "message": "",
                "conversation_id": "ordinary-empty-test",
                "panel_id": "ordinary-empty-test",
            },
        )
        self.assertEqual(ordinary_empty.status_code, 400)

    def test_picker_visual_outcome_reaches_existing_save_boundary(self):
        context = {"style_id": "academic"}

        def hook(text, hook_context):
            hook_context["_visual_outcome"] = {
                "state": "ready",
                "origin": "picker-save-test",
            }
            return f"hooked: {text}"

        from orchestrator import conversation_memory

        with tempfile.TemporaryDirectory() as temp_root:
            with (
                mock.patch.object(
                    conversation_memory,
                    "_DEFAULT_SESSIONS_ROOT",
                    Path(temp_root),
                ),
                mock.patch.object(server, "_begin_visual_outcome"),
                mock.patch.object(server, "load_config", return_value={"ok": True}),
                mock.patch.object(
                    server, "get_endpoint",
                    return_value={"name": "fake", "context_window": 4096},
                ),
                mock.patch("boot.PIPELINE_TRACE_AVAILABLE", False),
                mock.patch(
                    "milestone_executor.run_framework_command",
                    return_value="framework result",
                ),
                mock.patch("boot._run_visual_hook", side_effect=hook),
                mock.patch.object(server, "_save_conversation", return_value="chunk-1"),
                mock.patch.object(
                    server,
                    "_persist_turn_spatial_state_unlocked",
                    wraps=server._persist_turn_spatial_state_unlocked,
                ) as persist,
            ):
                reply = server._invoke_pipeline_unlocked(
                    "selected input", [], "picker-save-test", True,
                    extra_context=context,
                    framework_selected="terrain-mapping",
                    tag="private",
                    config_name="profile-a",
                )

            envelope = json.loads(
                (Path(temp_root) / "picker-save-test" / "conversation.json").read_text()
            )

        self.assertEqual(json.loads(reply)["status"], "ok")
        persist.assert_called_once()
        self.assertIs(persist.call_args.args[3], context)
        self.assertEqual(
            envelope["messages"][-1]["visual_outcome"]["origin"],
            "picker-save-test",
        )

    def test_dedicated_only_frameworks_stay_unavailable_to_generic_invocation(self):
        for framework_id in DEDICATED_ONLY_IDS:
            with self.subTest(framework_id=framework_id):
                with self.assertRaises(ValueError):
                    server._resolve_selected_framework(framework_id)


if __name__ == "__main__":
    unittest.main()
