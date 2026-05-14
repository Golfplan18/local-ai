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
        score, matched = _name_match_score(entry, claims)
        self.assertGreater(score, 0)
        self.assertTrue(any("consumer price" in m for m in matched))

    def test_returns_zero_when_no_claims(self):
        entry = {"series_id": "X", "name": "Y"}
        score, matched = _name_match_score(entry, [])
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
        # threshold
        ranked = rank_indicators_for_article(GEOPOLITICAL_ARTICLE)
        # All scores 0 (no metadata.primary_themes; claims don't mention
        # any catalog series)
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
        analysis = analyze_article_via_ranking(GEOPOLITICAL_ARTICLE)
        self.assertFalse(analysis.warrants_charts)

    def test_justification_is_deterministic_and_auditable(self):
        analysis = analyze_article_via_ranking(CPI_ARTICLE_WITH_THEMES)
        for opp in analysis.opportunities:
            # Justification should mention score components
            self.assertIn("score:", opp.justification)

    def test_default_mode_via_main_entry_is_ranking(self):
        # No call_fn, no mode kwarg → ranking path, succeeds.
        analysis = analyze_article_for_data_viz(CPI_ARTICLE_WITH_THEMES)
        self.assertTrue(analysis.warrants_charts)


if __name__ == "__main__":
    unittest.main(verbosity=2)
