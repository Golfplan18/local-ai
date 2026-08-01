#!/usr/bin/env python3
"""Guided values setup — registry, composer, marker, and endpoints.

Covers ``orchestrator/mind_guided.py`` (question registry validity, the
answers→mind.md composer, provenance-marker round-trip, free-text
sanitization) and the ``GET/POST /api/mind/guided`` endpoints in
``server/app.py`` (prefill, overwrite guard, validation errors).

Run::

    /opt/homebrew/bin/python3 -m unittest \
        orchestrator.tests.test_mind_guided -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))

import mind_guided as mg  # noqa: E402

STOCK_TEMPLATE = """# mind.md — Values Framework

*Default configuration. Customize by running the guided values setup.*

## Communication Preferences

Lead with conclusions.
"""

HAND_EDITED = """# mind.md — Values Framework

## My Own Rules

Never bury the lede.
"""


class RegistryValidity(unittest.TestCase):
    def test_question_ids_unique(self):
        ids = [q["id"] for q in mg.QUESTIONS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_sections_known_and_all_covered(self):
        for q in mg.QUESTIONS:
            self.assertIn(q["section"], mg.SECTION_ORDER)
        covered = {q["section"] for q in mg.QUESTIONS}
        self.assertEqual(covered, set(mg.SECTION_ORDER))

    def test_options_complete(self):
        for q in mg.QUESTIONS:
            opt_ids = [o["id"] for o in q["options"]]
            self.assertEqual(len(opt_ids), len(set(opt_ids)), q["id"])
            for o in q["options"]:
                for field in ("id", "label", "example", "prose"):
                    self.assertTrue(o.get(field), f"{q['id']}/{o.get('id')}: {field}")

    def test_free_text_ids_unique(self):
        fts = [q["free_text"]["id"] for q in mg.QUESTIONS if q.get("free_text")]
        self.assertEqual(len(fts), len(set(fts)))

    def test_default_answers_cover_option_questions(self):
        d = mg.default_answers()
        for q in mg.QUESTIONS:
            if q["options"]:
                self.assertEqual(d[q["id"]], q["options"][0]["id"])
            else:
                self.assertNotIn(q["id"], d)

    def test_questions_payload_json_safe(self):
        json.dumps(mg.questions_payload())


class Validation(unittest.TestCase):
    def test_unknown_question_rejected(self):
        with self.assertRaises(ValueError):
            mg.validate({"nope": "x"}, {})

    def test_unknown_option_rejected(self):
        with self.assertRaises(ValueError):
            mg.validate({"lead": "nope"}, {})

    def test_option_answer_for_free_text_only_question_rejected(self):
        with self.assertRaises(ValueError):
            mg.validate({"principles": "anything"}, {})

    def test_unknown_free_text_rejected(self):
        with self.assertRaises(ValueError):
            mg.validate({}, {"nope": "x"})

    def test_missing_answers_defaulted(self):
        answers, _ = mg.validate({"hedging": "softened"}, {})
        self.assertEqual(answers["hedging"], "softened")
        self.assertEqual(answers["lead"], "lead_conclusions")

    def test_free_text_sanitized_and_capped(self):
        _, ft = mg.validate({}, {
            "peer_domains": "  a<!-- evil -->b  ",
            "principles": "x" * 2000,
        })
        self.assertEqual(ft["peer_domains"], "a evil b")
        self.assertNotIn("<!--", ft["peer_domains"])
        self.assertNotIn("-->", ft["peer_domains"])
        self.assertEqual(len(ft["principles"]), mg.FREE_TEXT_MAX_LEN)

    def test_empty_free_text_dropped(self):
        _, ft = mg.validate({}, {"peer_domains": "   "})
        self.assertEqual(ft, {})


class Composer(unittest.TestCase):
    def test_all_sections_in_order(self):
        out = mg.compose({}, {})
        positions = [out.index(f"## {name}") for name in mg.SECTION_ORDER]
        self.assertEqual(positions, sorted(positions))

    def test_marker_present_and_default_template_marker_absent(self):
        out = mg.compose({}, {})
        self.assertIn(mg.MARKER_PREFIX, out)
        self.assertNotIn("*Default configuration. Customize by running the", out)

    def test_default_prose_present(self):
        out = mg.compose({}, {})
        self.assertIn("Lead with conclusions.", out)
        self.assertIn("maintain your position", out)
        self.assertIn("Do not fabricate sources", out)
        self.assertIn("Honesty is the foundation.", out)

    def test_calibration_fixed_lines_present(self):
        # The pushback-threshold calibration (2026-07-01) is emitted
        # regardless of answers — it is a floor, not a preference.
        out = mg.compose({"pushback": "defer"}, {})
        self.assertIn("agree cooperatively", out)
        self.assertIn("distinguish nitpicks from material objections", out)
        self.assertIn("Never silently override instructions.", out)

    def test_non_default_choice_swaps_prose(self):
        out = mg.compose({"length": "thorough"}, {})
        self.assertIn("Default to thorough answers", out)
        self.assertNotIn("minimum length that fully addresses", out)

    def test_directness_principle_tracks_hedging(self):
        direct = mg.compose({"hedging": "direct"}, {})
        softened = mg.compose({"hedging": "softened"}, {})
        self.assertIn("Directness is respect.", direct)
        self.assertNotIn("Directness is respect.", softened)
        self.assertIn("Candor with care", softened)

    def test_peer_domains_line(self):
        out = mg.compose({}, {"peer_domains": "distributed systems, baking"})
        self.assertIn(
            "Treat these as peer-level domains: distributed systems, baking.",
            out)

    def test_principles_lines_appended(self):
        out = mg.compose({}, {"principles": "Never use emoji.\n\nDates in ISO format."})
        # Search the section body, not the provenance marker (the raw free
        # text also appears inside the marker JSON near the top of file).
        body = out[out.index("## Standing Principles"):]
        self.assertIn("Never use emoji.", body)
        self.assertIn("Dates in ISO format.", body)
        # After the fixed closing principles.
        self.assertLess(body.index("performance of helpfulness"),
                        body.index("Never use emoji."))

    def test_marker_round_trip(self):
        answers = {"hedging": "softened", "length": "balanced"}
        ft = {"peer_domains": "woodworking"}
        parsed = mg.parse_marker(mg.compose(answers, ft))
        self.assertEqual(parsed["v"], mg.MARKER_VERSION)
        self.assertEqual(parsed["answers"]["hedging"], "softened")
        self.assertEqual(parsed["answers"]["length"], "balanced")
        # Defaults were materialized into the marker too.
        self.assertEqual(parsed["answers"]["lead"], "lead_conclusions")
        self.assertEqual(parsed["free_text"], ft)

    def test_parse_marker_absent_or_malformed(self):
        self.assertIsNone(mg.parse_marker(""))
        self.assertIsNone(mg.parse_marker(HAND_EDITED))
        self.assertIsNone(mg.parse_marker(mg.MARKER_PREFIX + " {not json} -->"))


class GuidedEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ORCHESTRATOR.parent / "server"))
        try:
            from server import app as S  # type: ignore
            cls.S = S
            cls.import_ok = True
        except Exception as exc:  # pragma: no cover
            cls.S = None
            cls.import_ok = False
            cls.import_err = str(exc)

    def setUp(self):
        if not self.import_ok:
            self.skipTest(
                f"could not import server.py: "
                f"{getattr(self, 'import_err', '<unknown>')}"
            )
        self._tmp = tempfile.TemporaryDirectory()
        self._mind = os.path.join(self._tmp.name, "mind.md")
        self._saved = self.S.MIND_MD_PATH
        self.S.MIND_MD_PATH = self._mind
        self.client = self.S.app.test_client()

    def tearDown(self):
        if self.import_ok:
            self.S.MIND_MD_PATH = self._saved
            self._tmp.cleanup()

    def _post(self, payload):
        return self.client.post(
            "/api/mind/guided", data=json.dumps(payload),
            content_type="application/json",
        )

    def test_marker_literal_matches_module(self):
        self.assertEqual(self.S._MIND_GUIDED_MARKER, mg.MARKER_PREFIX)

    def test_get_no_file(self):
        payload = json.loads(self.client.get("/api/mind/guided").data)
        self.assertFalse(payload["exists"])
        self.assertIsNone(payload["answers"])
        self.assertTrue(payload["questions"])
        self.assertEqual([q["id"] for q in payload["questions"]],
                         [q["id"] for q in mg.QUESTIONS])

    def test_post_writes_guided_file(self):
        resp = self._post({"answers": {"hedging": "softened"}, "free_text": {}})
        self.assertEqual(resp.status_code, 200, resp.data)
        payload = json.loads(resp.data)
        self.assertTrue(payload["exists"])
        self.assertTrue(payload["is_guided"])
        self.assertFalse(payload["is_default_template"])
        self.assertEqual(payload["sections"], mg.SECTION_ORDER)

    def test_get_prefills_after_post(self):
        self._post({"answers": {"length": "thorough"},
                    "free_text": {"peer_domains": "baking"}})
        payload = json.loads(self.client.get("/api/mind/guided").data)
        self.assertTrue(payload["is_guided"])
        self.assertEqual(payload["answers"]["length"], "thorough")
        self.assertEqual(payload["free_text"], {"peer_domains": "baking"})

    def test_post_over_stock_template_allowed(self):
        with open(self._mind, "w") as f:
            f.write(STOCK_TEMPLATE)
        self.assertEqual(self._post({"answers": {}}).status_code, 200)

    def test_post_over_guided_file_allowed(self):
        self._post({"answers": {}})
        self.assertEqual(self._post({"answers": {"hedging": "softened"}}).status_code, 200)

    def test_post_over_hand_edited_requires_confirm(self):
        with open(self._mind, "w") as f:
            f.write(HAND_EDITED)
        resp = self._post({"answers": {}})
        self.assertEqual(resp.status_code, 409)
        self.assertTrue(json.loads(resp.data)["needs_confirm"])
        with open(self._mind) as f:  # untouched
            self.assertEqual(f.read(), HAND_EDITED)
        resp = self._post({"answers": {}, "confirm_overwrite": True})
        self.assertEqual(resp.status_code, 200)
        with open(self._mind) as f:
            self.assertIn(mg.MARKER_PREFIX, f.read())

    def test_post_unknown_option_400(self):
        self.assertEqual(self._post({"answers": {"lead": "nope"}}).status_code, 400)
        self.assertEqual(
            self._post({"answers": {"nope": "x"}}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
