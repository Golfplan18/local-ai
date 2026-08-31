"""Execution Review Phase 2 — integration of risk_gate into boot.run_pipeline
(the terminal reference path). Heavy internals are mocked; the assertions are
about the risk-gate wiring: sticky short-circuit, inline override, the
irreversible pre-executor hold (executor NOT reached), and route_observed."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_ORCH = Path(__file__).resolve().parent.parent
if str(_ORCH) not in sys.path:
    sys.path.insert(0, str(_ORCH))
_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
import live_guard  # noqa: E402,F401 — quarantines durable oversight/telemetry writes

import boot  # noqa: E402
import oversight_queue  # noqa: E402
import risk_gate as rg  # noqa: E402
import tool_events as te  # noqa: E402


def _fake_context_pkg(gear=4, mode="root-cause-analysis", raw="do the thing"):
    return {"gear": gear, "mode_name": mode, "mode": mode, "mode_text": "",
            "cleaned_prompt": raw, "raw_prompt": raw, "trace_dir": None,
            "execution_context": "interactive"}


class TerminalRiskGateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._patches = [
            mock.patch.object(rg._rp, "DATA_DIR_STR", self._tmp),
            mock.patch.object(te, "APPROVALS_PATH",
                              os.path.join(self._tmp, "approvals.json")),
            mock.patch.object(boot, "load_routing_config", return_value={}),
            mock.patch.object(boot, "PIPELINE_TRACE_AVAILABLE", False),
            mock.patch.object(
                oversight_queue, "HUMAN_QUEUE_PATH",
                os.path.join(self._tmp, "human-queue.jsonl"),
            ),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def test_bare_risk_command_short_circuits(self):
        out = boot.run_pipeline("/risk high-risk", conversation_id="c1")
        self.assertIn("high-risk", out)
        self.assertEqual(rg.get_sticky("c1"), "high-risk")

    def test_risk_auto_clears(self):
        rg.set_sticky("c1", "irreversible")
        out = boot.run_pipeline("/risk auto", conversation_id="c1")
        self.assertIn("cleared", out)
        self.assertIsNone(rg.get_sticky("c1"))

    def test_irreversible_prompt_holds_before_executor(self):
        # Raw and cleaned/enriched forms are independent conservative floors.
        # Either disagreement direction must hold before the gear executor.
        cases = (
            (
                "dangerous raw, harmless cleaned",
                "send an email to the customers",
                "summarize the draft for me",
            ),
            (
                "harmless raw, dangerous cleaned",
                "summarize the draft for me",
                "send an email to the customers",
            ),
        )
        with mock.patch.object(boot, "run_step1_cleanup") as m_s1, \
             mock.patch.object(boot, "run_step2_context_assembly") as m_s2, \
             mock.patch.object(boot, "run_gear4") as m_g4, \
             mock.patch.object(boot, "run_gear3") as m_g3, \
             mock.patch.object(boot, "route_output", side_effect=lambda r, *a, **k: r):
            m_s1.return_value = {"mode": "x"}
            for index, (label, raw_request, enriched_request) in enumerate(cases):
                with self.subTest(label):
                    m_s2.return_value = _fake_context_pkg(
                        gear=4, mode="x", raw=enriched_request,
                    )
                    out = boot.run_pipeline(
                        raw_request,
                        conversation_id=f"tier-disagreement-{index}",
                        raw_user_input=raw_request,
                    )
                    self.assertIn("irreversible", out)
                    self.assertIsNotNone(rg.read_task_gate_marker(out))

            criteria_raw = "Summarize  this draft "
            m_s2.return_value = _fake_context_pkg(
                gear=4, mode="x", raw="summarize this draft",
            )
            with mock.patch.object(
                rg, "apply_criteria", return_value="HOLD:criteria unavailable",
            ):
                criteria_out = boot.run_pipeline(
                    "summarize this draft",
                    conversation_id="criteria-raw",
                    raw_user_input=criteria_raw,
                )
            criteria_marker = rg.read_task_gate_marker(criteria_out)
            self.assertEqual(
                criteria_marker["fp"],
                rg.task_fingerprint(
                    conversation_id="criteria-raw", prompt=criteria_raw,
                    surface="terminal", mode_id="x", output_target="screen",
                ),
            )
        m_g4.assert_not_called()
        m_g3.assert_not_called()

        outer = (
            "/direct /risk irreversible /framework process-inference "
            "summarize this draft"
        )
        dispatch = boot.effective_framework_dispatch(outer)
        turn_state = {}
        with mock.patch(
            "milestone_executor.run_framework_command",
        ) as framework_executor:
            try:
                framework_out = boot._run_pipeline_impl(
                    dispatch.effective_input,
                    output_target=dispatch.output_target,
                    extra_context={"risk_override": dispatch.risk_override},
                    raw_user_input=outer,
                    turn_state=turn_state,
                )
            finally:
                tool_events_module = turn_state.get("tool_events_module")
                if tool_events_module is not None:
                    tool_events_module.reset_turn_context(
                        turn_state.get("tool_events_context_token"),
                    )
                boot.reset_turn_trace_context(
                    turn_state.get("trace_context_token"),
                )
        framework_marker = rg.read_task_gate_marker(framework_out)
        self.assertEqual(
            framework_marker["fp"],
            rg.task_fingerprint(
                conversation_id=None, prompt=outer, surface="framework",
            ),
        )
        framework_executor.assert_not_called()

    def test_token_admits_held_task(self):
        # A token admits exactly one byte-identical raw task. A case/spacing
        # variant cannot consume or inherit it even when cleanup converges on
        # the same enriched request.
        raw = "deploy this to production now"
        variant = "Deploy  this to production now"
        fp = rg.task_fingerprint(conversation_id="c1", prompt=raw,
                                 surface="terminal", mode_id="x",
                                 output_target="screen", config_name="")
        rg.grant_task_token(fp, "c1")
        with mock.patch.object(boot, "run_step1_cleanup", return_value={"mode": "x"}), \
             mock.patch.object(boot, "run_step2_context_assembly",
                               return_value=_fake_context_pkg(gear=4, mode="x", raw=raw)), \
             mock.patch.object(boot, "run_gear4", return_value="EXECUTED") as m_g4, \
             mock.patch.object(boot, "route_output", side_effect=lambda r, *a, **k: r), \
             mock.patch.object(rg, "record_route_observed"):
            variant_out = boot.run_pipeline(
                variant, conversation_id="c1", raw_user_input=variant,
            )
            self.assertIn("irreversible", variant_out)
            m_g4.assert_not_called()
            self.assertTrue(rg.has_valid_task_token(fp))

            out = boot.run_pipeline(
                raw, conversation_id="c1", raw_user_input=raw,
            )
            self.assertIn("EXECUTED", out)
            self.assertFalse(rg.has_valid_task_token(fp))

            second_out = boot.run_pipeline(
                raw, conversation_id="c1", raw_user_input=raw,
            )
            self.assertIn("irreversible", second_out)
        m_g4.assert_called_once()

    def test_server_pipeline_uses_higher_raw_or_enriched_risk_and_exact_raw_identity(self):
        from server import app as server_runtime
        import milestone_executor

        captured = {}
        boot_api = mock.Mock()
        boot_api._context_source_exclusions.return_value = None
        boot_api._finalize_optional_context_package.side_effect = (
            lambda context, *_a, **_k: captured.update(context)
        )

        def _server_context(step1, *_args, **_kwargs):
            return _fake_context_pkg(
                gear=4,
                mode=step1.get("mode") or "x",
                raw=step1.get("cleaned_prompt") or "",
            )

        def _assert_fingerprint(frames, conversation_id, prompt, surface,
                                mode_id=""):
            marker = None
            for frame in frames:
                if not frame.startswith("data: "):
                    continue
                response = json.loads(frame[len("data: "):])
                decoded_marker = rg.read_task_gate_marker(
                    response.get("text", ""),
                )
                if decoded_marker is not None:
                    marker = decoded_marker
            self.assertEqual(
                marker["fp"],
                rg.task_fingerprint(
                    conversation_id=conversation_id, prompt=prompt,
                    surface=surface, mode_id=mode_id,
                ),
            )

        with mock.patch.object(server_runtime, "_boot_context_api", return_value=boot_api), \
             mock.patch.object(server_runtime, "run_step2_context_assembly", side_effect=_server_context), \
             mock.patch.object(server_runtime, "_begin_visual_outcome"), \
             mock.patch.object(server_runtime, "_conversation_turn_tag", return_value=""), \
             mock.patch.object(server_runtime, "_effective_conversation_tag", return_value=""), \
             mock.patch.object(server_runtime, "load_config", return_value={}), \
             mock.patch.object(server_runtime, "get_endpoint", return_value={"name": "test"}), \
             mock.patch.object(server_runtime, "_direct_system_prompt", return_value="system"), \
             mock.patch.object(milestone_executor, "run_framework_command", side_effect=AssertionError), \
             mock.patch.object(te, "get_turn_context", return_value={"conversation_id": "server-risk"}):
            raw_request = "send an email to the customers"
            frames = list(server_runtime._run_pipeline_from_step2(
                {
                    "mode": "x", "raw_prompt": "summarize the draft",
                    "cleaned_prompt": "summarize the draft", "pre_routing": {},
                },
                {}, [], "summarize the draft", raw_user_input=raw_request,
            ))
            _assert_fingerprint(frames, "server-risk", raw_request, "chat", "x")

            framework_cases = (
                (
                    "",
                    "/risk irreversible /framework process-inference summarize the draft",
                    "/framework process-inference summarize the draft",
                ),
                (
                    "process-inference",
                    "/risk irreversible summarize the draft",
                    "summarize the draft",
                ),
            )
            for index, (selected, raw_request, cleaned_request) in enumerate(
                framework_cases
            ):
                with self.subTest(framework_selected=selected or "typed"):
                    frames = list(server_runtime._pipeline_stream_impl(
                        cleaned_request, [],
                        panel_id=f"framework-risk-{index}",
                        extra_context={"risk_override": "irreversible"},
                        framework_selected=selected,
                        raw_user_input=raw_request,
                        turn_state={},
                    ))
                    _assert_fingerprint(
                        frames, f"framework-risk-{index}", raw_request,
                        "framework", selected,
                    )

            captured.clear()
            direct_raw = "/direct /risk irreversible hello"
            direct_frames = list(server_runtime._direct_stream(
                "hello", [], panel_id="direct-risk",
                extra_context={"risk_override": "irreversible"},
                raw_user_input=direct_raw,
            ))
            self.assertEqual(captured.get("cleaned_prompt"), "hello")
            self.assertNotIn("raw_prompt", captured)
            _assert_fingerprint(
                direct_frames, "direct-risk", direct_raw, "direct",
            )

    def test_task_gate_reply_one_mints_token(self):
        queue_id = rg.write_task_gate_card(
            "irreversible", "fpZ", "c1", "terminal", "deploy prod",
        )
        marker = rg.build_task_gate_prompt(
            "irreversible", "fpZ", queue_id,
        )
        history = [{"role": "user", "content": "deploy prod"},
                   {"role": "assistant", "content": marker}]
        out = boot.run_pipeline("1", history=history, conversation_id="c1")
        self.assertIn("Approved", out)
        self.assertTrue(rg.has_valid_task_token("fpZ", "c1"))

    def test_normal_turn_records_route_observed(self):
        with mock.patch.object(boot, "run_step1_cleanup", return_value={"mode": "x"}), \
             mock.patch.object(boot, "run_step2_context_assembly",
                               return_value=_fake_context_pkg(gear=4, raw="analyze X")), \
             mock.patch.object(boot, "run_gear4", return_value="OUT"), \
             mock.patch.object(boot, "route_output", side_effect=lambda r, *a, **k: r), \
             mock.patch.object(rg, "record_route_observed") as m_ro:
            boot.run_pipeline("analyze X", conversation_id="c1")
        m_ro.assert_called()


if __name__ == "__main__":
    unittest.main()
