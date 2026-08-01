#!/usr/bin/env python3
"""Regression tests for the V3 manual analysis picker path.

The picker sends ``manual_mode_selection`` from the browser. The server must
honor that explicit pick, replace stale automatic pre-routing state, and ask
the selected mode's Stage 3 missing-input question conversationally in the
plain-JSON V3 submit flow.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest import mock

WORKSPACE = os.path.expanduser("~/ora")
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

    def test_missing_selected_mode_input_is_saved_as_question(self):
        question = "To run this analysis, I need the situation. Could you share it?"
        missing = {
            "inputs_complete": False,
            "validated_inputs": {},
            "missing_fields": ["situation_or_artifact"],
            "completeness_question": question,
            "graceful_degradation_offer": None,
            "lighter_sibling_mode_id": None,
            "stage3_status": "missing-input-elicited",
        }

        patches = self._common_patches() + [
            mock.patch.object(server, "run_step1_cleanup", return_value=_base_step1()),
            mock.patch.object(server, "stage3_input_completeness_check",
                              return_value=missing),
            mock.patch.object(server, "_direct_stream",
                              side_effect=AssertionError("should not direct-stream")),
            mock.patch.object(server, "_run_pipeline_from_step2",
                              side_effect=AssertionError("should not run yet")),
        ]
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            chunks = list(server._pipeline_stream(
                "who benefits",
                [],
                panel_id="manual-missing",
                manual_mode_selection="cui-bono",
            ))

        events = _events(chunks)
        self.assertEqual(events[-1]["type"], "response")
        self.assertEqual(events[-1]["text"], question)
        pending = server._pending_clarification["manual-missing"]
        self.assertEqual(pending["source"], "manual_mode_selection")
        self.assertEqual(pending["step1"]["mode"], "cui-bono")
        self.assertEqual(
            pending["step1"]["pre_routing"]["pending_clarification"],
            question,
        )

    def test_next_reply_resumes_selected_mode_without_reclassification(self):
        captured = {}

        def fake_from_step2(step1, config, history, user_input, **kwargs):
            captured["step1"] = step1
            captured["user_input"] = user_input
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
        }

        patches = self._common_patches() + [
            mock.patch.object(server, "_run_pipeline_from_step2",
                              side_effect=fake_from_step2),
        ]
        with patches[0], patches[1], patches[2]:
            chunks = list(server._pipeline_stream(
                "Here is the zoning amendment text.",
                [],
                panel_id="manual-resume",
            ))

        events = _events(chunks)
        self.assertEqual(events[-1]["text"], "analysis complete")
        self.assertIn("who benefits", captured["step1"]["operational_notation"])
        self.assertIn("Here is the zoning amendment text.",
                      captured["step1"]["operational_notation"])
        self.assertIsNone(
            captured["step1"]["pre_routing"]["pending_clarification"]
        )
        self.assertTrue(
            captured["step1"]["pre_routing"]["manual_clarification_answered"]
        )

    def test_complete_selected_mode_replaces_old_prerouting_state(self):
        captured = {}

        def fake_from_step2(step1, config, history, user_input, **kwargs):
            captured["step1"] = step1
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
                panel_id="manual-complete",
                manual_mode_selection="cui-bono",
            ))

        events = _events(chunks)
        self.assertEqual(events[-1]["text"], "ok")
        pr = captured["step1"]["pre_routing"]
        self.assertEqual(captured["step1"]["mode"], "cui-bono")
        self.assertEqual(pr["dispatched_mode_id"], "cui-bono")
        self.assertEqual(pr["dispatch_announcement"], "manual announcement")
        self.assertIsNone(pr["pending_clarification"])
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
