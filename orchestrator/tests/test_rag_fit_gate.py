"""Tests for the RAG relevance fit-gate (orchestrator/rag_fit_gate.py).

The gate annotates each retrieved candidate KEEP/DROP against the user's
request, before the provenance ranker. Core guarantees under test:
- verdict parsing is lenient and order-correct;
- missing/garbled lines default to KEEP (fail-open per item);
- a model error or "[Error ...]" string fails open (keep all);
- the batched prompt actually carries the request + candidate sources.
"""

from __future__ import annotations

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
if _ORCHESTRATOR not in sys.path:
    sys.path.insert(0, _ORCHESTRATOR)

import rag_fit_gate as fg  # noqa: E402


def _chunks():
    return [
        {"document": "Zen gardens use negative space and asymmetry to frame stillness.",
         "metadata": {"source": "garden.md"}},
        {"document": "Hubble's law interprets cosmic redshift as expansion of space.",
         "metadata": {"source": "cosmo.md"}},
    ]


class TestParseVerdicts(unittest.TestCase):

    def test_keep_drop_in_order(self):
        text = "1: KEEP - on topic\n2: DROP - cosmology not art"
        v = fg._parse_gate_verdicts(text, 2)
        self.assertEqual([x[0] for x in v], ["keep", "drop"])
        self.assertIn("cosmology", v[1][1])

    def test_missing_line_defaults_keep(self):
        v = fg._parse_gate_verdicts("2: DROP - x", 3)
        self.assertEqual([x[0] for x in v], ["keep", "drop", "keep"])

    def test_garbage_defaults_all_keep(self):
        v = fg._parse_gate_verdicts("here are my thoughts, nothing structured", 2)
        self.assertEqual([x[0] for x in v], ["keep", "keep"])

    def test_format_variants(self):
        # "1." separator, ")" separator, lowercase, em-dash reason separator
        text = "1. DROP - a\n2) keep — b"
        v = fg._parse_gate_verdicts(text, 2)
        self.assertEqual([x[0] for x in v], ["drop", "keep"])
        self.assertEqual(v[1][1], "b")

    def test_out_of_range_index_ignored(self):
        v = fg._parse_gate_verdicts("5: DROP - x", 2)
        self.assertEqual([x[0] for x in v], ["keep", "keep"])


class TestApplyFitGate(unittest.TestCase):

    def test_annotates_keep_and_drop(self):
        def call_fn(system, user):
            return "1: KEEP - garden aesthetics\n2: DROP - cosmology off-topic"
        out = fg.apply_fit_gate(_chunks(), "japanese garden empty space", call_fn=call_fn)
        self.assertEqual(out[0]["gate_verdict"], "keep")
        self.assertEqual(out[1]["gate_verdict"], "drop")
        self.assertIn("cosmology", out[1]["gate_reason"])

    def test_fail_open_on_exception(self):
        def call_fn(system, user):
            raise RuntimeError("model down")
        out = fg.apply_fit_gate(_chunks(), "q", call_fn=call_fn)
        self.assertTrue(all(c["gate_verdict"] == "keep" for c in out))
        self.assertIn("failopen", out[0]["gate_reason"])

    def test_fail_open_on_error_string(self):
        def call_fn(system, user):
            return "[Error] quota exceeded"
        out = fg.apply_fit_gate(_chunks(), "q", call_fn=call_fn)
        self.assertTrue(all(c["gate_verdict"] == "keep" for c in out))

    def test_empty_input_returns_empty(self):
        called = {"n": 0}
        def call_fn(system, user):
            called["n"] += 1
            return ""
        out = fg.apply_fit_gate([], "q", call_fn=call_fn)
        self.assertEqual(out, [])
        self.assertEqual(called["n"], 0)  # no model call on empty pool

    def test_prompt_carries_request_and_sources(self):
        captured = {}
        def call_fn(system, user):
            captured["system"] = system
            captured["user"] = user
            return "1: KEEP\n2: KEEP"
        fg.apply_fit_gate(_chunks(), "MY_UNIQUE_REQUEST_TOKEN", call_fn=call_fn)
        self.assertIn("MY_UNIQUE_REQUEST_TOKEN", captured["user"])
        self.assertIn("garden.md", captured["user"])
        self.assertIn("cosmo.md", captured["user"])
        self.assertIn("KEEP", captured["system"])  # instruction names the verdicts

    def test_make_fit_gate_returns_callable(self):
        def call_fn(system, user):
            return "1: DROP - off\n2: KEEP - on"
        gate = fg.make_fit_gate(call_fn)
        out = gate(_chunks(), "q")
        self.assertEqual([c["gate_verdict"] for c in out], ["drop", "keep"])


if __name__ == "__main__":
    unittest.main()
