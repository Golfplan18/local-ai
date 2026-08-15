"""Reviser non-draft gate + trace self-detection tests.

Added 2026-06-01 (MSI gear-4 cascade-fix handoff #1 + #5).

#1 — A Step-5 reviser that narrates verification ("Now I'll run web
verification queries… the draft stands as previously emitted") with no
``## REVISED DRAFT`` section used to sail past ``_step_output_health``
(long enough, not a refusal idiom) and was written ``ok=True``, passing
an empty result downstream. The fix routes the existing
``_reviser_output_structural_check`` into ``_step_output_health`` for
``step_name == "reviser"`` so the existing retry-once-then-degrade path
in ``_call_with_retry`` fires. These tests pin:
  - the structural check classifies a stub vs a real envelope,
  - the health check gates a non-draft reviser output as unhealthy,
  - the gate is reviser-only (analyst / evaluator / verifier are not
    forced to carry a ``## REVISED DRAFT`` header),
  - the degraded-reviser fallback envelope itself passes the gate.

#5 — ``_record_model_usage`` now records ``finish_reason`` and falls
back to ``_CURRENT_STEP_CV`` for ``step_hint`` so usage.jsonl is
self-detecting (truncation + per-step joinability).
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock


HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKTREE_ROOT = os.path.dirname(HERE)
for p in (HERE, WORKTREE_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)



import boot


# A real reviser output carries the 8-section mirror contract; only the
# load-bearing ``## REVISED DRAFT`` body matters to the structural gate.
_REAL_REVISER_ENVELOPE = (
    "## ADDRESSED\nNone.\n\n"
    "## NOT ADDRESSED\nNone.\n\n"
    "## INCORPORATED\nNone.\n\n"
    "## DECLINED\nNone.\n\n"
    "## CLAIM RESOLUTIONS\nNone.\n\n"
    "## REMAINING UNCERTAINTIES\nNone.\n\n"
    "## REVISED DRAFT\n"
    + ("The committed analysis, re-emitted in full. " * 12)
    + "\n\n## CHANGELOG\nNo substantive changes; see NOT ADDRESSED.\n"
)

# The exact failure shape observed on the MSI voice path (prudence /
# ashley step5-revised-depth): verification narration, no draft.
_NARRATION_STUB = (
    "Now I'll run web verification queries for all three flagged claims "
    "before proceeding with the revision.\n\n"
    "**Query 1:** Volcker goal independence vs instrument independence\n"
    "**Query 2:** FOMC Statement Longer-Run Goals revised\n"
    "The revised draft stands as previously emitted."
)


class ReviserStructuralCheck(unittest.TestCase):
    def test_real_envelope_passes(self):
        ok, reason = boot._reviser_output_structural_check(_REAL_REVISER_ENVELOPE)
        self.assertTrue(ok, reason)

    def test_narration_stub_fails_missing_draft(self):
        ok, reason = boot._reviser_output_structural_check(_NARRATION_STUB)
        self.assertFalse(ok)
        self.assertIn("REVISED DRAFT", reason)

    def test_empty_fails(self):
        ok, _ = boot._reviser_output_structural_check("")
        self.assertFalse(ok)

    def test_header_present_but_body_empty_fails(self):
        ok, reason = boot._reviser_output_structural_check(
            "## ADDRESSED\nNone.\n\n" + ("x" * 200) + "\n\n## REVISED DRAFT\n\n## CHANGELOG\nx\n"
        )
        self.assertFalse(ok)


class ReviserHealthGate(unittest.TestCase):
    def test_health_gates_narration_stub_as_reviser(self):
        ok, reason = boot._step_output_health(_NARRATION_STUB, "reviser", min_chars=30)
        self.assertFalse(ok)
        # Reason is phrased as a directive folded into the regenerate hint.
        self.assertIn("REVISED DRAFT", reason)

    def test_health_passes_real_reviser_envelope(self):
        ok, _ = boot._step_output_health(_REAL_REVISER_ENVELOPE, "reviser", min_chars=30)
        self.assertTrue(ok)

    def test_gate_is_reviser_only(self):
        # The same narration text must NOT be gated for non-reviser steps —
        # only the reviser is required to carry a ## REVISED DRAFT header.
        for step in ("analyst", "evaluator", "consolidator"):
            ok, _ = boot._step_output_health(_NARRATION_STUB, step, min_chars=30)
            self.assertTrue(ok, f"{step} should not require ## REVISED DRAFT")

    def test_degraded_fallback_envelope_passes_gate(self):
        # The Step-5 contingency wraps the analyst output in a synthetic
        # reviser envelope; that envelope must itself satisfy the gate so
        # it is not re-degraded downstream.
        wrapped = boot._wrap_analyst_as_degraded_reviser_envelope(
            "A full in-voice analyst column. " * 20, stream_label="depth",
        )
        ok, _ = boot._step_output_health(wrapped, "reviser", min_chars=30)
        self.assertTrue(ok)


class UsageSelfDetection(unittest.TestCase):
    def test_finish_reason_and_step_hint_recorded(self):
        with tempfile.TemporaryDirectory() as root:
            d = os.path.join(root, "usage-dialogue", "turn")
            os.makedirs(d)
            tok_dir = boot.set_turn_trace_context(d)
            tok_step = boot._CURRENT_STEP_CV.set("reviser")
            try:
                with mock.patch.object(boot.pipeline_trace, "TRACE_ROOT", root):
                    boot._record_model_usage(
                        {"id": "ep-x", "model": "vendor/model",
                         "service": "openrouter"},
                        prompt_tokens=100, completion_tokens=200,
                        finish_reason="length",
                    )
            finally:
                boot._CURRENT_STEP_CV.reset(tok_step)
                boot.reset_turn_trace_context(tok_dir)
            with open(os.path.join(d, "usage.jsonl")) as fh:
                rec = json.loads(fh.read().strip())
        self.assertEqual(rec["step_hint"], "reviser")   # CV fallback
        self.assertEqual(rec["finish_reason"], "length")
        self.assertEqual(rec["completion_tokens"], 200)

    def test_explicit_step_hint_overrides_cv(self):
        with tempfile.TemporaryDirectory() as root:
            d = os.path.join(root, "usage-dialogue", "turn")
            os.makedirs(d)
            tok_dir = boot.set_turn_trace_context(d)
            tok_step = boot._CURRENT_STEP_CV.set("reviser")
            try:
                with mock.patch.object(boot.pipeline_trace, "TRACE_ROOT", root):
                    boot._record_model_usage(
                        {"id": "ep-x", "model": "vendor/model",
                         "service": "openai"},
                        prompt_tokens=1, completion_tokens=2,
                        step_hint="verifier", finish_reason="stop",
                    )
            finally:
                boot._CURRENT_STEP_CV.reset(tok_step)
                boot.reset_turn_trace_context(tok_dir)
            with open(os.path.join(d, "usage.jsonl")) as fh:
                rec = json.loads(fh.read().strip())
        self.assertEqual(rec["step_hint"], "verifier")


if __name__ == "__main__":
    unittest.main()
