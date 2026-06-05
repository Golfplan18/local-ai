"""Tests for orchestrator/provenance.py — Phase 5.1.

Contract from Reference — Ora YAML Schema §4 (rev 5.2, 2026-06-05):
    Eleven types in the vocabulary. Provenance weights and decay eligibility
    are derived from type. The engram authorship caps (`ai-derived`,
    `source-derived`) were retired 2026-06-05 — trust follows whether the user
    kept the claim, not which side typed it. `superseded` (resources) remains a
    weight modifier per §6.5.

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
    """The engram authorship caps (`ai-derived`, `source-derived`) were retired
    2026-06-05 — trust follows review-status, not authorship side."""

    def test_ai_derived_retired(self):
        self.assertNotIn("ai-derived", provenance.PROVENANCE_MODIFIER_TAGS)

    def test_source_derived_retired(self):
        self.assertNotIn("source-derived", provenance.PROVENANCE_MODIFIER_TAGS)

    def test_modifier_set_empty(self):
        self.assertEqual(len(provenance.PROVENANCE_MODIFIER_TAGS), 0)


class TestWeightFor(unittest.TestCase):
    """weight_for(type, tags) is the public lookup used by the ranker."""

    def test_known_type_returns_weight(self):
        self.assertEqual(provenance.weight_for("engram"), 1.0)
        self.assertEqual(provenance.weight_for("chat"), 0.6)
        self.assertEqual(provenance.weight_for("transcript"), 0.6)
        self.assertEqual(provenance.weight_for("web"), 0.1)
        self.assertEqual(provenance.weight_for("resource"), 0.8)

    def test_engram_with_ai_derived_tag(self):
        # Cap retired 2026-06-05: a kept engram is adopted thinking regardless
        # of authorship side. AI-side engrams now weigh the same as user-side.
        self.assertEqual(provenance.weight_for("engram", ["ai-derived"]), 1.0)

    def test_engram_with_source_derived_tag(self):
        self.assertEqual(provenance.weight_for("engram", ["source-derived"]), 1.0)

    def test_engram_authorship_tags_no_longer_modify(self):
        # The former caps are inert tags now.
        self.assertEqual(
            provenance.weight_for("engram", ["ai-derived", "source-derived"]),
            1.0,
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

    def test_retired_authorship_tags_are_inert(self):
        # `ai-derived` no longer modifies weight anywhere — a resource (or any
        # type) carrying it keeps its base weight.
        self.assertEqual(provenance.weight_for("resource", ["ai-derived"]), 0.8)
        self.assertEqual(provenance.weight_for("engram", ["ai-derived"]), 1.0)

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
        # Merged into the resource tier 2026-06-05: a cleared site is curated
        # reference, so a trusted-web hit weighs the same as a saved resource.
        self.assertEqual(provenance.EXTERNAL_WEIGHTS["whitelisted"], 0.8)

    def test_whitelisted_matches_resource_tier(self):
        self.assertEqual(provenance.EXTERNAL_WEIGHTS["whitelisted"],
                         provenance.TYPE_WEIGHTS["resource"])

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

    def test_ai_side_engram_equals_user_side(self):
        # 2026-06-05: the authorship gap was retired. A kept engram weighs 1.0
        # whether its words originated with the user or the AI.
        self.assertEqual(
            provenance.weight_for("engram"),
            provenance.weight_for("engram", ["ai-derived"]),
        )
        self.assertEqual(
            provenance.weight_for("engram"),
            provenance.weight_for("engram", ["source-derived"]),
        )

    def test_engram_outranks_resource(self):
        # Engrams (the user's kept thinking) rank above curated resources.
        self.assertGreater(
            provenance.weight_for("engram"),
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


class TestSupersededTag(unittest.TestCase):
    """Schema rev 5.1 — `superseded` temporal-state tag for resources.

    Weight modifier on `resource` chunks reducing P2 (0.8) to 0.6
    (matching the chat tier). Preserves history at retrieval — does NOT
    filter the chunk out. Distinct from `archived` mechanic which
    excludes from default retrieval entirely.
    """

    def test_superseded_tag_in_temporal_state_dict(self):
        self.assertIn("superseded", provenance.TEMPORAL_STATE_TAGS)
        self.assertEqual(provenance.TEMPORAL_STATE_TAGS["superseded"], 0.6)

    def test_resource_with_superseded_drops_to_0_6(self):
        # Resource base weight is 0.8; superseded reduces to 0.6.
        self.assertEqual(
            provenance.weight_for("resource", tags=["superseded"]),
            0.6,
        )

    def test_resource_without_superseded_keeps_0_8(self):
        # No tag → base resource weight unchanged.
        self.assertEqual(provenance.weight_for("resource"), 0.8)
        self.assertEqual(provenance.weight_for("resource", tags=[]), 0.8)
        self.assertEqual(
            provenance.weight_for("resource", tags=["news"]),
            0.8,
        )

    def test_superseded_matches_chat_tier(self):
        # Per design choice (2026-05-10): superseded resources land at
        # the same retrieval tier as chat/transcript (0.6).
        self.assertEqual(
            provenance.weight_for("resource", tags=["superseded"]),
            provenance.weight_for("chat"),
        )

    def test_superseded_is_modifier_not_filter(self):
        # Critical AHI distinction: `superseded` does NOT remove the
        # chunk from retrieval (that would be `archived` behavior).
        # weight_for must return a non-None float.
        weight = provenance.weight_for("resource", tags=["superseded"])
        self.assertIsNotNone(weight)
        self.assertGreater(weight, 0.0)

    def test_archived_and_superseded_are_separate_concepts(self):
        # `archived` is a filter (handled in knowledge_search, not here);
        # `superseded` is a weight modifier (handled here).
        # weight_for treats `archived` as an unknown modifier tag (it's
        # not in PROVENANCE_MODIFIER_TAGS or TEMPORAL_STATE_TAGS).
        self.assertNotIn("archived", provenance.TEMPORAL_STATE_TAGS)
        self.assertNotIn("archived", provenance.PROVENANCE_MODIFIER_TAGS)
        # A resource with the archived tag returns its base weight from
        # weight_for; the filter mechanic happens elsewhere.
        self.assertEqual(
            provenance.weight_for("resource", tags=["archived"]),
            0.8,
        )

    def test_superseded_with_inert_authorship_tag(self):
        # `superseded` (0.6) still modifies; `ai-derived` is now inert, so a
        # resource with both lands at 0.6 (superseded alone).
        self.assertEqual(
            provenance.weight_for(
                "resource",
                tags=["superseded", "ai-derived"],
            ),
            0.6,
        )


class TestTemporalStateTagsExport(unittest.TestCase):
    """The new TEMPORAL_STATE_TAGS dict is exported alongside
    PROVENANCE_MODIFIER_TAGS for external consumers (resolver scripts,
    indexer, etc.)."""

    def test_temporal_state_tags_exported(self):
        self.assertIn("TEMPORAL_STATE_TAGS", provenance.__all__)

    def test_provenance_modifier_tags_still_exported(self):
        # Don't break existing consumers.
        self.assertIn("PROVENANCE_MODIFIER_TAGS", provenance.__all__)


if __name__ == "__main__":
    unittest.main()
