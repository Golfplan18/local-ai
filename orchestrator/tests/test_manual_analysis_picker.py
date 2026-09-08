#!/usr/bin/env python3
"""Regression tests for the V3 manual analysis picker path.

The picker sends ``manual_mode_selection`` from the browser. The server must
honor that explicit pick, replace stale automatic pre-routing state, and ask
the selected mode's Stage 3 missing-input question conversationally in the
plain-JSON V3 submit flow.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from copy import deepcopy
import json
import os
import sys
import unittest
from unittest import mock

WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator"))
sys.path.insert(0, os.path.join(WORKSPACE, "server"))

from server import app as server  # noqa: E402


def _events(chunks: list[str]) -> list[dict]:
    out = []
    for chunk in chunks:
        if chunk.startswith("data: "):
            out.append(json.loads(chunk[6:]))
    return out


def _base_step1() -> dict:
    return {
        "mode": "general-inquiry",
        "triage_tier": 1,
        "classification_confidence": "auto",
        "detected_invocation": "",
        "cleaned_prompt": "who benefits",
        "operational_notation": "who benefits",
        "pre_routing": {
            "dispatched_mode_id": "general-inquiry",
            "territory": "T0-default-judgment",
            "bypass_to_direct_response": False,
            "pending_clarification": None,
            "pending_clarification_stage": None,
            "completeness_gaps": [],
            "dispatch_announcement": "old automatic announcement",
            "lighter_sibling_mode_id": None,
            "confidence": "fallback",
            "stage1_output": {"matches": [{"mode": "general-inquiry"}]},
        },
    }


class TestManualAnalysisPicker(unittest.TestCase):
    def setUp(self):
        server._pending_clarification.clear()

    def tearDown(self):
        server._pending_clarification.clear()

    def _common_patches(self):
        return [
            mock.patch.object(server, "load_config", return_value={"ok": True}),
            mock.patch.object(server, "get_endpoint",
                              return_value={"name": "fake", "context_window": 4096}),
        ]

    @contextmanager
    def _isolated_routing_turn(self, *, conversation_tag="", from_step2=None):
        """Keep routing and privacy checks real; stop at the analysis handoff."""
        boot = sys.modules[server.run_step1_cleanup.__module__]
        from orchestrator import conversation_memory, oversight_events, pipeline_trace

        endpoint = {
            "name": "routing-fixture-model", "context_window": 65536,
            "max_tokens": 512,
        }
        automatic = []
        real_cleanup = server.run_step1_cleanup

        def identity_cleanup(messages, selected_endpoint):
            self.assertEqual(selected_endpoint, endpoint)
            self.assertEqual(boot._CURRENT_STEP_CV.get(), "step1-phase-a")
            prompt = messages[-1]["content"].split("[Current prompt]\n")[-1]
            return "### CLEANED PROMPT (Operational Notation)\n" + prompt

        def capture_cleanup(*args, **kwargs):
            step1 = real_cleanup(*args, **kwargs)
            automatic.append(deepcopy(step1))
            return step1

        with ExitStack() as stack:
            patches = [
                mock.patch.object(server, "load_config", return_value={"fixture": True}),
                mock.patch.object(server, "get_endpoint", return_value=endpoint),
                mock.patch.object(boot, "get_slot_endpoint", return_value=endpoint),
                mock.patch.object(boot, "call_model", side_effect=identity_cleanup),
                mock.patch.object(server, "run_step1_cleanup", side_effect=capture_cleanup),
                mock.patch.object(server, "_preflight_framework_turn", return_value=None),
                mock.patch.object(server, "_begin_visual_outcome", return_value=None),
                mock.patch.object(conversation_memory, "get_conversation_tag",
                                  return_value=conversation_tag),
                mock.patch.object(conversation_memory, "load_conversation_json",
                                  return_value={"tag": conversation_tag}),
                mock.patch.object(server, "_conversation_creation_tags", {}),
                mock.patch.object(server, "_unreadable_conversations", set()),
                mock.patch.object(boot, "PIPELINE_TRACE_AVAILABLE", False),
                mock.patch.object(pipeline_trace, "finalize_manifest", return_value=None),
                mock.patch.object(oversight_events, "emit", return_value={}),
                mock.patch.object(server, "call_model",
                                  side_effect=AssertionError("unexpected provider call")),
                mock.patch.object(server, "_direct_stream",
                                  side_effect=AssertionError("should not direct-stream")),
                mock.patch.object(server, "_run_pipeline_from_step2", side_effect=(
                    from_step2 or AssertionError("should not run analysis yet")
                )),
            ]
            for patch in patches:
                stack.enter_context(patch)
            yield automatic

    def test_missing_selected_mode_input_is_saved_as_question(self):
        question = (
            "Ask: 'Could you describe the situation, decision, or paste the "
            "article/document you want me to look at?'"
        )
        with self._isolated_routing_turn() as automatic:
            chunks = list(server._pipeline_stream(
                "Steelman this argument.",
                [],
                panel_id="manual-missing",
                manual_mode_selection="cui-bono",
                config_name="routing-fixture-profile",
            ))

        events = _events(chunks)
        self.assertEqual(events[-1]["type"], "response")
        self.assertEqual(events[-1]["text"], question)
        self.assertEqual(len(automatic), 1)
        self.assertNotEqual(automatic[0]["mode"], "cui-bono")
        pending = server._pending_clarification["manual-missing"]
        self.assertEqual(pending["source"], "manual_mode_selection")
        self.assertEqual(pending["step1"]["mode"], "cui-bono")
        self.assertEqual(pending["config_name"], "routing-fixture-profile")
        self.assertEqual(pending["model_id"], "routing-fixture-model")
        self.assertEqual(pending["conversation_tag"], "")
        self.assertEqual(pending["turn_privacy"], server._turn_privacy_for_tag(""))
        self.assertEqual(
            pending["step1"]["pre_routing"]["stage3_output"]["missing_fields"],
            ["situation_or_artifact"],
        )
        self.assertEqual(
            pending["step1"]["pre_routing"]["pending_clarification"],
            question,
        )

    def test_next_reply_resumes_selected_mode_without_reclassification(self):
        captured = {}

        def fake_from_step2(step1, config, history, user_input, **kwargs):
            captured["step1"] = step1
            captured["config"] = config
            captured["user_input"] = user_input
            captured["kwargs"] = kwargs
            yield server._sse("response", text="analysis complete")

        server._pending_clarification["manual-resume"] = {
            "source": "manual_mode_selection",
            "step1": {
                "mode": "cui-bono",
                "triage_tier": 1,
                "cleaned_prompt": "who benefits",
                "operational_notation": "who benefits",
                "pre_routing": {
                    "pending_clarification": "Need the situation.",
                    "pending_clarification_stage": "stage3",
                    "completeness_gaps": ["situation_or_artifact"],
                },
            },
            "config": {"ok": True},
            "history": [],
            "user_input": "who benefits",
            "images": None,
            "extra_context": None,
            **server._capture_clarification_authority(
                config_name="paused-fixture-profile",
                model_id="routing-fixture-model",
                conversation_tag="private",
            ),
        }

        with self._isolated_routing_turn(
            conversation_tag="private", from_step2=fake_from_step2,
        ) as automatic:
            chunks = list(server._pipeline_stream(
                "The zoning amendment permits eight-storey apartments near the "
                "station and removes minimum parking requirements. Existing "
                "tenants receive relocation assistance during construction.",
                [],
                panel_id="manual-resume",
                config_name="later-fixture-profile",
            ))

        events = _events(chunks)
        self.assertEqual(events[-1]["text"], "analysis complete")
        self.assertEqual(automatic, [], "a selected-mode reply must not be reclassified")
        self.assertNotIn("manual-resume", server._pending_clarification)
        self.assertEqual(captured["step1"]["mode"], "cui-bono")
        self.assertEqual(captured["config"], {"ok": True})
        self.assertEqual(captured["kwargs"]["config_name"], "paused-fixture-profile")
        self.assertEqual(captured["kwargs"]["conversation_tag"], "private")
        self.assertEqual(captured["user_input"], "who benefits")
        self.assertIn("who benefits", captured["step1"]["operational_notation"])
        self.assertIn("The zoning amendment permits eight-storey apartments",
                      captured["step1"]["operational_notation"])
        self.assertIsNone(
            captured["step1"]["pre_routing"]["pending_clarification"]
        )
        self.assertTrue(
            captured["step1"]["pre_routing"]["manual_clarification_answered"]
        )

    def test_complete_selected_mode_replaces_old_prerouting_state(self):
        captured = {}
        prompt = (
            "Steelman this argument.\n\n"
            "The zoning amendment allows eight-storey apartments around the "
            "station, removes on-site parking minimums, and gives existing "
            "tenants relocation assistance. Landowners may build more units, "
            "while nearby residents will face two years of construction."
        )

        def fake_from_step2(step1, config, history, user_input, **kwargs):
            captured["step1"] = step1
            yield server._sse("response", text="ok")

        with self._isolated_routing_turn(from_step2=fake_from_step2) as automatic:
            chunks = list(server._pipeline_stream(
                prompt,
                [],
                panel_id="manual-complete",
                manual_mode_selection="cui-bono",
            ))

        events = _events(chunks)
        self.assertEqual(events[-1]["text"], "ok")
        self.assertEqual(len(automatic), 1)
        self.assertNotEqual(automatic[0]["mode"], "cui-bono")
        pr = captured["step1"]["pre_routing"]
        self.assertEqual(captured["step1"]["mode"], "cui-bono")
        self.assertEqual(pr["dispatched_mode_id"], "cui-bono")
        self.assertEqual(pr["manual_override_prior_dispatch"], automatic[0]["mode"])
        self.assertEqual(pr["territory"], "T2-interest-and-power")
        self.assertIn("who-benefits analysis (cui bono)", pr["dispatch_announcement"])
        self.assertNotEqual(
            pr["dispatch_announcement"],
            automatic[0]["pre_routing"]["dispatch_announcement"],
        )
        self.assertIsNone(pr["pending_clarification"])
        self.assertIsNone(pr["pending_clarification_stage"])
        self.assertEqual(pr["completeness_gaps"], [])
        self.assertTrue(pr["stage3_output"]["inputs_complete"])
        self.assertIn("situation_or_artifact", pr["stage3_output"]["validated_inputs"])
        self.assertTrue(pr["manual_override_applied"])

    def test_selected_lens_is_threaded_into_pipeline_context(self):
        captured = {}

        def fake_from_step2(step1, config, history, user_input, **kwargs):
            captured["extra_context"] = kwargs.get("extra_context")
            yield server._sse("response", text="ok")

        complete = {
            "inputs_complete": True,
            "validated_inputs": {"situation_or_artifact": "present"},
            "missing_fields": [],
            "completeness_question": None,
            "graceful_degradation_offer": None,
            "lighter_sibling_mode_id": None,
            "stage3_status": "complete",
        }
        patches = self._common_patches() + [
            mock.patch.object(server, "run_step1_cleanup", return_value=_base_step1()),
            mock.patch.object(server, "stage3_input_completeness_check",
                              return_value=complete),
            mock.patch.object(server, "compose_dispatch_announcement",
                              return_value="manual announcement"),
            mock.patch.object(server, "_run_pipeline_from_step2",
                              side_effect=fake_from_step2),
            mock.patch.object(server, "_direct_stream",
                              side_effect=AssertionError("should not direct-stream")),
        ]
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            chunks = list(server._pipeline_stream(
                "Who benefits from the zoning amendment text pasted here?",
                [],
                panel_id="manual-lens",
                manual_mode_selection="cui-bono",
                manual_lens_selection="ulrich-csh-boundary-categories",
            ))

        events = _events(chunks)
        self.assertEqual(events[-1]["text"], "ok")
        self.assertEqual(
            captured["extra_context"]["selected_lens_id"],
            "ulrich-csh-boundary-categories",
        )

    def test_lens_owned_applicability_remains_valid_for_mode(self):
        self.assertTrue(
            server._lens_available_for_mode("root-cause-analysis", "inversion")
        )
        rows = server.list_pickable_analysis_modes()
        root_cause = next(row for row in rows if row["id"] == "root-cause-analysis")
        lenses = {lens["id"]: lens for lens in root_cause["lenses"]}
        self.assertIn("inversion", lenses)
        self.assertEqual(lenses["inversion"]["category"], "related")


if __name__ == "__main__":
    unittest.main()
