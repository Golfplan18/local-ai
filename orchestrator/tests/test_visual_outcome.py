"""Durable assistant-message visual outcomes."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from orchestrator import conversation_memory as memory

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boot  # noqa: E402


class VisualOutcomePersistenceTests(unittest.TestCase):
    def test_bypass_context_carries_terminal_outcome_to_persistence(self):
        from server import app as server_app

        source = {
            "_visual_outcome": {
                "state": "failed", "stage": "dispatch", "reason": "pane unavailable",
            },
            "_visual_fallback_origin": "normal_fallback",
        }
        target = {}
        server_app._copy_visual_outcome_context(source, target)
        self.assertEqual(target["_visual_outcome"]["state"], "failed")
        self.assertEqual(target["_visual_fallback_origin"], "normal_fallback")

    def test_building_placeholder_is_completed_in_place(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            memory.begin_visual_outcome("visual-outcome", "Explain the dependency", sessions_root=root)
            first = memory.load_conversation_json("visual-outcome", sessions_root=root)
            self.assertEqual(len(first["messages"]), 2)
            self.assertEqual(first["messages"][-1]["visual_outcome"]["state"], "building")
            memory.save_turn_spatial_state(
                "visual-outcome", "Explain the dependency",
                "The service depends on the database.",
                visual_outcome={"state": "ready"}, sessions_root=root,
            )
            second = memory.load_conversation_json("visual-outcome", sessions_root=root)
            self.assertEqual(len(second["messages"]), 2)
            self.assertEqual(second["messages"][-1]["content"], "The service depends on the database.")
            self.assertEqual(second["messages"][-1]["visual_outcome"]["state"], "ready")

    def test_outcome_update_does_not_add_a_message(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            memory.begin_visual_outcome("visual-outcome-2", "Compare the options", sessions_root=root)
            path = memory.set_assistant_visual_outcome(
                "visual-outcome-2",
                {"state": "failed", "stage": "dispatch", "reason": "editor unavailable"},
                assistant_index=0, sessions_root=root,
            )
            self.assertIsNotNone(path)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(data["messages"]), 2)
            self.assertEqual(data["messages"][-1]["visual_outcome"]["state"], "failed")
            self.assertEqual(data["messages"][-1]["visual_outcome"]["stage"], "dispatch")

    def test_noninteractive_result_is_headlessly_rendered_and_persisted(self):
        example = Path(os.environ.get("ORA_HOME", os.path.expanduser("~/ora"))) \
            / "config/visual-schemas/examples/concept_map.valid.json"
        envelope = json.loads(example.read_text(encoding="utf-8"))
        response = (
            "The service depends on the database.\n\n"
            "```ora-visual\n" + json.dumps(envelope) + "\n```"
        )
        with tempfile.TemporaryDirectory() as temp:
            context = {
                "mode_name": "synthesis",
                "execution_context": "agent",
                "trace_dir": temp,
            }
            with mock.patch.object(
                boot, "_render_visual_svg_cli", return_value=("<svg/>", None)
            ) as render:
                result = boot._run_visual_hook(response, context)
            self.assertNotIn("ora-visual", result)
            self.assertEqual(context["_visual_outcome"]["state"], "ready")
            self.assertEqual(render.call_count, 1)
            self.assertTrue((Path(temp) / "visual-artifact.svg").exists())
            self.assertTrue((Path(temp) / "visual-artifact.json").exists())

    def test_noninteractive_result_without_trace_fails_loudly(self):
        example = Path(os.environ.get("ORA_HOME", os.path.expanduser("~/ora"))) \
            / "config/visual-schemas/examples/concept_map.valid.json"
        envelope = json.loads(example.read_text(encoding="utf-8"))
        response = "```ora-visual\n" + json.dumps(envelope) + "\n```"
        context = {"mode_name": "synthesis", "execution_context": "agent"}
        with mock.patch.object(
            boot, "_render_visual_svg_cli", return_value=("<svg/>", None)
        ):
            boot._run_visual_hook(response, context)
        self.assertEqual(context["_visual_outcome"]["state"], "failed")
        self.assertEqual(context["_visual_outcome"]["stage"], "cli_render")
