#!/usr/bin/env python3
"""Regression checks for the mode/lens integrity audit."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
AUDIT_PATH = REPO_ROOT / "scripts" / "lens_integrity_audit.py"

spec = importlib.util.spec_from_file_location("lens_integrity_audit", AUDIT_PATH)
audit = importlib.util.module_from_spec(spec)
sys.modules["lens_integrity_audit"] = audit
assert spec.loader is not None
spec.loader.exec_module(audit)


class LensIntegrityAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = audit.build_report(REPO_ROOT)

    def _unresolved_ids(self) -> set[str]:
        return {row["id"] for row in self.report["unresolved_by_id"]}

    def _mode_row(self, mode_id: str) -> dict:
        return next(row for row in self.report["modes"] if row["mode"] == mode_id)

    def test_high_impact_foundational_lenses_resolve(self):
        unresolved = self._unresolved_ids()
        self.assertNotIn("kahneman-tversky-bias-catalog", unresolved)
        self.assertNotIn("knightian-risk-uncertainty-ambiguity", unresolved)

    def test_next_repair_batch_lenses_resolve(self):
        unresolved = self._unresolved_ids()
        self.assertNotIn("rumelt-strategy-kernel", unresolved)
        self.assertNotIn("meadows-twelve-leverage-points", unresolved)
        self.assertNotIn("senge-system-archetypes", unresolved)
        self.assertNotIn("fgl-fear-greed-laziness", unresolved)
        self.assertNotIn("voss-tactical-empathy", unresolved)
        self.assertNotIn("shackel-motte-and-bailey", unresolved)
        self.assertNotIn("bordwell-poetics-of-cinema", unresolved)
        self.assertNotIn("public-choice-theory", unresolved)
        self.assertNotIn("cda-fairclough-presupposition-and-nominalization", unresolved)
        self.assertNotIn("iyengar-episodic-thematic", unresolved)
        self.assertNotIn("lewicki-negotiation-frameworks", unresolved)
        self.assertNotIn("cross-domain-analogical-mapping", unresolved)
        self.assertNotIn("debono-ago", unresolved)
        self.assertNotIn("failure-mode-literature", unresolved)
        self.assertNotIn("post-mortem-analyses", unresolved)
        self.assertNotIn("adversarial-case-studies", unresolved)
        self.assertNotIn("opv-other-points-of-view", unresolved)
        self.assertNotIn("rapoport-rules-of-engagement", unresolved)
        self.assertNotIn("novak-concept-map-tradition", unresolved)
        self.assertNotIn("sterman-system-dynamics-modelling", unresolved)
        self.assertNotIn("forrester-industrial-dynamics", unresolved)
        self.assertNotIn("heuer-ach-diagnosticity", unresolved)
        self.assertNotIn("heuer-ach-methodology", unresolved)
        self.assertNotIn("debono-pmi", unresolved)
        self.assertNotIn("de-bono-consequence-and-sequel", unresolved)
        self.assertNotIn("expected-utility-theory", unresolved)
        self.assertNotIn("hegelian-dialectic-aufheben", unresolved)
        self.assertNotIn("lakatos-hard-core-protective-belt", unresolved)
        self.assertNotIn("shell-scenario-method", unresolved)
        self.assertNotIn("tversky-spatial-correspondence-principles", unresolved)
        self.assertNotIn("game-theory-equilibrium-concepts", unresolved)
        self.assertNotIn("schelling-strategy-of-conflict", unresolved)
        self.assertNotIn("rittel-webber-wicked-characteristics", unresolved)
        self.assertNotIn("kuhn-paradigm-incommensurability", unresolved)
        self.assertNotIn("ordinary-language-philosophy-tradition", unresolved)
        self.assertNotIn("structural-relationship-taxonomy", unresolved)

    def test_no_required_lens_dependencies_are_unresolved(self):
        required = [
            item
            for row in self.report["unresolved_by_id"]
            for item in row["modes"]
            if item["category"] == "required"
        ]
        self.assertEqual(required, [])

    def test_no_foundational_lens_dependencies_are_unresolved(self):
        foundational = [
            item
            for row in self.report["unresolved_by_id"]
            for item in row["modes"]
            if item["category"] == "foundational"
        ]
        self.assertEqual(foundational, [])

    def test_root_cause_rename_repairs_are_direct_dependencies(self):
        row = self._mode_row("root-cause-analysis")
        direct = {item["id"]: item["category"] for item in row["direct"]}
        self.assertEqual(direct["fishbone-diagram"], "required")
        self.assertEqual(direct["five-whys"], "required")
        self.assertEqual(direct["swiss-cheese-model"], "optional")
        unresolved = {item["id"] for item in row["unresolved"]}
        self.assertNotIn("ishikawa-fishbone-frameworks", unresolved)
        self.assertNotIn("five-whys-protocol", unresolved)
        self.assertNotIn("reason-swiss-cheese-model", unresolved)

    def test_runtime_now_exposes_more_resolved_than_unresolved_links(self):
        summary = self.report["summary"]
        self.assertEqual(summary["unresolved_declared_links"], 0)
        self.assertGreater(
            summary["direct_resolved_links"],
            summary["unresolved_declared_links"],
        )
        self.assertGreater(summary["visible_links"], 300)


if __name__ == "__main__":
    unittest.main()
