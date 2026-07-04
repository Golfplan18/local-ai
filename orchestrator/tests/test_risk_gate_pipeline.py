"""Execution Review Phase 2 — integration of risk_gate into boot.run_pipeline
(the terminal reference path). Heavy internals are mocked; the assertions are
about the risk-gate wiring: sticky short-circuit, inline override, the
irreversible pre-executor hold (executor NOT reached), and route_observed."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_ORCH = Path(__file__).resolve().parent.parent
if str(_ORCH) not in sys.path:
    sys.path.insert(0, str(_ORCH))

import boot  # noqa: E402
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
            # No queue card writes hitting real files.
            mock.patch.object(rg, "write_task_gate_card", return_value="q1"),
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
        # A prompt whose Stage-A floor is irreversible must NOT reach the
        # gear executor; it returns the hold reply with a task-gate marker.
        with mock.patch.object(boot, "run_step1_cleanup") as m_s1, \
             mock.patch.object(boot, "run_step2_context_assembly") as m_s2, \
             mock.patch.object(boot, "run_gear4") as m_g4, \
             mock.patch.object(boot, "run_gear3") as m_g3, \
             mock.patch.object(boot, "route_output", side_effect=lambda r, *a, **k: r):
            m_s1.return_value = {"mode": "x"}
            m_s2.return_value = _fake_context_pkg(
                gear=4, raw="deploy this to production now")
            out = boot.run_pipeline("deploy this to production now",
                                    conversation_id="c1")
        m_g4.assert_not_called()
        m_g3.assert_not_called()
        self.assertIn("irreversible", out)
        self.assertIsNotNone(rg.read_task_gate_marker(out))

    def test_token_admits_held_task(self):
        # With a valid token for the fingerprint, the same task proceeds to
        # the executor (hold consumed).
        raw = "deploy this to production now"
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
            out = boot.run_pipeline(raw, conversation_id="c1")
        m_g4.assert_called_once()
        self.assertIn("EXECUTED", out)

    def test_task_gate_reply_one_mints_token(self):
        marker = rg.build_task_gate_prompt("irreversible", "fpZ", "q1")
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
