"""Deterministic coverage for model-authored visual recovery."""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import visual_recovery as vr  # noqa: E402
from visual_validator import validate_envelope  # noqa: E402


class TestVisualRecovery(unittest.TestCase):
    def test_extracts_mermaid_fence_and_detects_dialect(self):
        body = "%% generated diagram\nsequenceDiagram\n  Alice->>Bob: Hello"
        fenced = f"```mermaid\n{body}\n```"

        self.assertEqual(
            vr.find_fenced_blocks(f"Before\n{fenced}\nAfter"),
            [("mermaid", body, fenced)],
        )
        self.assertEqual(vr.detect_mermaid_dialect(body), "sequence")

    def test_normalizes_multiline_dagitty(self):
        source = """dag {
  $treatment$ [exposure] # assigned treatment
  outcome [outcome]
  confounder -> treatment
  treatment -> outcome
}"""

        self.assertEqual(
            vr.normalize_dagitty(source),
            "dag { treatment [exposure] ; outcome [outcome] ; "
            "confounder -> treatment ; treatment -> outcome }",
        )

    def test_repairs_malformed_envelope_to_valid_shape(self):
        malformed = {
            "type": "causal_dag",
            "notes": "schema-forbidden envelope property",
            "spec": {
                "dsl": (
                    "dag {\n"
                    "  treatment [exposure]\n"
                    "  outcome [outcome]\n"
                    "  treatment -> outcome\n"
                    "}"
                ),
                "decorative_note": "schema-forbidden spec property",
            },
        }
        text = f"```ora-visual\n{json.dumps(malformed)}\n```"

        recovered = vr.recover_envelope(
            [text], ["causal_dag"], mode="causal-analysis"
        )

        self.assertIsNotNone(recovered)
        envelope = recovered["envelope"]
        self.assertEqual(recovered["via"], "model_envelope")
        self.assertNotIn("notes", envelope)
        self.assertNotIn("decorative_note", envelope["spec"])
        self.assertEqual(envelope["spec"]["focal_exposure"], "treatment")
        self.assertEqual(envelope["spec"]["focal_outcome"], "outcome")
        self.assertTrue(validate_envelope(envelope).valid)

    def test_splice_preserves_surrounding_prose(self):
        import boot

        opening = "Opening analysis stays here."
        closing = "Closing recommendation stays here."
        response = (
            f"{opening}\n\n"
            "```mermaid\n"
            "flowchart TD\n"
            "  A[Observe] --> B[Explain]\n"
            "```\n\n"
            f"{closing}"
        )

        with mock.patch.object(boot, "PIPELINE_TRACE_AVAILABLE", False):
            spliced, diagnostics = boot._maybe_recover_visual(
                response,
                {"visual_kind": "flowchart"},
                mode=None,
            )

        self.assertIsNotNone(spliced)
        self.assertTrue(spliced.startswith(f"{opening}\n\n```ora-visual\n"))
        self.assertTrue(spliced.endswith(f"```\n\n{closing}"))
        self.assertNotIn("```mermaid", spliced)
        self.assertTrue(diagnostics["recovered"])

    def test_unrecoverable_cycle_returns_none(self):
        cyclic_dag = """```dagitty
dag {
  x [exposure]
  y [outcome]
  x -> y
  y -> x
}
```"""

        self.assertIsNone(
            vr.recover_envelope(
                [cyclic_dag], ["causal_dag"], mode="causal-analysis"
            )
        )


if __name__ == "__main__":
    unittest.main()
