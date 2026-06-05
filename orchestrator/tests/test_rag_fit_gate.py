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
import rag_engine  # noqa: E402


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


class TestCosmologyRegression(unittest.TestCase):
    """End-to-end funnel regression for the original failure: a cosmology
    chunk must not survive a Japanese-garden art query. A content-based stub
    gate stands in for the model (the live-model check is the optional class
    below), so the funnel behaviour is locked without a live model."""

    def _scenario(self):
        return [
            {"document": ("Buddhist sunyata emptiness parallels the cosmological "
                          "insight; Hubble's law and cosmic redshift describe expansion."),
             "similarity": 0.71, "metadata": {"type": "engram", "source": "cosmo.md"}},
            {"document": ("The Japanese tea garden uses ma negative space and "
                          "yohaku-no-bi to frame stillness."),
             "similarity": 0.60, "metadata": {"type": "engram", "source": "garden.md"}},
        ]

    def test_cosmology_dropped_garden_kept(self):
        def call_fn(system, user):  # a correct model's verdicts for this scenario
            return "1: DROP - cosmology not garden\n2: KEEP - garden composition"
        gate = fg.make_fit_gate(call_fn)
        chunks = gate(self._scenario(),
                      "Ma reading of a Japanese garden — what is the empty space doing?")
        ranked = rag_engine.rank_vault_chunks(chunks, similarity_floor=0.40)
        sources = [c["metadata"]["source"] for c in ranked]
        # The contaminant is gone and the on-topic chunk survives — even though
        # the cosmology chunk had the HIGHER similarity (0.71 vs 0.60).
        self.assertNotIn("cosmo.md", sources)
        self.assertIn("garden.md", sources)


@unittest.skipUnless(os.environ.get("ORA_RAG_GATE_LIVE_TEST") == "1",
                     "set ORA_RAG_GATE_LIVE_TEST=1 to run the live-model gate check")
class TestLiveModelGate(unittest.TestCase):
    """Optional: validates that the real configured gate model actually drops
    the cosmology engram on the art query. Skipped by default (needs a live
    model endpoint + credentials)."""

    def test_real_model_drops_cosmology_keeps_garden(self):
        from orchestrator.model_dispatch import invoke_chat
        def call_fn(system, user):
            return invoke_chat(system, user, slot="classification", context="interactive")
        chunks = [
            {"document": ("Buddhist sunyata emptiness parallels the cosmological insight "
                          "that observations depend on information propagation through "
                          "space-time; Hubble's law and redshift."),
             "metadata": {"source": "cosmo.md"}},
            {"document": ("The Japanese tea garden uses ma (negative space) and "
                          "yohaku-no-bi to frame stillness."),
             "metadata": {"source": "garden.md"}},
        ]
        out = fg.apply_fit_gate(
            chunks, "Ma reading of a Japanese garden — what is the empty space doing?",
            call_fn=call_fn)
        verdicts = {c["metadata"]["source"]: c["gate_verdict"] for c in out}
        self.assertEqual(verdicts["cosmo.md"], "drop")
        self.assertEqual(verdicts["garden.md"], "keep")


if __name__ == "__main__":
    unittest.main()
