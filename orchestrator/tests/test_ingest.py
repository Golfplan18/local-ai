"""Tests for the unified ingest pipeline (orchestrator.historical.ingest).

All three stage functions are mocked — these tests verify orchestration:
stage order, flag routing, backend propagation, worker capping, and
summary shape.
"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date
from unittest.mock import patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.historical import ingest  # noqa: E402


def _mocks():
    return (
        patch.object(ingest, "run_batch",
                     return_value={"files_succeeded": 2}),
        patch.object(ingest, "run_chain_detection",
                     return_value={"sessions": 5, "chains": 1,
                                   "sessions_to_paths": {"s1": ["a.md"]}}),
        patch.object(ingest, "run_chunk_emission",
                     return_value={"sessions_processed": 1}),
        patch.object(ingest, "run_phase5",
                     return_value={"pairs_processed": 3}),
    )


class TestRunIngest(unittest.TestCase):

    def test_all_stages_run_in_order(self):
        m_batch, m_detect, m_emit, m_p5 = _mocks()
        order = []
        with m_batch as b, m_detect as d, m_emit as e, m_p5 as p:
            b.side_effect = lambda **kw: order.append("cleanup") or {"ok": 1}
            d.side_effect = lambda **kw: order.append("detect") or {
                "sessions": 1, "chains": 0, "sessions_to_paths": {}}
            e.side_effect = lambda *a, **kw: order.append("emit") or {}
            p.side_effect = lambda **kw: order.append("phase5") or {}
            summary = ingest.run_ingest(progress=False)
        self.assertEqual(order, ["cleanup", "detect", "emit", "phase5"])
        self.assertIn("cleanup", summary)
        self.assertIn("chunks", summary)
        self.assertIn("engrams", summary)
        self.assertIn("duration_secs", summary)

    def test_no_chunks_skips_stage_two(self):
        m_batch, m_detect, m_emit, m_p5 = _mocks()
        with m_batch, m_detect as d, m_emit as e, m_p5:
            summary = ingest.run_ingest(chunks=False, progress=False)
        d.assert_not_called()
        e.assert_not_called()
        self.assertEqual(summary["chunks"], {"skipped": True})

    def test_no_engrams_skips_stage_three(self):
        m_batch, m_detect, m_emit, m_p5 = _mocks()
        with m_batch, m_detect, m_emit, m_p5 as p:
            summary = ingest.run_ingest(engrams=False, progress=False)
        p.assert_not_called()
        self.assertEqual(summary["engrams"], {"skipped": True})

    def test_backend_propagates_to_all_stages(self):
        m_batch, m_detect, m_emit, m_p5 = _mocks()
        with m_batch as b, m_detect, m_emit, m_p5 as p:
            ingest.run_ingest(backend="claude-cli", progress=False)
        self.assertEqual(b.call_args[1]["backend"], "claude-cli")
        self.assertEqual(p.call_args[1]["backend"], "claude-cli")

    def test_cli_backend_caps_phase5_workers(self):
        m_batch, m_detect, m_emit, m_p5 = _mocks()
        with m_batch, m_detect, m_emit, m_p5 as p:
            ingest.run_ingest(backend="claude-cli", max_workers=8,
                              progress=False)
        self.assertLessEqual(p.call_args[1]["max_workers"], 3)

    def test_date_filters_reach_cleanup(self):
        m_batch, m_detect, m_emit, m_p5 = _mocks()
        with m_batch as b, m_detect, m_emit, m_p5:
            ingest.run_ingest(from_date=date(2026, 5, 1), progress=False)
        self.assertEqual(b.call_args[1]["from_date"], date(2026, 5, 1))


class TestIngestCLI(unittest.TestCase):

    def test_cli_flags_route(self):
        m_batch, m_detect, m_emit, m_p5 = _mocks()
        with m_batch as b, m_detect, m_emit, m_p5 as p, \
             patch("builtins.print"):
            ingest.main(["--backend", "claude-cli", "--no-engrams",
                         "--quiet", "--limit", "10"])
        self.assertEqual(b.call_args[1]["backend"], "claude-cli")
        self.assertEqual(b.call_args[1]["limit"], 10)
        p.assert_not_called()


if __name__ == "__main__":
    unittest.main()
