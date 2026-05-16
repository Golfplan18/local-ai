#!/usr/bin/env python3
"""Tests for article_data_viz.py — Phase 3 article-classifier."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))
sys.path.insert(0, str(ORCHESTRATOR / "integrations"))

import article_data_viz as adv  # noqa: E402
from article_data_viz import (  # noqa: E402
    ArticleVizAnalysis,
    ArticleVizResult,
    INDICATOR_CATALOG,
    VizOpportunity,
    _build_classifier_prompt,
    _diagnostic_phrases,
    _expand_article_topics,
    _name_match_score,
    _parse_classifier_response,
    _topic_overlap_score,
    analyze_article_for_data_viz,
    analyze_article_via_ranking,
    extract_article_summary,
    parse_article_file,
    rank_indicators_for_article,
    render_figures_for_article,
)
from data_viz_render import FigureResult  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ECONOMIC_ARTICLE = {
    "headline": "May jobs report shows U-3 unchanged at 4.1% as participation slips",
    "lede": (
        "The Labor Department reported on Friday that the U.S. unemployment "
        "rate held at 4.1% in May for the third consecutive month, while the "
        "labor force participation rate fell 0.2 percentage points to 62.4%. "
        "Nonfarm payrolls grew by 138,000, below economist consensus of 175,000."
    ),
    "nut_graf": (
        "The combination of stable headline unemployment and declining "
        "participation suggests the labor market is softening in ways the "
        "U-3 rate alone obscures. Wage growth, as measured by the Atlanta "
        "Fed's Wage Growth Tracker, slowed to 4.2% year-over-year."
    ),
    "atomic_claims": [
        {"text": "U-3 unemployment rate held at 4.1% in May 2026"},
        {"text": "Labor force participation rate fell 0.2pp to 62.4%"},
        {"text": "Nonfarm payrolls added 138,000 jobs in May"},
        {"text": "Atlanta Fed Wage Growth Tracker slowed to 4.2% YoY"},
    ],
}

GEOPOLITICAL_ARTICLE = {
    "headline": "Iran response to U.S. proposal rejected as war reaches day 72",
    "lede": (
        "Iran transmitted its response to a U.S. 14-point proposal to end the "
        "U.S.–Israel war on Iran via Pakistani mediation channels on Saturday, "
        "and U.S. President Donald Trump rejected the response."
    ),
    "atomic_claims": [
        {"text": "Iran transmitted response via Pakistani mediation channels"},
        {"text": "Trump rejected the response as 'totally unacceptable'"},
        {"text": "Iran's parliament speaker said ceasefire requires lifting blockade"},
    ],
}


# ---------------------------------------------------------------------------
# Article extraction
# ---------------------------------------------------------------------------

class TestExtractArticleSummary(unittest.TestCase):

    def test_includes_headline_lede_nutgraf_claims(self):
        s = extract_article_summary(ECONOMIC_ARTICLE)
        self.assertIn("Headline:", s)
        self.assertIn("Lede:", s)
        self.assertIn("Nut graf:", s)
        self.assertIn("Key claims", s)
        self.assertIn("U-3 unemployment rate", s)

    def test_handles_missing_fields(self):
        article = {"headline": "Test"}  # only headline
        s = extract_article_summary(article)
        self.assertIn("Test", s)
        # Should not crash on missing lede / claims

    def test_caps_claim_count(self):
        many_claims = {
            "headline": "x",
            "atomic_claims": [{"text": f"claim {i}"} for i in range(20)],
        }
        s = extract_article_summary(many_claims, max_claims=3)
        self.assertIn("claim 0", s)
        self.assertIn("claim 2", s)
        self.assertNotIn("claim 5", s)
        self.assertNotIn("claim 10", s)

    def test_trims_long_lede(self):
        long_lede = "x" * 2000
        article = {"headline": "h", "lede": long_lede}
        s = extract_article_summary(article)
        # Lede should be truncated; total summary should be reasonable
        self.assertLess(len(s), 1500)


# ---------------------------------------------------------------------------
# Article file parsing
# ---------------------------------------------------------------------------

class TestParseArticleFile(unittest.TestCase):

    def test_parses_yaml_frontmatter(self):
        content = """---
headline: Test Article
lede: Test lede goes here.
publish_date: 2026-05-13
---

# Article body content
"""
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(content)
            path = f.name

        try:
            data = parse_article_file(path)
            self.assertEqual(data["headline"], "Test Article")
            self.assertEqual(data["lede"], "Test lede goes here.")
        finally:
            os.unlink(path)

    def test_returns_empty_on_no_frontmatter(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write("# Just a heading, no YAML\n")
            path = f.name
        try:
            data = parse_article_file(path)
            self.assertEqual(data.get("headline", ""), "")
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

class TestBuildClassifierPrompt(unittest.TestCase):

    def test_returns_two_messages(self):
        msgs = _build_classifier_prompt("test summary")
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["role"], "system")
        self.assertEqual(msgs[1]["role"], "user")

    def test_system_includes_catalog(self):
        msgs = _build_classifier_prompt("x")
        system = msgs[0]["content"]
        # Catalog should appear in system prompt
        for entry in INDICATOR_CATALOG[:3]:
            self.assertIn(entry["series_id"], system)

    def test_system_includes_guardrail(self):
        msgs = _build_classifier_prompt("x")
        system = msgs[0]["content"]
        self.assertIn("meaningless data serves no one", system.lower())

    def test_user_contains_article_summary(self):
        msgs = _build_classifier_prompt("MY_ARTICLE_TEXT")
        user = msgs[1]["content"]
        self.assertIn("MY_ARTICLE_TEXT", user)


# ---------------------------------------------------------------------------
# Classifier response parsing
# ---------------------------------------------------------------------------

class TestParseClassifierResponse(unittest.TestCase):

    def test_parses_clean_json(self):
        raw = json.dumps({
            "warrants_charts": True,
            "opportunities": [
                {"series_id": "UNRATE", "transformation": "raw",
                 "narrative_role": "anchors",
                 "justification": "anchors the unemployment claim",
                 "priority": 1},
                {"series_id": "PAYEMS", "transformation": "first_diff",
                 "narrative_role": "quantifies",
                 "justification": "quantifies monthly job change",
                 "priority": 2},
            ],
        })
        analysis = _parse_classifier_response(raw)
        self.assertTrue(analysis.warrants_charts)
        self.assertEqual(len(analysis.opportunities), 2)
        self.assertEqual(analysis.opportunities[0].series_id, "UNRATE")
        self.assertEqual(analysis.opportunities[0].priority, 1)

    def test_strips_code_fences(self):
        raw = '```json\n{"warrants_charts": false, "opportunities": []}\n```'
        analysis = _parse_classifier_response(raw)
        self.assertFalse(analysis.warrants_charts)

    def test_drops_unknown_series(self):
        raw = json.dumps({
            "warrants_charts": True,
            "opportunities": [
                {"series_id": "UNRATE", "transformation": "raw",
                 "narrative_role": "anchors", "justification": "ok", "priority": 1},
                {"series_id": "MADEUP_SERIES", "transformation": "raw",
                 "narrative_role": "anchors", "justification": "x", "priority": 2},
            ],
        })
        analysis = _parse_classifier_response(raw)
        self.assertEqual(len(analysis.opportunities), 1)
        self.assertEqual(analysis.opportunities[0].series_id, "UNRATE")

    def test_caps_at_4_opportunities(self):
        raw = json.dumps({
            "warrants_charts": True,
            "opportunities": [
                {"series_id": e["series_id"], "transformation": "raw",
                 "narrative_role": "anchors", "justification": "x",
                 "priority": i + 1}
                for i, e in enumerate(INDICATOR_CATALOG[:6])
            ],
        })
        analysis = _parse_classifier_response(raw)
        self.assertLessEqual(len(analysis.opportunities), 4)

    def test_invalid_json_returns_error(self):
        analysis = _parse_classifier_response("not json")
        self.assertFalse(analysis.warrants_charts)
        self.assertIn("No JSON", analysis.error)

    def test_warrants_false_with_empty_opportunities(self):
        raw = json.dumps({"warrants_charts": True, "opportunities": []})
        analysis = _parse_classifier_response(raw)
        # Empty opportunities → not warranting (defensive)
        self.assertFalse(analysis.warrants_charts)

    def test_invalid_transformation_falls_back_to_raw(self):
        raw = json.dumps({
            "warrants_charts": True,
            "opportunities": [
                {"series_id": "UNRATE", "transformation": "weird_xform",
                 "narrative_role": "anchors", "justification": "x", "priority": 1}
            ],
        })
        analysis = _parse_classifier_response(raw)
        self.assertEqual(analysis.opportunities[0].transformation, "raw")


# ---------------------------------------------------------------------------
# analyze_article_for_data_viz (mocked classifier)
# ---------------------------------------------------------------------------

class TestAnalyzeArticle(unittest.TestCase):

    def test_no_call_fn_returns_error(self):
        # classifier mode without call_fn → error
        analysis = analyze_article_for_data_viz(
            ECONOMIC_ARTICLE, call_fn=None, mode="classifier",
        )
        self.assertFalse(analysis.warrants_charts)
        self.assertIn("call_fn", analysis.error)

    def test_economic_article_with_classifier(self):
        fake_response = json.dumps({
            "warrants_charts": True,
            "opportunities": [
                {"series_id": "UNRATE", "transformation": "raw",
                 "narrative_role": "anchors",
                 "justification": "anchors the headline U-3 claim", "priority": 1},
                {"series_id": "CIVPART", "transformation": "raw",
                 "narrative_role": "contextualizes",
                 "justification": "shows the participation drop", "priority": 2},
            ],
        })
        fake_call = mock.MagicMock(return_value=fake_response)
        analysis = analyze_article_for_data_viz(
            ECONOMIC_ARTICLE, call_fn=fake_call, mode="classifier",
        )
        self.assertTrue(analysis.warrants_charts)
        self.assertEqual(len(analysis.opportunities), 2)
        # Verify call_fn was called with expected shape
        call_args = fake_call.call_args
        msgs = call_args[0][0]  # first positional arg = messages list
        self.assertEqual(msgs[0]["role"], "system")

    def test_geopolitical_article_returns_no_opportunities(self):
        fake_response = json.dumps({
            "warrants_charts": False,
            "opportunities": [],
        })
        fake_call = mock.MagicMock(return_value=fake_response)
        analysis = analyze_article_for_data_viz(
            GEOPOLITICAL_ARTICLE, call_fn=fake_call, mode="classifier",
        )
        self.assertFalse(analysis.warrants_charts)
        self.assertEqual(len(analysis.opportunities), 0)

    def test_empty_article_returns_error(self):
        fake_call = mock.MagicMock(return_value="{}")
        analysis = analyze_article_for_data_viz(
            {}, call_fn=fake_call, mode="classifier",
        )
        self.assertFalse(analysis.warrants_charts)
        self.assertIn("no headline", analysis.error.lower())
        # call_fn should not have been called
        fake_call.assert_not_called()

    def test_call_fn_returns_non_string(self):
        fake_call = mock.MagicMock(return_value=None)
        analysis = analyze_article_for_data_viz(
            ECONOMIC_ARTICLE, call_fn=fake_call, mode="classifier",
        )
        self.assertFalse(analysis.warrants_charts)
        self.assertIn("empty", analysis.error.lower())


# ---------------------------------------------------------------------------
# render_figures_for_article (mocked end-to-end)
# ---------------------------------------------------------------------------

class TestRenderFiguresForArticle(unittest.TestCase):

    def test_geopolitical_article_returns_success_no_figures(self):
        """Non-economic article → success=True with empty figures list.
        This is editorially correct — not a failure."""
        fake_response = json.dumps({
            "warrants_charts": False, "opportunities": [],
        })
        fake_call = mock.MagicMock(return_value=fake_response)
        result = render_figures_for_article(
            GEOPOLITICAL_ARTICLE, call_fn=fake_call, mode="classifier",
        )
        self.assertTrue(result.success)
        self.assertEqual(len(result.figures), 0)
        self.assertFalse(result.analysis.warrants_charts)

    def test_economic_article_renders_figures(self):
        fake_response = json.dumps({
            "warrants_charts": True,
            "opportunities": [
                {"series_id": "UNRATE", "transformation": "raw",
                 "narrative_role": "anchors", "justification": "ok", "priority": 1},
            ],
        })
        fake_call = mock.MagicMock(return_value=fake_response)

        fake_figure_result = FigureResult(
            success=True,
            svg_path="/tmp/fake.svg",
            url="/figures/fake.svg",
            envelope={"id": "fig-fake", "type": "time_series"},
            attribution="Source: FRED, series UNRATE, retrieved today.",
            figure_schema={
                "url": "/figures/fake.svg",
                "alt": "alt text",
                "caption": "test caption",
                "credit": "MSI",
                "source": "FRED, series UNRATE",
                "chart_type": "timeseries",
                "transformation": "raw",
                "ai_authored": True,
            },
        )
        with mock.patch.object(adv, "render_figure",
                               return_value=fake_figure_result):
            result = render_figures_for_article(
                ECONOMIC_ARTICLE, call_fn=fake_call, mode="classifier",
                article_slug="2026-05-may-jobs-report",
            )

        self.assertTrue(result.success)
        self.assertEqual(len(result.figures), 1)
        self.assertEqual(result.figures[0]["chart_type"], "timeseries")
        self.assertEqual(len(result.figure_results), 1)

    def test_partial_render_failure_returns_what_succeeded(self):
        fake_response = json.dumps({
            "warrants_charts": True,
            "opportunities": [
                {"series_id": "UNRATE", "transformation": "raw",
                 "narrative_role": "anchors", "justification": "x", "priority": 1},
                {"series_id": "PAYEMS", "transformation": "first_diff",
                 "narrative_role": "quantifies", "justification": "x", "priority": 2},
            ],
        })
        fake_call = mock.MagicMock(return_value=fake_response)

        # First succeeds, second fails
        success_result = FigureResult(
            success=True, svg_path="/tmp/ok.svg",
            figure_schema={"url": "/figures/ok.svg", "chart_type": "timeseries"},
        )
        fail_result = FigureResult(
            success=False, error_code="data_unavailable",
            error_message="series has no data",
        )
        with mock.patch.object(adv, "render_figure",
                               side_effect=[success_result, fail_result]):
            result = render_figures_for_article(
                ECONOMIC_ARTICLE, call_fn=fake_call, mode="classifier",
            )

        self.assertTrue(result.success)  # at least one succeeded
        self.assertEqual(len(result.figures), 1)  # only the success
        self.assertEqual(len(result.figure_results), 2)  # both attempts logged

    def test_all_renders_fail_returns_overall_failure(self):
        fake_response = json.dumps({
            "warrants_charts": True,
            "opportunities": [
                {"series_id": "UNRATE", "transformation": "raw",
                 "narrative_role": "anchors", "justification": "x", "priority": 1},
            ],
        })
        fake_call = mock.MagicMock(return_value=fake_response)
        fail_result = FigureResult(
            success=False, error_code="render_failed",
            error_message="compiler died",
        )
        with mock.patch.object(adv, "render_figure", return_value=fail_result):
            result = render_figures_for_article(
                ECONOMIC_ARTICLE, call_fn=fake_call, mode="classifier",
            )

        self.assertFalse(result.success)
        self.assertEqual(len(result.figures), 0)
        self.assertIn("render_failed", result.error)

    def test_classifier_error_propagates(self):
        fake_call = mock.MagicMock(return_value=None)
        result = render_figures_for_article(
            ECONOMIC_ARTICLE, call_fn=fake_call, mode="classifier",
        )
        self.assertFalse(result.success)
        self.assertTrue(result.error)


CPI_ARTICLE_WITH_THEMES = {
    "headline": "April CPI cools to 3.1% as shelter inflation stays sticky",
    "lede": "Consumer prices rose 3.1 percent year-over-year in April 2026.",
    "metadata": {
        "primary_themes": [
            "inflation_measurement", "monetary_policy", "shelter_inflation",
            "k_shaped_consumer", "fed_rate_path",
        ],
    },
    "atomic_claims": [
        {"text": "The Consumer Price Index for All Urban Consumers rose 3.1 percent."},
        {"text": "Core CPI rose 3.3 percent year-over-year."},
        {"text": "Federal funds futures priced a 33 percent rate-cut probability."},
    ],
}


# ---------------------------------------------------------------------------
# Objective ranking — Phase 1 scoring
# ---------------------------------------------------------------------------

class TestDiagnosticPhrases(unittest.TestCase):
    def test_includes_series_id(self):
        entry = {"series_id": "CPIAUCSL", "name": "Consumer Price Index"}
        phrases = _diagnostic_phrases(entry)
        self.assertIn("cpiaucsl", phrases)

    def test_includes_full_name_lowercased(self):
        entry = {"series_id": "X", "name": "Federal Funds Rate"}
        phrases = _diagnostic_phrases(entry)
        self.assertIn("federal funds rate", phrases)

    def test_extracts_parenthetical(self):
        entry = {"series_id": "X", "name": "Unemployment Rate (U-3)"}
        phrases = _diagnostic_phrases(entry)
        self.assertIn("u-3", phrases)
        self.assertIn("unemployment rate", phrases)

    def test_extracts_bigrams_and_trigrams(self):
        entry = {"series_id": "X", "name": "Total Nonfarm Payrolls"}
        phrases = _diagnostic_phrases(entry)
        self.assertIn("nonfarm payrolls", phrases)  # bigram
        self.assertIn("total nonfarm payrolls", phrases)  # trigram

    def test_recognises_allcaps_abbreviations(self):
        entry = {"series_id": "PCEPI", "name": "PCE Price Index"}
        phrases = _diagnostic_phrases(entry)
        self.assertIn("pce", phrases)


class TestTopicSynonymExpansion(unittest.TestCase):
    def test_expands_known_theme(self):
        expanded = _expand_article_topics(["shelter_inflation"])
        # shelter_inflation maps to housing + inflation-measurement
        self.assertIn("housing", expanded)
        self.assertIn("inflation-measurement", expanded)

    def test_passes_unknown_theme_through(self):
        expanded = _expand_article_topics(["unknown_theme"])
        self.assertIn("unknown-theme", expanded)


class TestNameMatchScore(unittest.TestCase):
    def test_matches_explicit_citation(self):
        entry = {"series_id": "CPIAUCSL",
                 "name": "Consumer Price Index (all urban consumers)"}
        claims = [{"text": "The Consumer Price Index rose 3.1 percent."}]
        score, matched, _indices = _name_match_score(entry, claims)
        self.assertGreater(score, 0)
        self.assertTrue(any("consumer price" in m for m in matched))

    def test_returns_zero_when_no_claims(self):
        entry = {"series_id": "X", "name": "Y"}
        score, matched, _indices = _name_match_score(entry, [])
        self.assertEqual(score, 0.0)


class TestTopicOverlapScore(unittest.TestCase):
    def test_matches_overlapping_topic(self):
        entry = {"series_id": "X", "topics": ["inflation-measurement"]}
        score, matched = _topic_overlap_score(
            entry, ["inflation_measurement", "monetary_policy"])
        self.assertEqual(score, 1.0)
        self.assertIn("inflation-measurement", matched)

    def test_returns_zero_when_no_overlap(self):
        entry = {"series_id": "X", "topics": ["housing"]}
        score, matched = _topic_overlap_score(
            entry, ["geopolitics"])
        self.assertEqual(score, 0.0)


class TestRankIndicators(unittest.TestCase):
    def test_cpi_article_ranks_cpi_indicators_high(self):
        ranked = rank_indicators_for_article(CPI_ARTICLE_WITH_THEMES)
        # Top 3 should include CPIAUCSL and either CPILFESL or FEDFUNDS
        top_ids = {s.entry["series_id"] for s in ranked[:4]}
        self.assertIn("CPIAUCSL", top_ids)
        # CPILFESL or PCEPI should also be high (both inflation indicators
        # the article touches via topic overlap)
        self.assertTrue(
            "CPILFESL" in top_ids or "PCEPI" in top_ids,
            f"top picks were: {top_ids}",
        )

    def test_geopolitical_article_scores_all_zero(self):
        # No themes, no claim-name matches → no indicator clears the
        # threshold under Phase 1 (name + topic only). With Phase 2
        # semantic embeddings, unrelated-domain content can still have
        # non-zero cosine similarity to economic indicators, so we
        # isolate Phase 1 behavior with use_semantic=False.
        ranked = rank_indicators_for_article(
            GEOPOLITICAL_ARTICLE, use_semantic=False)
        self.assertTrue(all(s.total == 0 for s in ranked),
                        f"unexpected non-zero: {[(s.entry['series_id'], s.total) for s in ranked if s.total > 0]}")

    def test_deterministic_same_input_same_picks(self):
        ranked1 = rank_indicators_for_article(CPI_ARTICLE_WITH_THEMES)
        ranked2 = rank_indicators_for_article(CPI_ARTICLE_WITH_THEMES)
        ids1 = [s.entry["series_id"] for s in ranked1]
        ids2 = [s.entry["series_id"] for s in ranked2]
        self.assertEqual(ids1, ids2)


class TestAnalyzeArticleViaRanking(unittest.TestCase):
    def test_returns_opportunities_for_economic_article(self):
        analysis = analyze_article_via_ranking(CPI_ARTICLE_WITH_THEMES)
        self.assertTrue(analysis.warrants_charts)
        self.assertGreater(len(analysis.opportunities), 0)
        self.assertLessEqual(len(analysis.opportunities), 4)

    def test_returns_no_charts_for_geopolitical_article(self):
        # Phase 1 isolation: with semantic off, no indicator clears the
        # threshold (no themes, no name matches).
        analysis = analyze_article_via_ranking(
            GEOPOLITICAL_ARTICLE, use_semantic=False)
        self.assertFalse(analysis.warrants_charts)

    def test_justification_is_deterministic_and_auditable(self):
        analysis = analyze_article_via_ranking(CPI_ARTICLE_WITH_THEMES)
        for opp in analysis.opportunities:
            # Each opportunity's justification must carry an audit trail.
            # Singleton opportunities cite per-dimension score components
            # ("score: name_match=0.8, theme=..."); composite-chart
            # opportunities cite group-membership ("Composite chart: N of
            # M group members ... appeared in top picks"). Both formats
            # are deterministic and auditable; the test accepts either.
            j = opp.justification
            self.assertTrue(
                "score:" in j or "Composite chart:" in j,
                f"justification lacks audit signal: {j!r}"
            )

    def test_default_mode_via_main_entry_is_ranking(self):
        # No call_fn, no mode kwarg → ranking path, succeeds.
        analysis = analyze_article_for_data_viz(CPI_ARTICLE_WITH_THEMES)
        self.assertTrue(analysis.warrants_charts)


# ---------------------------------------------------------------------------
# Phase 2 — semantic match
# ---------------------------------------------------------------------------

class TestSemanticMatch(unittest.TestCase):
    """Phase 2 — semantic embedding match.

    Uses controlled fixture vectors via mocked _embed_texts so the tests
    don't depend on live Ollama. Verifies that the wiring is correct
    (similarity → score → total) without relying on real embedding
    quality.
    """

    def _patch_embed(self, indicator_vector_map: dict[str, list[float]],
                     claim_vectors: list[list[float]]):
        """Build a mock that returns indicator vectors for the catalog
        call (long list) and claim vectors for the claims call (short
        list). Both calls funnel through _embed_texts so a side_effect
        function distinguishes by argument length / content."""
        catalog_ids = [e["series_id"] for e in adv.INDICATOR_CATALOG]

        def fake_embed(texts):
            if len(texts) == len(catalog_ids):
                return [indicator_vector_map.get(sid, [0.0] * 768)
                        for sid in catalog_ids]
            return claim_vectors[: len(texts)]

        return mock.patch.object(adv, "_embed_texts", side_effect=fake_embed)

    def test_semantic_match_lifts_a_non_named_indicator(self):
        """When an article doesn't name an indicator but its claims are
        semantically close, the semantic_match dimension should lift
        that indicator's total score."""
        # Construct an article whose claims are semantically close to
        # CSUSHPISA (the Case-Shiller home price index) via the mock,
        # but never name it.
        article = {
            "metadata": {"primary_themes": []},  # no topic overlap either
            "atomic_claims": [
                {"text": "Homeowners face stretched budgets as housing costs rise."},
            ],
        }
        # Set CSUSHPISA's indicator vector to match the claim's vector.
        # 768-dim vectors; just use [1, 0, 0, ...] for the claim and
        # CSUSHPISA, and orthogonal for everything else.
        claim_vec = [1.0] + [0.0] * 767
        ind_map = {sid: [0.0] * 768 for sid in
                   (e["series_id"] for e in adv.INDICATOR_CATALOG)}
        ind_map["CSUSHPISA"] = claim_vec  # identical → cos sim = 1.0

        # Bypass the cache by using a side_effect that always runs:
        with mock.patch.object(adv, "_load_or_compute_indicator_embeddings",
                               return_value=ind_map):
            with self._patch_embed(ind_map, [claim_vec]):
                ranked = adv.rank_indicators_for_article(article)

        # CSUSHPISA should be the top pick — sim=1.0 → normalized=1.0
        # → weighted=2.0 → total=2.0; everything else 0.
        self.assertEqual(ranked[0].entry["series_id"], "CSUSHPISA")
        self.assertAlmostEqual(ranked[0].semantic_match, 1.0, places=3)
        self.assertGreater(ranked[0].total, 0)

    def test_semantic_disabled_via_kwarg_returns_phase1_only(self):
        # With use_semantic=False, semantic scores should all be 0
        # regardless of mock vectors.
        article = CPI_ARTICLE_WITH_THEMES
        ranked = adv.rank_indicators_for_article(article, use_semantic=False)
        self.assertTrue(all(s.semantic_match == 0.0 for s in ranked))

    def test_embedder_unavailable_degrades_to_phase1(self):
        # When _load_or_compute_indicator_embeddings returns None
        # (Ollama unreachable), the ranking falls back to Phase 1 only.
        with mock.patch.object(adv, "_load_or_compute_indicator_embeddings",
                               return_value=None):
            ranked = adv.rank_indicators_for_article(CPI_ARTICLE_WITH_THEMES)
        # All semantic scores 0, but Phase 1 still finds CPI indicators.
        self.assertTrue(all(s.semantic_match == 0.0 for s in ranked))
        self.assertGreater(ranked[0].total, 0)  # Phase 1 still works

    def test_cosine_similarity_unit_vectors(self):
        # Identical vectors → 1.0
        v = [0.6, 0.8, 0.0]
        self.assertAlmostEqual(adv._cosine_similarity(v, v), 1.0, places=5)
        # Orthogonal → 0.0
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        self.assertAlmostEqual(adv._cosine_similarity(a, b), 0.0, places=5)
        # Empty / None → 0.0
        self.assertEqual(adv._cosine_similarity([], []), 0.0)
        self.assertEqual(adv._cosine_similarity(None, [1.0]), 0.0)

    def test_indicator_embedding_text_includes_name_and_covers(self):
        entry = {"series_id": "X", "name": "Foo Bar", "covers": "the foo signal"}
        text = adv._indicator_embedding_text(entry)
        self.assertIn("Foo Bar", text)
        self.assertIn("the foo signal", text)


class TestLibraryMatchScore(unittest.TestCase):
    """Phase 3 — library_match scoring against the Distributional Library."""

    def test_expand_article_reports_known_theme(self):
        out = adv._expand_article_reports(["inflation_measurement"])
        self.assertIn("1.5", out)

    def test_expand_article_reports_multi_report_theme(self):
        # shelter_inflation maps to ["2.8", "1.5"]
        out = adv._expand_article_reports(["shelter_inflation"])
        self.assertIn("2.8", out)
        self.assertIn("1.5", out)

    def test_expand_article_reports_unknown_theme(self):
        # Unknown themes contribute nothing
        self.assertEqual(adv._expand_article_reports(["geopolitics"]), set())

    def test_library_match_scores_overlap(self):
        entry = {"series_id": "CPIAUCSL", "linked_reports": ["1.5"]}
        score, matched = adv._library_match_score(
            entry, ["inflation_measurement"])
        self.assertEqual(score, 1.0)  # 1 of 1 reports overlap
        self.assertEqual(matched, ["1.5"])

    def test_library_match_partial_overlap(self):
        entry = {"series_id": "MORTGAGE30US", "linked_reports": ["2.5", "2.8"]}
        # shelter_inflation expands to ["2.8", "1.5"] → overlaps 2.8 only
        score, matched = adv._library_match_score(entry, ["shelter_inflation"])
        self.assertEqual(score, 0.5)  # 1 of 2
        self.assertEqual(matched, ["2.8"])

    def test_library_match_returns_zero_when_no_linked_reports(self):
        entry = {"series_id": "X"}  # no linked_reports field
        score, matched = adv._library_match_score(
            entry, ["inflation_measurement"])
        self.assertEqual(score, 0.0)
        self.assertEqual(matched, [])

    def test_ranking_uses_library_dimension(self):
        # The CPI article should have library_match contributing > 0 for
        # CPIAUCSL because inflation_measurement → report 1.5 ∈ CPIAUCSL.linked_reports
        ranked = adv.rank_indicators_for_article(
            CPI_ARTICLE_WITH_THEMES, use_semantic=False,
        )
        cpi = next(s for s in ranked if s.entry["series_id"] == "CPIAUCSL")
        self.assertGreater(cpi.library_match, 0)
        self.assertIn("1.5", cpi.matched_reports)


class TestCompositeConsolidation(unittest.TestCase):
    """Tests for the composite-chart post-pass consolidation logic."""

    def test_series_to_group_resolves_known_member(self):
        self.assertEqual(adv._series_to_group("UNRATE"), "unemployment-rates")
        self.assertEqual(adv._series_to_group("CPIAUCSL"), "inflation-yoy")
        self.assertEqual(adv._series_to_group("FEDFUNDS"), "policy-rates")

    def test_series_to_group_unknown_returns_none(self):
        self.assertIsNone(adv._series_to_group("NOT_A_SERIES"))

    def test_consolidates_when_threshold_met(self):
        # inflation-yoy has min_members_for_composite=3. Provide 4 picks.
        picks = [
            adv.VizOpportunity(series_id="CPIAUCSL", transformation="yoy_pct", priority=1),
            adv.VizOpportunity(series_id="CPILFESL", transformation="yoy_pct", priority=2),
            adv.VizOpportunity(series_id="PCEPI", transformation="raw", priority=3),
            adv.VizOpportunity(series_id="PCEPILFE", transformation="raw", priority=4),
        ]
        result = adv._consolidate_composites(picks)
        # All 4 fold into one composite
        self.assertEqual(len(result), 1)
        comp = result[0]
        self.assertIsInstance(comp, adv.CompositeOpportunity)
        self.assertEqual(comp.group_id, "inflation-yoy")
        # The composite chart shows ALL group members, not just the
        # picked subset (4 in this case matches both)
        self.assertEqual(sorted(comp.members),
                         sorted(["CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE"]))

    def test_does_not_consolidate_below_threshold(self):
        # Only 2 picks from inflation-yoy (threshold 3) → no consolidation
        picks = [
            adv.VizOpportunity(series_id="CPIAUCSL", transformation="yoy_pct", priority=1),
            adv.VizOpportunity(series_id="CPILFESL", transformation="yoy_pct", priority=2),
        ]
        result = adv._consolidate_composites(picks)
        self.assertEqual(len(result), 2)
        for r in result:
            self.assertIsInstance(r, adv.VizOpportunity)

    def test_consolidates_two_member_group(self):
        # unemployment-rates has min=2; UNRATE + U6RATE → composite
        picks = [
            adv.VizOpportunity(series_id="UNRATE", transformation="raw", priority=1),
            adv.VizOpportunity(series_id="U6RATE", transformation="raw", priority=2),
        ]
        result = adv._consolidate_composites(picks)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].group_id, "unemployment-rates")

    def test_mixes_composite_and_singletons(self):
        # CPI×3 (consolidates) + FEDFUNDS singleton
        picks = [
            adv.VizOpportunity(series_id="CPIAUCSL", transformation="yoy_pct", priority=1),
            adv.VizOpportunity(series_id="CPILFESL", transformation="yoy_pct", priority=2),
            adv.VizOpportunity(series_id="PCEPI", transformation="raw", priority=3),
            adv.VizOpportunity(series_id="FEDFUNDS", transformation="raw", priority=4),
        ]
        result = adv._consolidate_composites(picks)
        # 1 composite + 1 singleton; FEDFUNDS alone below its 2-member
        # threshold for policy-rates group
        self.assertEqual(len(result), 2)
        types = {type(r).__name__ for r in result}
        self.assertEqual(types, {"CompositeOpportunity", "VizOpportunity"})

    def test_orders_by_priority(self):
        # FEDFUNDS+DGS10 → policy-rates composite at priority min(3,4)=3
        # CPIAUCSL+CPILFESL+PCEPI → inflation-yoy composite at priority 1
        picks = [
            adv.VizOpportunity(series_id="CPIAUCSL", transformation="yoy_pct", priority=1),
            adv.VizOpportunity(series_id="CPILFESL", transformation="yoy_pct", priority=2),
            adv.VizOpportunity(series_id="PCEPI", transformation="raw", priority=3),
            adv.VizOpportunity(series_id="FEDFUNDS", transformation="raw", priority=4),
            adv.VizOpportunity(series_id="DGS10", transformation="raw", priority=5),
        ]
        result = adv._consolidate_composites(picks)
        # Two composites; inflation-yoy first by priority
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].group_id, "inflation-yoy")
        self.assertEqual(result[1].group_id, "policy-rates")


class TestResolveAsOfDate(unittest.TestCase):
    """Tests for _resolve_as_of_date — picks the FRED vintage date."""

    def test_env_override_wins(self):
        with mock.patch.dict("os.environ", {"ORA_FRED_AS_OF": "2024-03-15"}):
            self.assertEqual(
                adv._resolve_as_of_date({"publish_date": "2025-01-01"}),
                "2024-03-15",
            )

    def test_falls_back_to_publish_date_string(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("ORA_FRED_AS_OF", None)
            self.assertEqual(
                adv._resolve_as_of_date({"publish_date": "2024-03-15"}),
                "2024-03-15",
            )

    def test_handles_date_object_from_yaml(self):
        from datetime import date
        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("ORA_FRED_AS_OF", None)
            self.assertEqual(
                adv._resolve_as_of_date({"publish_date": date(2024, 3, 15)}),
                "2024-03-15",
            )

    def test_returns_none_when_no_signal(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("ORA_FRED_AS_OF", None)
            self.assertIsNone(adv._resolve_as_of_date({}))


class TestFredAsOfUrlConstruction(unittest.TestCase):
    """Verify the FRED URL includes realtime_start/realtime_end when
    as_of_date is set on the SeriesQuery."""

    def test_observations_url_includes_realtime_params(self):
        from orchestrator.integrations import fred_api as fa
        captured = {}

        def fake_get(url, *, timeout=30):
            captured["url"] = url
            return {"observations": [{"date": "2024-03-01", "value": "100.0"}]}

        with mock.patch.object(fa, "_http_get_json", side_effect=fake_get), \
             mock.patch.object(fa, "_get_api_key", return_value="dummy"), \
             mock.patch.object(fa, "_read_cache", return_value=None), \
             mock.patch.object(fa, "_write_cache"), \
             mock.patch.object(fa, "_fetch_metadata", return_value=None):
            fa.fetch_series(fa.SeriesQuery(
                series_id="GDPC1",
                observation_start="2022-01-01",
                as_of_date="2024-03-15",
            ))
        self.assertIn("realtime_start=2024-03-15", captured["url"])
        self.assertIn("realtime_end=2024-03-15", captured["url"])

    def test_observations_url_omits_realtime_when_no_as_of(self):
        from orchestrator.integrations import fred_api as fa
        captured = {}

        def fake_get(url, *, timeout=30):
            captured["url"] = url
            return {"observations": [{"date": "2024-03-01", "value": "100.0"}]}

        with mock.patch.object(fa, "_http_get_json", side_effect=fake_get), \
             mock.patch.object(fa, "_get_api_key", return_value="dummy"), \
             mock.patch.object(fa, "_read_cache", return_value=None), \
             mock.patch.object(fa, "_write_cache"), \
             mock.patch.object(fa, "_fetch_metadata", return_value=None):
            fa.fetch_series(fa.SeriesQuery(series_id="GDPC1"))
        self.assertNotIn("realtime_start", captured["url"])

    def test_cache_key_differs_by_as_of(self):
        """Same series + different as_of = different cache file. Prevents
        a current-data fetch from polluting a vintage fetch and vice versa."""
        from orchestrator.integrations import fred_api as fa
        q1 = fa.SeriesQuery(series_id="GDPC1", as_of_date=None)
        q2 = fa.SeriesQuery(series_id="GDPC1", as_of_date="2024-03-15")
        self.assertNotEqual(fa._cache_key(q1), fa._cache_key(q2))


class TestFrameworkAlignment(unittest.TestCase):
    """Phase 4 — framework-point alignment scoring."""

    def test_expand_article_framework_points(self):
        out = adv._expand_article_framework_points(["inflation_measurement"])
        # inflation_measurement → [3, 9]
        self.assertIn(3, out)
        self.assertIn(9, out)

    def test_expand_unknown_theme_returns_empty(self):
        self.assertEqual(
            adv._expand_article_framework_points(["geopolitics"]),
            set(),
        )

    def test_framework_alignment_scores_overlap(self):
        # CPIAUCSL has framework_points=[3, 9]
        entry = {"series_id": "CPIAUCSL", "framework_points": [3, 9]}
        score, matched = adv._framework_alignment_score(
            entry, ["inflation_measurement"])
        self.assertEqual(score, 1.0)  # 2 of 2 points match
        self.assertEqual(matched, [3, 9])

    def test_framework_alignment_partial_overlap(self):
        # Indicator carries [3, 4, 13]; article's themes give [3, 9]
        entry = {"series_id": "X", "framework_points": [3, 4, 13]}
        score, matched = adv._framework_alignment_score(
            entry, ["inflation_measurement"])
        # Only point 3 overlaps. 1 of 3 = 0.333
        self.assertAlmostEqual(score, 1.0 / 3.0, places=3)
        self.assertEqual(matched, [3])

    def test_framework_alignment_zero_when_no_points(self):
        entry = {"series_id": "X"}  # no framework_points
        score, matched = adv._framework_alignment_score(
            entry, ["inflation_measurement"])
        self.assertEqual(score, 0.0)
        self.assertEqual(matched, [])

    def test_ranking_uses_framework_alignment(self):
        ranked = adv.rank_indicators_for_article(
            CPI_ARTICLE_WITH_THEMES, use_semantic=False,
        )
        cpi = next(s for s in ranked if s.entry["series_id"] == "CPIAUCSL")
        # CPIAUCSL framework_points=[3, 9]; article gives points [3, 9, 13, 4, 10] etc
        # → score 1.0
        self.assertGreater(cpi.framework_alignment, 0)
        self.assertIn(3, cpi.matched_framework_points)


class TestFactCheck(unittest.TestCase):
    """Fact-check article body values against FRED ground truth."""

    def test_extract_first_percent_simple(self):
        self.assertEqual(adv._extract_first_percent("rose 3.1 percent"), 3.1)
        self.assertEqual(adv._extract_first_percent("up 3.1%"), 3.1)
        self.assertEqual(adv._extract_first_percent("-1.8 percent decline"), -1.8)

    def test_extract_first_percent_returns_none_when_absent(self):
        self.assertIsNone(adv._extract_first_percent(""))
        self.assertIsNone(adv._extract_first_percent("Iran rejected the proposal."))

    def test_extract_first_percent_first_only_when_multiple(self):
        # "3.1 percent ... 3.3 percent" → first one wins
        self.assertEqual(
            adv._extract_first_percent("headline 3.1 percent and core 3.3 percent"),
            3.1,
        )

    def test_fact_check_skips_non_comparable_predicates(self):
        # Probability claim → should be skipped (predicate is non-comparable)
        article = {
            "atomic_claims": [
                {"claim_id": "c_001",
                 "text": "Fed funds futures priced ~33 percent probability.",
                 "predicate": "priced_probability_of",
                 "temporal": "2026-05-13"},
            ],
        }
        scored = [adv.ScoredIndicator(
            entry={"series_id": "FEDFUNDS", "default_transformation": "raw"},
            name_match=1.0,
            matched_claim_indices=[0],
        )]
        results = adv.fact_check_article_against_fred(article, scored)
        self.assertEqual(len(results), 1)
        self.assertIsNone(results[0].discrepancy_pp)
        self.assertIn("non-comparable", results[0].note)

    def test_fact_check_skips_claims_without_percent(self):
        article = {
            "atomic_claims": [
                {"claim_id": "c_001",
                 "text": "Fed kept the target range unchanged.",
                 "predicate": "reported_yoy_change",
                 "temporal": "2026-05-13"},
            ],
        }
        scored = [adv.ScoredIndicator(
            entry={"series_id": "FEDFUNDS", "default_transformation": "raw"},
            name_match=1.0,
            matched_claim_indices=[0],
        )]
        results = adv.fact_check_article_against_fred(article, scored)
        self.assertEqual(len(results), 1)
        self.assertIsNone(results[0].article_value)
        self.assertIn("no percent value", results[0].note)

    def test_fact_check_flags_discrepancy_above_tolerance(self):
        article = {
            "atomic_claims": [
                {"claim_id": "c_001",
                 "text": "CPI rose 3.1 percent over 12 months.",
                 "predicate": "reported_yoy_change",
                 "temporal": "2026-04-30"},
            ],
        }
        scored = [adv.ScoredIndicator(
            entry={"series_id": "CPIAUCSL",
                   "default_transformation": "yoy_pct"},
            name_match=1.0,
            matched_claim_indices=[0],
        )]
        # Mock the FRED-value fetcher to return 3.78 (the actual FRED
        # value as of April 2026); article claims 3.1 → 0.68pp discrepancy
        # exceeds the 0.5pp default tolerance.
        with mock.patch.object(adv, "_fred_value_for_claim",
                               return_value=3.78):
            results = adv.fact_check_article_against_fred(article, scored)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertAlmostEqual(r.article_value, 3.1, places=2)
        self.assertAlmostEqual(r.fred_value, 3.78, places=2)
        self.assertFalse(r.within_tolerance)
        self.assertAlmostEqual(r.discrepancy_pp, 0.68, places=2)

    def test_fact_check_passes_within_tolerance(self):
        article = {
            "atomic_claims": [
                {"claim_id": "c_001",
                 "text": "CPI rose 3.7 percent over 12 months.",
                 "predicate": "reported_yoy_change",
                 "temporal": "2026-04-30"},
            ],
        }
        scored = [adv.ScoredIndicator(
            entry={"series_id": "CPIAUCSL",
                   "default_transformation": "yoy_pct"},
            name_match=1.0,
            matched_claim_indices=[0],
        )]
        with mock.patch.object(adv, "_fred_value_for_claim",
                               return_value=3.78):
            results = adv.fact_check_article_against_fred(article, scored)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].within_tolerance)

    def test_fact_check_skips_when_fred_unavailable(self):
        article = {
            "atomic_claims": [
                {"claim_id": "c_001",
                 "text": "CPI rose 3.1 percent.",
                 "predicate": "reported_yoy_change",
                 "temporal": "2026-04-30"},
            ],
        }
        scored = [adv.ScoredIndicator(
            entry={"series_id": "CPIAUCSL",
                   "default_transformation": "yoy_pct"},
            name_match=1.0,
            matched_claim_indices=[0],
        )]
        with mock.patch.object(adv, "_fred_value_for_claim",
                               return_value=None):
            results = adv.fact_check_article_against_fred(article, scored)
        self.assertEqual(len(results), 1)
        self.assertIsNone(results[0].fred_value)
        self.assertIn("no FRED value", results[0].note)

    def test_fact_check_returns_empty_when_no_picks(self):
        article = {"atomic_claims": [{"claim_id": "c_001", "text": "Test."}]}
        results = adv.fact_check_article_against_fred(article, [])
        self.assertEqual(results, [])

    def test_fact_check_skips_picks_without_matched_claims(self):
        article = {"atomic_claims": [{"claim_id": "c_001", "text": "Test."}]}
        scored = [adv.ScoredIndicator(
            entry={"series_id": "CPIAUCSL", "default_transformation": "raw"},
            name_match=0.0,
            matched_claim_indices=[],  # no claims matched
        )]
        results = adv.fact_check_article_against_fred(article, scored)
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
