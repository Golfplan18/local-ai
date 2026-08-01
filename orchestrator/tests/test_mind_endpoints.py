#!/usr/bin/env python3
"""/api/mind endpoints + the pipeline values-block fix (2026-07-01).

Covers:
* GET /api/mind — existence/summary payload, stock-template detection,
  section extraction.
* POST /api/mind — editor save (atomic write, validation) and
  create-from-template (refuses to clobber a customized file).
* boot._extract_boot_behavioral_preamble — the [YOUR VALUES — mind.md]
  block appended by load_boot_md must survive the pipeline-prompt trim
  (before the fix it was silently dropped, so the custom-values toggle
  never reached gear 1-4 step prompts).

Run::

    /opt/homebrew/bin/python3 -m unittest \
        orchestrator.tests.test_mind_endpoints -v
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

TEMPLATE = """# mind.md — Values Framework

*Default configuration. Customize by running the MindSpec interview.*

## Communication Preferences

Lead with conclusions.

## Standing Principles

Honesty is the foundation.
"""

CUSTOM = """# mind.md — Values Framework

## My Own Rules

Never bury the lede.
"""


class MindEndpoints(unittest.TestCase):
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
        self._template = os.path.join(self._tmp.name, "mind-template.md")
        with open(self._template, "w") as f:
            f.write(TEMPLATE)
        self._saved = (self.S.MIND_MD_PATH, self.S.MIND_TEMPLATE_PATH)
        self.S.MIND_MD_PATH = self._mind
        self.S.MIND_TEMPLATE_PATH = self._template
        self.client = self.S.app.test_client()

    def tearDown(self):
        if self.import_ok:
            self.S.MIND_MD_PATH, self.S.MIND_TEMPLATE_PATH = self._saved
            self._tmp.cleanup()

    def _post(self, payload):
        return self.client.post(
            "/api/mind", data=json.dumps(payload),
            content_type="application/json",
        )

    # ── GET ──────────────────────────────────────────────────────────────

    def test_get_missing_file(self):
        resp = self.client.get("/api/mind")
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.data)
        self.assertFalse(payload["exists"])
        self.assertTrue(payload["template_available"])

    def test_get_stock_template_detected(self):
        with open(self._mind, "w") as f:
            f.write(TEMPLATE)
        payload = json.loads(self.client.get("/api/mind").data)
        self.assertTrue(payload["exists"])
        self.assertTrue(payload["is_default_template"])
        self.assertEqual(payload["sections"],
                         ["Communication Preferences", "Standing Principles"])
        self.assertIn("content", payload)
        self.assertIn("mtime", payload)

    def test_get_customized_not_flagged(self):
        with open(self._mind, "w") as f:
            f.write(CUSTOM)
        payload = json.loads(self.client.get("/api/mind").data)
        self.assertTrue(payload["exists"])
        self.assertFalse(payload["is_default_template"])
        self.assertEqual(payload["sections"], ["My Own Rules"])

    # ── POST ─────────────────────────────────────────────────────────────

    def test_post_content_writes_file(self):
        resp = self._post({"content": CUSTOM})
        self.assertEqual(resp.status_code, 200, resp.data)
        payload = json.loads(resp.data)
        self.assertTrue(payload["exists"])
        with open(self._mind) as f:
            self.assertEqual(f.read(), CUSTOM)

    def test_post_empty_content_rejected(self):
        self.assertEqual(self._post({"content": "   "}).status_code, 400)
        self.assertEqual(self._post({}).status_code, 400)

    def test_create_from_template(self):
        resp = self._post({"action": "create_from_template"})
        self.assertEqual(resp.status_code, 200, resp.data)
        payload = json.loads(resp.data)
        self.assertTrue(payload["is_default_template"])
        with open(self._mind) as f:
            self.assertEqual(f.read(), TEMPLATE)

    def test_create_refuses_to_clobber_customized(self):
        with open(self._mind, "w") as f:
            f.write(CUSTOM)
        resp = self._post({"action": "create_from_template"})
        self.assertEqual(resp.status_code, 409)
        with open(self._mind) as f:
            self.assertEqual(f.read(), CUSTOM)

    def test_create_over_stock_template_allowed(self):
        with open(self._mind, "w") as f:
            f.write(TEMPLATE)
        resp = self._post({"action": "create_from_template"})
        self.assertEqual(resp.status_code, 200, resp.data)


class ValuesBlockSurvivesPipelineTrim(unittest.TestCase):
    """boot._extract_boot_behavioral_preamble keeps [YOUR VALUES — mind.md]."""

    @classmethod
    def setUpClass(cls):
        import boot  # noqa: E402 — orchestrator on sys.path above
        cls.boot = boot

    BOOT_MD = (
        "# boot\n\n"
        "§ CONSTITUTION\n\nSovereignty. Honesty.\n\n"
        "§ STANDING RULES\n\n### Anti-Sycophancy\nNo empty agreement.\n\n"
        "§ MODELS\n\nirrelevant architecture text\n\n"
        "---\n[YOUR VALUES — mind.md (authoritative; supersedes the default "
        "Mind Seeds above)]\n\n## My Own Rules\n\nNever bury the lede.\n\n"
        "## ANTI-CONFABULATION DISCIPLINE — UNIVERSAL\n\nNever invent facts.\n"
    )

    def test_values_block_kept(self):
        out = self.boot._extract_boot_behavioral_preamble(self.BOOT_MD)
        self.assertIn("[YOUR VALUES — mind.md", out)
        self.assertIn("Never bury the lede.", out)
        # Ordered before the anti-confab block, after the standing rules.
        self.assertLess(out.index("[YOUR VALUES"),
                        out.index("ANTI-CONFABULATION DISCIPLINE"))
        # Architectural sections stay trimmed.
        self.assertNotIn("irrelevant architecture text", out)

    def test_no_values_block_no_leak(self):
        stripped = self.BOOT_MD.replace(
            "---\n[YOUR VALUES — mind.md (authoritative; supersedes the "
            "default Mind Seeds above)]\n\n## My Own Rules\n\n"
            "Never bury the lede.\n\n", "")
        out = self.boot._extract_boot_behavioral_preamble(stripped)
        self.assertNotIn("[YOUR VALUES", out)
        self.assertNotIn("Never bury the lede.", out)


if __name__ == "__main__":
    unittest.main()
