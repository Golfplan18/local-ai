#!/usr/bin/env python3
"""Tests for the per-turn token-usage capture and cost-summary aggregator.

Covers the data path from a usage.jsonl input → cost-summary.json output:
- per-model aggregation of calls / prompt_tokens / completion_tokens
- pricing join against ``config/model-registry.json``
- per-model + grand-total cost in USD
- handling of unpriced models (flagged, not dropped)
- empty / missing usage.jsonl returns a status placeholder, no crash
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))

import boot  # noqa: E402


class CostSummaryAggregator(unittest.TestCase):
    """``compute_cost_summary`` reads usage.jsonl, joins pricing, writes JSON."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cost-summary-test-")
        self.addCleanup(self._rm_tmp)

    def _rm_tmp(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_usage(self, records: list[dict]) -> None:
        path = os.path.join(self.tmp, "usage.jsonl")
        with open(path, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    def _fake_registry(self, models: dict[str, dict]) -> dict:
        return {"models": models}

    def test_no_usage_file_returns_placeholder(self):
        summary = boot.compute_cost_summary(self.tmp)
        self.assertEqual(summary.get("status"), "no_usage_data")

    def test_empty_trace_dir_returns_placeholder(self):
        summary = boot.compute_cost_summary("")
        self.assertEqual(summary.get("status"), "no_trace_dir")

    def test_single_model_priced_call(self):
        self._write_usage([
            {
                "model_id": "qwen/qwen3.5-9b",
                "service": "openrouter",
                "prompt_tokens": 1000,
                "completion_tokens": 500,
                "total_tokens": 1500,
            },
        ])
        fake_reg = self._fake_registry({
            "qwen/qwen3.5-9b": {
                "pricing": {
                    "input_per_token": 4e-08,   # $0.04 / M
                    "output_per_token": 1.5e-07,  # $0.15 / M
                },
            },
        })
        # Write the registry into a temp file and point WORKSPACE at
        # the parent. compute_cost_summary opens
        # os.path.join(WORKSPACE, "config/model-registry.json").
        cfg_dir = os.path.join(self.tmp, "config")
        os.makedirs(cfg_dir, exist_ok=True)
        with open(os.path.join(cfg_dir, "model-registry.json"), "w") as f:
            json.dump(fake_reg, f)
        with patch.object(boot, "WORKSPACE", self.tmp):
            summary = boot.compute_cost_summary(self.tmp)
        self.assertEqual(summary["status"], "computed")
        rows = summary["per_model"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["model_id"], "qwen/qwen3.5-9b")
        self.assertEqual(row["calls"], 1)
        self.assertEqual(row["prompt_tokens"], 1000)
        self.assertEqual(row["completion_tokens"], 500)
        # 1000 * 4e-8 = $0.00004 input
        # 500 * 1.5e-7 = $0.000075 output
        # total = $0.000115
        self.assertAlmostEqual(row["input_cost_usd"], 0.00004, places=6)
        self.assertAlmostEqual(row["output_cost_usd"], 0.000075, places=6)
        self.assertAlmostEqual(row["total_cost_usd"], 0.000115, places=6)
        self.assertTrue(row["priced"])
        # Grand totals match the single row.
        totals = summary["totals"]
        self.assertEqual(totals["calls"], 1)
        self.assertEqual(totals["prompt_tokens"], 1000)
        self.assertEqual(totals["completion_tokens"], 500)
        self.assertAlmostEqual(totals["total_cost_usd"], 0.000115, places=6)

    def test_multi_model_with_unpriced(self):
        self._write_usage([
            {"model_id": "openai/gpt-5.5", "service": "openrouter",
             "prompt_tokens": 2000, "completion_tokens": 1000,
             "total_tokens": 3000},
            {"model_id": "openai/gpt-5.5", "service": "openrouter",
             "prompt_tokens": 500, "completion_tokens": 200,
             "total_tokens": 700},
            {"model_id": "custom/local-model", "service": "openrouter",
             "prompt_tokens": 100, "completion_tokens": 50,
             "total_tokens": 150},
        ])
        fake_reg = self._fake_registry({
            "openai/gpt-5.5": {
                "pricing": {
                    "input_per_token": 5e-06,   # $5 / M
                    "output_per_token": 3e-05,  # $30 / M
                },
            },
            # custom/local-model intentionally absent from pricing
        })
        cfg_dir = os.path.join(self.tmp, "config")
        os.makedirs(cfg_dir, exist_ok=True)
        with open(os.path.join(cfg_dir, "model-registry.json"), "w") as f:
            json.dump(fake_reg, f)
        with patch.object(boot, "WORKSPACE", self.tmp):
            summary = boot.compute_cost_summary(self.tmp)
        self.assertEqual(summary["status"], "computed")
        # Two distinct models, with gpt-5.5 having higher cost so it
        # should sort first.
        rows = summary["per_model"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["model_id"], "openai/gpt-5.5")
        gpt = rows[0]
        self.assertEqual(gpt["calls"], 2)
        self.assertEqual(gpt["prompt_tokens"], 2500)
        self.assertEqual(gpt["completion_tokens"], 1200)
        # 2500 * 5e-6 = $0.0125 input
        # 1200 * 3e-5 = $0.036 output
        # total = $0.0485
        self.assertAlmostEqual(gpt["input_cost_usd"], 0.0125, places=6)
        self.assertAlmostEqual(gpt["output_cost_usd"], 0.036, places=6)
        self.assertAlmostEqual(gpt["total_cost_usd"], 0.0485, places=6)
        # Unpriced model gets calls and tokens but zero cost + priced=False
        local = rows[1]
        self.assertEqual(local["model_id"], "custom/local-model")
        self.assertEqual(local["calls"], 1)
        self.assertFalse(local["priced"])
        self.assertEqual(local["total_cost_usd"], 0.0)
        self.assertIn("custom/local-model", summary["unpriced_models"])

    def test_cost_summary_file_is_written(self):
        self._write_usage([
            {"model_id": "openai/gpt-5.5", "prompt_tokens": 100,
             "completion_tokens": 50, "total_tokens": 150,
             "service": "openrouter"},
        ])
        fake_reg = self._fake_registry({
            "openai/gpt-5.5": {
                "pricing": {"input_per_token": 5e-06, "output_per_token": 3e-05},
            },
        })
        cfg_dir = os.path.join(self.tmp, "config")
        os.makedirs(cfg_dir, exist_ok=True)
        with open(os.path.join(cfg_dir, "model-registry.json"), "w") as f:
            json.dump(fake_reg, f)
        with patch.object(boot, "WORKSPACE", self.tmp):
            summary = boot.compute_cost_summary(self.tmp)
        # File should now exist on disk with the same content.
        out_path = os.path.join(self.tmp, "cost-summary.json")
        self.assertTrue(os.path.exists(out_path))
        with open(out_path) as f:
            loaded = json.load(f)
        self.assertEqual(loaded["status"], "computed")
        self.assertEqual(len(loaded["per_model"]), 1)
        self.assertAlmostEqual(loaded["totals"]["total_cost_usd"], 0.002, places=6)


class RecordModelUsage(unittest.TestCase):
    """``_record_model_usage`` appends to usage.jsonl when the ContextVar
    is set, no-ops otherwise."""

    def test_no_trace_dir_is_noop(self):
        # ContextVar default is None — no exception, no file written.
        boot._TURN_TRACE_DIR_CV.set(None)
        # Should not raise.
        boot._record_model_usage(
            {"id": "test-endpoint", "service": "openai"},
            prompt_tokens=100, completion_tokens=50,
        )

    def test_writes_usage_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            boot._TURN_TRACE_DIR_CV.set(tmp)
            try:
                boot._record_model_usage(
                    {"id": "endp-A", "model_id": "qwen/qwen3.5-9b",
                     "service": "openrouter"},
                    prompt_tokens=200, completion_tokens=100,
                    total_tokens=300,
                )
            finally:
                boot._TURN_TRACE_DIR_CV.set(None)
            path = os.path.join(tmp, "usage.jsonl")
            self.assertTrue(os.path.exists(path))
            with open(path) as f:
                lines = [json.loads(l) for l in f if l.strip()]
            self.assertEqual(len(lines), 1)
            rec = lines[0]
            self.assertEqual(rec["endpoint_id"], "endp-A")
            self.assertEqual(rec["model_id"], "qwen/qwen3.5-9b")
            self.assertEqual(rec["service"], "openrouter")
            self.assertEqual(rec["prompt_tokens"], 200)
            self.assertEqual(rec["completion_tokens"], 100)
            self.assertEqual(rec["total_tokens"], 300)


if __name__ == "__main__":
    unittest.main()
