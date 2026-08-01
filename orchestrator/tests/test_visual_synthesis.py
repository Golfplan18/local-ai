"""Tests for visual_synthesis (Phase 1 — emission reliability)."""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import visual_synthesis as vs  # noqa: E402

EXAMPLES = Path(os.path.expanduser("~/ora/config/visual-schemas/examples"))


def _example(vtype: str) -> dict:
    return json.loads((EXAMPLES / f"{vtype}.valid.json").read_text())


class _MockModel:
    """Returns a scripted sequence of responses; repeats the last forever."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        i = min(len(self.prompts) - 1, len(self.responses) - 1)
        return self.responses[i]


class TestSynthesize(unittest.TestCase):
    def test_one_shot_valid(self):
        env_in = _example("concept_map")
        model = _MockModel([json.dumps(env_in)])
        env, attempts = vs.synthesize_envelope(
            "some prose", "synthesis", ["concept_map"], model)
        self.assertIsNotNone(env)
        self.assertEqual(env["type"], "concept_map")
        self.assertEqual(len(attempts), 1)
        self.assertTrue(attempts[0]["ok"])
        self.assertEqual(len(model.prompts), 1)

    def test_repair_after_ascii_then_valid(self):
        ascii_art = "Here is a concept map:\n+------+\n| node |\n+------+\n"
        valid = json.dumps(_example("concept_map"))
        model = _MockModel([ascii_art, valid])
        env, attempts = vs.synthesize_envelope(
            "prose", "synthesis", ["concept_map"], model)
        self.assertIsNotNone(env)
        self.assertEqual(len(attempts), 2)
        self.assertFalse(attempts[0]["ok"])
        self.assertTrue(attempts[1]["ok"])
        # The repair prompt must carry the failure feedback forward.
        self.assertIn("INVALID", model.prompts[1].upper())

    def test_autofill_restores_mechanical_fields(self):
        env_in = _example("concept_map")
        for k in ("id", "schema_version", "mode_context", "semantic_description"):
            env_in.pop(k, None)
        model = _MockModel([json.dumps(env_in)])
        env, attempts = vs.synthesize_envelope(
            "prose", "terrain-mapping", ["concept_map"], model)
        self.assertIsNotNone(env, f"attempts={attempts}")
        self.assertEqual(env["schema_version"], vs.SCHEMA_VERSION)
        self.assertEqual(env["mode_context"], "terrain-mapping")
        self.assertTrue(env["id"])
        self.assertIn("short_alt", env["semantic_description"])

    def test_persistent_garbage_returns_none(self):
        model = _MockModel(["not json at all"])
        env, attempts = vs.synthesize_envelope(
            "prose", "synthesis", ["concept_map"], model)
        self.assertIsNone(env)
        self.assertEqual(len(attempts), vs.MAX_REPAIR_ROUNDS + 1)
        self.assertTrue(all(not a["ok"] for a in attempts))

    def test_call_fn_exception_is_caught(self):
        def boom(_):
            raise RuntimeError("endpoint down")
        env, attempts = vs.synthesize_envelope("p", "synthesis", ["concept_map"], boom)
        self.assertIsNone(env)
        self.assertEqual(len(attempts), 1)
        self.assertIn("call_fn error", attempts[0]["reason"])


class TestAutofill(unittest.TestCase):
    def test_preserves_authored_fields(self):
        env = vs.autofill(
            {"id": "mine", "type": "fishbone",
             "semantic_description": {"short_alt": "authored alt"}},
            "root-cause-analysis", "fishbone")
        self.assertEqual(env["id"], "mine")               # not overwritten
        self.assertEqual(env["type"], "fishbone")
        self.assertEqual(env["semantic_description"]["short_alt"], "authored alt")
        self.assertEqual(env["schema_version"], vs.SCHEMA_VERSION)
        self.assertEqual(env["mode_context"], "root-cause-analysis")

    def test_fills_type_from_target_when_missing(self):
        env = vs.autofill({}, "systems-dynamics", "causal_loop_diagram")
        self.assertEqual(env["type"], "causal_loop_diagram")
        self.assertIn("short_alt", env["semantic_description"])

    def test_requested_type_overrides_mismatched_model_type(self):
        env = vs.autofill(
            {"type": "causal_loop_diagram"},
            "root-cause-analysis",
            "fishbone",
        )
        self.assertEqual(env["type"], "fishbone")


class TestVisualKindThreading(unittest.TestCase):
    def test_pipeline_merges_extra_context_before_visual_hook(self):
        import boot

        seen = {}

        def fake_step1(user_input, conv_context, config, **kwargs):
            return {"mode": "root-cause-analysis", "cleaned_prompt": user_input}

        def fake_step2(step1, config, **kwargs):
            return {"gear": 4, "cleaned_prompt": step1["cleaned_prompt"]}

        def fake_hook(response, context_pkg):
            seen.update(context_pkg)
            return response

        with (
            mock.patch.object(boot, "PIPELINE_TRACE_AVAILABLE", False),
            mock.patch.object(boot, "load_routing_config", return_value={}),
            mock.patch.object(boot, "run_step1_cleanup", side_effect=fake_step1),
            mock.patch.object(boot, "run_step2_context_assembly", side_effect=fake_step2),
            mock.patch.object(boot, "run_gear4", return_value="answer"),
            mock.patch.object(boot, "_run_visual_hook", side_effect=fake_hook),
            mock.patch.object(boot, "route_output", side_effect=lambda text, *_: text),
        ):
            result = boot.run_pipeline(
                "diagnose this",
                extra_context={"visual_kind": "fishbone", "ignored": None},
            )

        self.assertEqual(result, "answer")
        self.assertEqual(seen["visual_kind"], "fishbone")
        self.assertNotIn("ignored", seen)

    def test_agentic_loop_forwards_extra_context(self):
        import boot

        extra = {"visual_kind": "tornado"}
        with mock.patch.object(boot, "run_pipeline", return_value="answer") as run:
            self.assertEqual(
                boot.run_agentic_loop("show sensitivity", extra_context=extra),
                "answer",
            )
        self.assertEqual(run.call_args.kwargs["extra_context"], extra)

    def test_regenerate_honors_manual_visual_type(self):
        import boot
        from server import app as server

        seen = {}

        def target_types(mode, preferred_kind=None):
            seen["args"] = (mode, preferred_kind)
            return [preferred_kind] if preferred_kind else ["concept_map"]

        with (
            mock.patch.object(boot, "_mode_target_types", side_effect=target_types),
            mock.patch.object(boot, "_resolve_synthesis_endpoint", return_value={"id": "test"}),
            mock.patch.object(boot, "_strip_visual_blocks_and_markers", side_effect=lambda text: text),
            mock.patch.object(vs, "synthesize_envelope", return_value=({"type": "fishbone"}, [])),
            server.app.test_request_context(
                "/api/visual/regenerate",
                method="POST",
                json={
                    "prose": "Recurring failures",
                    "mode": "root-cause-analysis",
                    "manual_visual_type": "fishbone",
                },
            ),
        ):
            response = server.visual_regenerate()

        self.assertTrue(response.get_json()["ok"])
        self.assertEqual(seen["args"], ("root-cause-analysis", "fishbone"))


if __name__ == "__main__":
    unittest.main()
