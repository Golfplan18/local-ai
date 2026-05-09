"""Tests for orchestrator/provenance.py — Phase 5.1.

Contract from Reference — Ora YAML Schema §4 (rev 5, 2026-05-09):
    Eleven types in the vocabulary. Provenance weights and decay
    eligibility are derived from type, with provenance-modifier tags
    (`ai-derived`, `source-derived`) lowering effective weight per §6.5.

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
    """Each retained type maps to its expected weight per Schema §4 rev 5."""

    def test_engram_weight(self):
        self.assertEqual(provenance.TYPE_WEIGHTS["engram"], 1.0)

    def test_resource_weight(self):
        self.assertEqual(provenance.TYPE_WEIGHTS["resource"], 0.8)

    def test_chat_weight(self):
        self.assertEqual(provenance.TYPE_WEIGHTS["chat"], 0.6)

    def test_transcript_weight(self):
        self.assertEqual(provenance.TYPE_WEIGHTS["transcript"], 0.6)

    def test_web_weight(self):
        self.assertEqual(provenance.TYPE_WEIGHTS["web"], 0.1)

    def test_framework_not_retrieved(self):
        self.assertIsNone(provenance.TYPE_WEIGHTS["framework"])

    def test_mode_not_retrieved(self):
        self.assertIsNone(provenance.TYPE_WEIGHTS["mode"])

    def test_reference_not_retrieved(self):
        self.assertIsNone(provenance.TYPE_WEIGHTS["reference"])

    def test_working_not_retrieved(self):
        self.assertIsNone(provenance.TYPE_WEIGHTS["working"])

    def test_matrix_not_retrieved(self):
        self.assertIsNone(provenance.TYPE_WEIGHTS["matrix"])

    def test_supervision_not_retrieved(self):
        self.assertIsNone(provenance.TYPE_WEIGHTS["supervision"])

    def test_retired_types_absent(self):
        # rev 5: incubator and msi-research are retired entirely.
        self.assertNotIn("incubator", provenance.TYPE_WEIGHTS)
        self.assertNotIn("msi-research", provenance.TYPE_WEIGHTS)

    def test_vocabulary_size(self):
        # Schema §4 rev 5: eleven active values.
        self.assertEqual(len(provenance.TYPE_WEIGHTS), 11)


class TestProvenanceModifierTags(unittest.TestCase):
    """Provenance-modifier tags lower effective engram weight per §6.5."""

    def test_ai_derived_modifier(self):
        self.assertEqual(provenance.PROVENANCE_MODIFIER_TAGS["ai-derived"], 0.9)

    def test_source_derived_modifier(self):
        self.assertEqual(provenance.PROVENANCE_MODIFIER_TAGS["source-derived"], 0.9)

    def test_modifier_set_size(self):
        self.assertEqual(len(provenance.PROVENANCE_MODIFIER_TAGS), 2)


class TestWeightFor(unittest.TestCase):
    """weight_for(type, tags) is the public lookup used by the ranker."""

    def test_known_type_returns_weight(self):
        self.assertEqual(provenance.weight_for("engram"), 1.0)
        self.assertEqual(provenance.weight_for("chat"), 0.6)
        self.assertEqual(provenance.weight_for("transcript"), 0.6)
        self.assertEqual(provenance.weight_for("web"), 0.1)
        self.assertEqual(provenance.weight_for("resource"), 0.8)

    def test_engram_with_ai_derived_tag(self):
        # AHI grounding: AI-derived engrams are weighted below user-authored.
        self.assertEqual(provenance.weight_for("engram", ["ai-derived"]), 0.9)

    def test_engram_with_source_derived_tag(self):
        # External-author engrams are weighted at the same tier as AI-derived.
        self.assertEqual(provenance.weight_for("engram", ["source-derived"]), 0.9)

    def test_engram_with_both_modifier_tags(self):
        # Defensive: if both apply, the lower (or equal) wins.
        self.assertEqual(
            provenance.weight_for("engram", ["ai-derived", "source-derived"]),
            0.9,
        )

    def test_engram_with_unrelated_tags_unchanged(self):
        # Non-modifier tags don't affect weight.
        self.assertEqual(
            provenance.weight_for("engram", ["atomic", "epistemology"]),
            1.0,
        )

    def test_engram_with_empty_tags_unchanged(self):
        self.assertEqual(provenance.weight_for("engram", []), 1.0)
        self.assertEqual(provenance.weight_for("engram", None), 1.0)

    def test_modifier_tags_on_non_engram_apply(self):
        # The modifier is keyed on tag, not type — if a resource somehow
        # carries `ai-derived`, the modifier still applies (defensive).
        # Unlikely in practice but the invariant is: tag-aware weighting
        # is uniform.
        self.assertEqual(
            provenance.weight_for("resource", ["ai-derived"]),
            0.8,  # min(0.8, 0.9) — base wins because base is lower
        )

    def test_non_retrieved_type_returns_none(self):
        # Not-retrieved types return None regardless of tags.
        self.assertIsNone(provenance.weight_for("framework"))
        self.assertIsNone(provenance.weight_for("mode"))
        self.assertIsNone(provenance.weight_for("reference"))
        self.assertIsNone(provenance.weight_for("working"))
        self.assertIsNone(provenance.weight_for("matrix"))
        self.assertIsNone(provenance.weight_for("supervision"))

    def test_retired_types_return_none(self):
        # Retired in rev 5: incubator, msi-research.
        self.assertIsNone(provenance.weight_for("incubator"))
        self.assertIsNone(provenance.weight_for("msi-research"))

    def test_unknown_type_returns_none(self):
        self.assertIsNone(provenance.weight_for("unknown_type"))
        self.assertIsNone(provenance.weight_for(""))
        self.assertIsNone(provenance.weight_for("ENGRAM"))  # case-sensitive

    def test_none_input_returns_none(self):
        self.assertIsNone(provenance.weight_for(None))


class TestDecayEligibleTypes(unittest.TestCase):
    """Decay eligibility per Schema §4 rev 5 column "Decays?"."""

    def test_decay_eligible_set_contents(self):
        # Schema §4 rev 5: chat, transcript, web all decay.
        # Vetted retrieval-eligible types (engram, resource) do not.
        # Not-retrieved types are not in the set (they don't enter ranking).
        # incubator and msi-research are retired and not in the set.
        expected = {"chat", "transcript", "web"}
        self.assertEqual(provenance.DECAY_ELIGIBLE_TYPES, expected)

    def test_decay_set_size(self):
        self.assertEqual(len(provenance.DECAY_ELIGIBLE_TYPES), 3)

    def test_vetted_types_not_in_decay_set(self):
        for t in ("engram", "resource"):
            self.assertNotIn(t, provenance.DECAY_ELIGIBLE_TYPES)

    def test_not_retrieved_types_not_in_decay_set(self):
        for t in ("framework", "mode", "reference", "working",
                  "matrix", "supervision"):
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
        self.assertEqual(len(provenance.EXTERNAL_WEIGHTS), 4)


class TestOrdering(unittest.TestCase):
    """Provenance ordering invariants the ranker depends on (rev 5)."""

    def test_user_engram_outranks_ai_derived_engram(self):
        # AHI grounding: human-authored beats AI-authored at retrieval.
        self.assertGreater(
            provenance.weight_for("engram"),
            provenance.weight_for("engram", ["ai-derived"]),
        )

    def test_user_engram_outranks_source_derived_engram(self):
        # External-author engrams are subordinate to user-authored.
        self.assertGreater(
            provenance.weight_for("engram"),
            provenance.weight_for("engram", ["source-derived"]),
        )

    def test_engram_tagged_outranks_resource(self):
        # An AI-derived or source-derived engram still ranks above a
        # raw resource chunk — the distillation premium survives the
        # provenance discount.
        self.assertGreater(
            provenance.weight_for("engram", ["ai-derived"]),
            provenance.weight_for("resource"),
        )

    def test_resource_outranks_chat(self):
        self.assertGreater(
            provenance.weight_for("resource"),
            provenance.weight_for("chat"),
        )

    def test_chat_outranks_web(self):
        self.assertGreater(
            provenance.weight_for("chat"),
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
