"""Tests for visual_synthesis (Phase 1 — emission reliability)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import visual_synthesis as vs  # noqa: E402

EXAMPLES = vs.SCHEMAS_ROOT / "examples"


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
    def test_narrow_regenerate_replaces_only_target_visual(self):
        import boot
        import conversation_memory
        from server import app as server

        malformed_fence = (
            '```ora-visual\n'
            '{not json\n'
            '```'
        )
        first_fence = (
            '```ora-visual\n'
            '{"type":"concept_map","title":"First sibling"}\n'
            '```'
        )
        second_fence = (
            '```ora-visual\n'
            '{"type":"pro_con","title":"Target sibling"}\n'
            '```'
        )
        original_content = (
            "Lead prose byte.\n" + malformed_fence
            + "\nMalformed fence stays byte-identical.\n" + first_fence
            + "\nMiddle prose byte.\n" + second_fence
            + "\nTail prose byte."
        )
        replacement = {
            "type": "pro_con",
            "title": "Narrowed target",
            "spec": {"pros": [{"text": "One subject"}], "cons": []},
        }

        def response_and_status(result):
            if isinstance(result, tuple):
                return result[0], result[1]
            return result, result.status_code

        with tempfile.TemporaryDirectory() as tmp:
            sessions_root = Path(tmp) / "sessions"
            conversation_id = "narrow-target-test"
            conversation_dir = sessions_root / conversation_id
            conversation_dir.mkdir(parents=True)
            conversation_path = conversation_dir / "conversation.json"
            conversation_path.write_text(json.dumps({
                "conversation_id": conversation_id,
                "messages": [
                    {"role": "user", "content": "Show both"},
                    {"role": "assistant", "content": original_content},
                ],
            }), encoding="utf-8")

            common_request = {
                "prose": original_content,
                "mode": "synthesis",
                "manual_visual_type": "pro_con",
                "narrow_subject": True,
                "conversation_id": conversation_id,
                "assistant_index": 0,
            }
            with (
                mock.patch.object(
                    conversation_memory, "_DEFAULT_SESSIONS_ROOT",
                    sessions_root,
                ),
                mock.patch.object(boot, "_mode_target_types", return_value=["pro_con"]),
                mock.patch.object(
                    boot, "_resolve_synthesis_endpoint", return_value={"id": "test"},
                ),
                mock.patch.object(
                    boot, "_strip_visual_blocks_and_markers", side_effect=lambda text: text,
                ),
                mock.patch.object(
                    vs, "synthesize_envelope", return_value=(replacement, []),
                ) as synthesize,
            ):
                with server.app.test_request_context(
                    "/api/visual/regenerate",
                    method="POST",
                    json={**common_request, "visual_block_index": 2},
                ):
                    valid_response, valid_status = response_and_status(
                        server.visual_regenerate()
                    )

                self.assertEqual(valid_status, 200)
                self.assertTrue(valid_response.get_json()["persisted"])
                self.assertTrue(
                    valid_response.get_json()["visual_outcome_persisted"],
                )
                self.assertEqual(
                    valid_response.get_json()["visual_outcome"]["state"],
                    "failed",
                )
                self.assertEqual(
                    valid_response.get_json()["visual_outcome"]["reason"],
                    (
                        "A narrower visual was saved, but insertion has not "
                        "been confirmed."
                    ),
                )
                self.assertEqual(
                    valid_response.get_json()["visual_outcome"]
                    ["legibility_attempts"],
                    {"2": "exhausted"},
                )
                persisted = json.loads(conversation_path.read_text(encoding="utf-8"))
                expected_content = (
                    "Lead prose byte.\n" + malformed_fence
                    + "\nMalformed fence stays byte-identical.\n" + first_fence
                    + "\nMiddle prose byte.\n```ora-visual\n"
                    + json.dumps(replacement, indent=2, ensure_ascii=False)
                    + "\n```\nTail prose byte."
                )
                self.assertEqual(
                    persisted["messages"][1]["content"], expected_content,
                )
                self.assertEqual(
                    persisted["messages"][1]["content"].count(first_fence), 1,
                )
                self.assertEqual(
                    persisted["messages"][1]["content"].count(malformed_fence), 1,
                )
                self.assertEqual(
                    persisted["messages"][1]["visual_outcome"]
                    ["legibility_attempts"],
                    {"2": "exhausted"},
                )
                self.assertEqual(
                    persisted["messages"][1]["visual_outcome"]["state"],
                    "failed",
                )
                self.assertEqual(
                    persisted["messages"][1]["visual_outcome"]["reason"],
                    (
                        "A narrower visual was saved, but insertion has not "
                        "been confirmed."
                    ),
                )
                bytes_after_valid = conversation_path.read_bytes()

                with server.app.test_request_context(
                    "/api/visual/regenerate",
                    method="POST",
                    json={**common_request, "visual_block_index": 2},
                ):
                    duplicate_response, duplicate_status = response_and_status(
                        server.visual_regenerate()
                    )
                self.assertEqual(duplicate_status, 409)
                self.assertEqual(
                    duplicate_response.get_json()["retry_status"], "exhausted",
                )
                self.assertTrue(
                    duplicate_response.get_json()["visual_outcome_persisted"],
                )
                self.assertEqual(
                    duplicate_response.get_json()["visual_outcome"],
                    persisted["messages"][1]["visual_outcome"],
                )
                self.assertEqual(synthesize.call_count, 1)
                self.assertEqual(conversation_path.read_bytes(), bytes_after_valid)

                with server.app.test_request_context(
                    "/api/visual/regenerate",
                    method="POST",
                    json={**common_request, "visual_block_index": "2"},
                ):
                    invalid_response, invalid_status = response_and_status(
                        server.visual_regenerate()
                    )
                self.assertEqual(invalid_status, 400)
                self.assertFalse(invalid_response.get_json()["ok"])
                self.assertEqual(conversation_path.read_bytes(), bytes_after_valid)

                with server.app.test_request_context(
                    "/api/visual/regenerate",
                    method="POST",
                    json={**common_request, "visual_block_index": 9},
                ):
                    missing_response, missing_status = response_and_status(
                        server.visual_regenerate()
                    )
                self.assertEqual(missing_status, 404)
                self.assertIn("targeted visual block", missing_response.get_json()["reason"])
                self.assertEqual(conversation_path.read_bytes(), bytes_after_valid)

    def test_narrow_failure_reports_only_a_confirmed_terminal_outcome(self):
        import boot
        import conversation_memory
        from server import app as server

        content = '```ora-visual\n{"type":"concept_map"}\n```'
        with tempfile.TemporaryDirectory() as tmp:
            sessions_root = Path(tmp) / "sessions"
            conversation_memory.save_turn_spatial_state(
                "narrow-failure-confirmation",
                "Show it",
                content,
                visual_outcome={"state": "building"},
                sessions_root=sessions_root,
            )
            with (
                mock.patch.object(
                    conversation_memory, "_DEFAULT_SESSIONS_ROOT", sessions_root,
                ),
                mock.patch.object(
                    boot, "_mode_target_types", return_value=["concept_map"],
                ),
                mock.patch.object(
                    boot, "_resolve_synthesis_endpoint", return_value={"id": "test"},
                ),
                mock.patch.object(
                    boot, "_strip_visual_blocks_and_markers",
                    side_effect=lambda text: text,
                ),
                mock.patch.object(
                    vs, "synthesize_envelope", return_value=(None, ["attempt"]),
                ),
                mock.patch.object(
                    conversation_memory,
                    "set_assistant_visual_outcome",
                    return_value=(None, None),
                ),
            ):
                with server.app.test_request_context(
                    "/api/visual/regenerate",
                    method="POST",
                    json={
                        "prose": content,
                        "mode": "synthesis",
                        "narrow_subject": True,
                        "conversation_id": "narrow-failure-confirmation",
                        "assistant_index": 0,
                        "visual_block_index": 0,
                    },
                ):
                    response = server.visual_regenerate()

        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertFalse(payload["visual_outcome_persisted"])
        self.assertNotIn("visual_outcome", payload)

    def test_visual_modules_use_runtime_configuration_root(self):
        import runtime_paths
        import visual_adversarial
        import visual_recovery
        import visual_validator

        expected = runtime_paths.CONFIG_DIR
        self.assertEqual(vs.SCHEMAS_ROOT, expected / "visual-schemas")
        self.assertEqual(visual_validator.SCHEMAS_ROOT, expected / "visual-schemas")
        self.assertEqual(visual_recovery.SCHEMAS_ROOT, expected / "visual-schemas")
        self.assertEqual(
            visual_adversarial.MODE_CONFIG_PATH,
            expected / "mode-to-visual.json",
        )

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
