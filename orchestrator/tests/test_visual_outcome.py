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
    def test_positive_exceptions_skip_visual_recovery_and_synthesis(self):
        explicit = {
            "cleaned_prompt": "Don't analyze this; just answer.",
            "mode_name": "simple",
            "pre_routing": {"visual_exception": "explicit_opt_out"},
        }
        with mock.patch.object(boot, "_maybe_recover_visual") as recover, \
             mock.patch.object(boot, "_maybe_synthesize_visual") as synthesize, \
             mock.patch.object(boot, "_maybe_build_concept_map") as fallback:
            self.assertEqual(boot._run_visual_hook("Short response.", explicit),
                             "Short response.")
            self.assertEqual(explicit["_visual_outcome"]["state"], "not_applicable")
        recover.assert_not_called()
        synthesize.assert_not_called()
        fallback.assert_not_called()

    def test_greeting_prefixed_substantive_reply_keeps_fallback_eligible(self):
        context = {
            "cleaned_prompt": "Hi there, explain the service dependency.",
            "mode_name": "simple",
            "pre_routing": {
                "visual_exception": "greeting_or_acknowledgement",
            },
        }
        visual = "```ora-visual\n{}\n```"
        with mock.patch.object(boot, "_maybe_recover_visual", return_value=(None, None)), \
             mock.patch.object(boot, "_maybe_synthesize_visual", return_value=(None, None)), \
             mock.patch.object(
                 boot, "_maybe_build_concept_map",
                 return_value=("The service depends on the database.\n\n" + visual,
                               {"blocked": False, "type": "concept_map"}),
             ) as fallback:
            result = boot._run_visual_hook("The service depends on the database.", context)
        fallback.assert_called_once()
        self.assertIn("ora-visual", result)
        self.assertEqual(context["_visual_outcome"]["state"], "building")

        no_visual_context = {
            "cleaned_prompt": "Hi there, explain the service dependency.",
            "mode_name": "simple",
            "pre_routing": {
                "visual_exception": "greeting_or_acknowledgement",
            },
        }
        with mock.patch.object(boot, "VISUAL_HOOK_AVAILABLE", True), \
             mock.patch.object(boot, "_maybe_recover_visual", return_value=(None, None)), \
             mock.patch.object(boot, "_maybe_synthesize_visual", return_value=(None, None)), \
             mock.patch.object(boot, "_maybe_build_concept_map", return_value=(None, None)):
            boot._run_visual_hook(
                "The service depends on the database.", no_visual_context,
            )
        self.assertEqual(no_visual_context["_visual_outcome"]["state"], "failed")
        self.assertNotEqual(
            no_visual_context["_visual_outcome"]["reason"],
            boot._VISUAL_NOT_APPLICABLE_REASONS["greeting_or_acknowledgement"],
        )

    def test_standalone_greeting_is_durable_when_visual_hook_is_unavailable(self):
        greeting = {
            "cleaned_prompt": "Hi there!",
            "mode_name": "simple",
            "pre_routing": {
                "visual_exception": "greeting_or_acknowledgement",
            },
        }
        substantive = {
            "cleaned_prompt": "Hi there, explain the service dependency.",
            "mode_name": "simple",
            "pre_routing": {
                "visual_exception": "greeting_or_acknowledgement",
            },
        }
        with mock.patch.object(boot, "VISUAL_HOOK_AVAILABLE", False):
            self.assertEqual(boot._run_visual_hook("Hello!", greeting), "Hello!")
            self.assertEqual(
                boot._run_visual_hook(
                    "The service depends on the database.", substantive,
                ),
                "The service depends on the database.",
            )
        self.assertEqual(greeting["_visual_outcome"]["state"], "not_applicable")
        self.assertNotEqual(
            substantive.get("_visual_outcome", {}).get("reason"),
            boot._VISUAL_NOT_APPLICABLE_REASONS["greeting_or_acknowledgement"],
        )

    def test_lookup_translation_and_analysis_are_not_visual_exceptions(self):
        contexts = [
            {
                "cleaned_prompt": "Translate this paragraph into French.",
                "mode_name": "simple",
                "pre_routing": boot.run_pre_routing_pipeline(
                    "Translate this paragraph into French."
                ),
            },
            {
                "cleaned_prompt": "Explain how the service depends on the database.",
                "mode_name": "causal-dag",
                "pre_routing": {},
            },
        ]
        with mock.patch.object(
            boot, "_maybe_recover_visual", return_value=(None, None)
        ), mock.patch.object(
            boot,
            "_maybe_synthesize_visual",
            return_value=("response with visual", {"blocked": False}),
        ) as synthesize:
            for context in contexts:
                boot._run_visual_hook("Relationship-bearing response.", context)
        self.assertEqual(synthesize.call_count, 2)

    def test_error_and_no_relationship_reasons_are_distinct(self):
        error_context = {
            "cleaned_prompt": "Explain this.",
            "mode_name": "simple",
            "_trace_terminal_status": "error",
        }
        no_relation_context = {
            "cleaned_prompt": "State the isolated fact.",
            "mode_name": "simple",
            "execution_context": "agent",
        }
        boot._run_visual_hook("Endpoint failed.", error_context)
        boot._run_visual_hook("One isolated fact.", no_relation_context)
        self.assertEqual(error_context["_visual_outcome"]["state"],
                         "not_applicable")
        self.assertEqual(no_relation_context["_visual_outcome"]["state"],
                         "not_applicable")
        self.assertNotEqual(error_context["_visual_outcome"]["reason"],
                            no_relation_context["_visual_outcome"]["reason"])

    def test_direct_error_reason_reaches_persistence_context(self):
        from server import app as server_app
        import conversation_memory as server_memory

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            conversation_id = "visual-direct-error"
            context = {}
            endpoint = {"name": "configured", "type": "api"}
            direct_step = {
                "mode": "standard",
                "triage_tier": 1,
                "classification_confidence": "high",
                "detected_invocation": "",
                "pre_routing": {
                    "bypass_to_direct_response": True,
                    "pending_clarification": None,
                    "dispatched_mode_id": None,
                },
            }
            with mock.patch.object(
                memory, "_DEFAULT_SESSIONS_ROOT", root,
            ), mock.patch.object(
                server_memory, "_DEFAULT_SESSIONS_ROOT", root,
            ), mock.patch.object(
                server_app, "load_config", return_value={},
            ), mock.patch.object(
                server_app, "get_endpoint",
                side_effect=[endpoint, endpoint, None],
            ), mock.patch.object(
                server_app, "run_step1_cleanup", return_value=direct_step,
            ), mock.patch(
                "orchestrator.pipeline_trace.start_trace", return_value=None,
            ):
                reply = server_app._invoke_pipeline_unlocked(
                    "Hi", [], conversation_id, False,
                    extra_context=context,
                )

            payload = json.loads(reply[0] if isinstance(reply, tuple) else reply)
            durable = memory.load_conversation_json(
                conversation_id, sessions_root=root,
            )
        self.assertEqual(payload["status"], "errored")
        self.assertIn("No AI endpoints configured", payload["failure_summary"])
        self.assertEqual(context["_visual_outcome"]["state"], "not_applicable")
        self.assertIn("error", context["_visual_outcome"]["reason"].lower())
        self.assertEqual(durable["last_status"], "errored")
        self.assertEqual(
            durable["messages"][-1]["visual_outcome"]["state"],
            "not_applicable",
        )
        self.assertIn(
            "error",
            durable["messages"][-1]["visual_outcome"]["reason"].lower(),
        )

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
