"""Tests for orchestrator/provenance.py — Phase 5.1.

Contract from Reference — Ora YAML Schema §4 (rev 3, 2026-04-30):
    Twelve types in the vocabulary. Provenance weights and decay eligibility
    are derived from type, not stored separately.

Contract from Reference — Ora YAML Schema §5:
    External tier (live web fetches) classified as one of four values, each
    carrying a fixed weight.

This module is the single source of truth for the type→weight mapping
consumed by the RAG ranker (Phase 5.6).
"""

from __future__ import annotations

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
if _ORCHESTRATOR not in sys.path:
    sys.path.insert(0, _ORCHESTRATOR)

import provenance  # noqa: E402


class TestTypeWeights(unittest.TestCase):
    """Each of the twelve types maps to its expected weight per Schema §4."""

    def test_engram_weight(self):
        self.assertEqual(provenance.TYPE_WEIGHTS["engram"], 1.0)

    def test_framework_weight(self):
        self.assertEqual(provenance.TYPE_WEIGHTS["framework"], 1.0)

    def test_mode_weight(self):
        self.assertEqual(provenance.TYPE_WEIGHTS["mode"], 1.0)

    def test_reference_weight(self):
        self.assertEqual(provenance.TYPE_WEIGHTS["reference"], 1.0)

    def test_resource_weight(self):
        self.assertEqual(provenance.TYPE_WEIGHTS["resource"], 0.7)

    def test_incubator_weight(self):
        self.assertEqual(provenance.TYPE_WEIGHTS["incubator"], 0.4)

    def test_chat_weight(self):
        self.assertEqual(provenance.TYPE_WEIGHTS["chat"], 0.3)

    def test_transcript_weight(self):
        self.assertEqual(provenance.TYPE_WEIGHTS["transcript"], 0.3)

    def test_working_weight(self):
        self.assertEqual(provenance.TYPE_WEIGHTS["working"], 0.2)

    def test_web_weight(self):
        self.assertEqual(provenance.TYPE_WEIGHTS["web"], 0.1)

    def test_matrix_not_retrieved(self):
        # Schema §4: matrix is "n/a — not retrieved as content"
        self.assertIsNone(provenance.TYPE_WEIGHTS["matrix"])

    def test_supervision_not_retrieved(self):
        # Schema §4: supervision is "n/a — not retrieved as content"
        self.assertIsNone(provenance.TYPE_WEIGHTS["supervision"])

    def test_vocabulary_size(self):
        # Schema §4 (rev 3): twelve active values, mutually exclusive.
        self.assertEqual(len(provenance.TYPE_WEIGHTS), 12)


class TestWeightFor(unittest.TestCase):
    """weight_for(chunk_type) is the public lookup used by the ranker."""

    def test_known_type_returns_weight(self):
        self.assertEqual(provenance.weight_for("engram"), 1.0)
        self.assertEqual(provenance.weight_for("chat"), 0.3)
        self.assertEqual(provenance.weight_for("transcript"), 0.3)
        self.assertEqual(provenance.weight_for("web"), 0.1)

    def test_non_retrieved_type_returns_none(self):
        # matrix and supervision are vocabulary-valid but not retrieved.
        # weight_for returns None so the ranker can skip them cleanly.
        self.assertIsNone(provenance.weight_for("matrix"))
        self.assertIsNone(provenance.weight_for("supervision"))

    def test_unknown_type_returns_none(self):
        # Unknown types fall through to None — the ranker treats this the
        # same as matrix/supervision (drop the chunk, don't crash).
        self.assertIsNone(provenance.weight_for("unknown_type"))
        self.assertIsNone(provenance.weight_for(""))
        self.assertIsNone(provenance.weight_for("ENGRAM"))  # case-sensitive

    def test_none_input_returns_none(self):
        # Defensive: a chunk with no type field shouldn't blow up the ranker.
        self.assertIsNone(provenance.weight_for(None))


class TestDecayEligibleTypes(unittest.TestCase):
    """Decay eligibility per Schema §4 column "Decays?"."""

    def test_decay_eligible_set_contents(self):
        # Schema §4: incubator, chat, transcript, working, web all decay.
        # Vetted types (engram, framework, mode, reference, resource) do not.
        # matrix, supervision are n/a and not in the set.
        expected = {"incubator", "chat", "transcript", "working", "web"}
        self.assertEqual(provenance.DECAY_ELIGIBLE_TYPES, expected)

    def test_decay_set_size(self):
        self.assertEqual(len(provenance.DECAY_ELIGIBLE_TYPES), 5)

    def test_vetted_types_not_in_decay_set(self):
        for t in ("engram", "framework", "mode", "reference", "resource"):
            self.assertNotIn(t, provenance.DECAY_ELIGIBLE_TYPES)

    def test_navigation_types_not_in_decay_set(self):
        for t in ("matrix", "supervision"):
            self.assertNotIn(t, provenance.DECAY_ELIGIBLE_TYPES)


class TestExternalWeights(unittest.TestCase):
    """External-tier classifications per Schema §5 (live web fetches)."""

    def test_whitelisted_weight(self):
        self.assertEqual(provenance.EXTERNAL_WEIGHTS["whitelisted"], 0.7)

    def test_corroborated_weight(self):
        self.assertEqual(provenance.EXTERNAL_WEIGHTS["corroborated"], 0.3)

    def test_single_weight(self):
        self.assertEqual(provenance.EXTERNAL_WEIGHTS["single"], 0.15)

    def test_excluded_weight(self):
        self.assertEqual(provenance.EXTERNAL_WEIGHTS["excluded"], 0.0)

    def test_external_classifications_size(self):
        # Schema §5: exactly four external classifications.
        self.assertEqual(len(provenance.EXTERNAL_WEIGHTS), 4)


class TestOrdering(unittest.TestCase):
    """Provenance ordering invariants the ranker depends on."""

    def test_engram_outranks_resource(self):
        self.assertGreater(
            provenance.weight_for("engram"),
            provenance.weight_for("resource"),
        )

    def test_resource_outranks_incubator(self):
        self.assertGreater(
            provenance.weight_for("resource"),
            provenance.weight_for("incubator"),
        )

    def test_incubator_outranks_chat(self):
        self.assertGreater(
            provenance.weight_for("incubator"),
            provenance.weight_for("chat"),
        )

    def test_chat_outranks_working(self):
        self.assertGreater(
            provenance.weight_for("chat"),
            provenance.weight_for("working"),
        )

    def test_working_outranks_web(self):
        self.assertGreater(
            provenance.weight_for("working"),
            provenance.weight_for("web"),
        )

    def test_chat_and_transcript_share_weight(self):
        # Schema §4: transcript is "Decays like chat" with the same weight.
        self.assertEqual(
            provenance.weight_for("chat"),
            provenance.weight_for("transcript"),
        )

    def test_whitelisted_external_outranks_corroborated(self):
        self.assertGreater(
            provenance.EXTERNAL_WEIGHTS["whitelisted"],
            provenance.EXTERNAL_WEIGHTS["corroborated"],
        )

    def test_corroborated_outranks_single(self):
        self.assertGreater(
            provenance.EXTERNAL_WEIGHTS["corroborated"],
            provenance.EXTERNAL_WEIGHTS["single"],
        )

    def test_excluded_is_floor(self):
        self.assertEqual(provenance.EXTERNAL_WEIGHTS["excluded"], 0.0)


if __name__ == "__main__":
    unittest.main()
