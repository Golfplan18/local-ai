"""Tests for the G1.36 honne/tatemae input toggle: server._apply_style_audience
folds the active project's interaction_style onto the per-turn style override
when the turn is marked 'internal'."""

from __future__ import annotations

import os
import sys
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (_REPO, os.path.join(_REPO, "server"), os.path.join(_REPO, "orchestrator")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from orchestrator.embedding import install_test_stub  # noqa: E402
install_test_stub()
import server  # noqa: E402


class StyleAudienceTests(unittest.TestCase):
    def setUp(self):
        import orchestrator.active_project as ap
        import orchestrator.project_meta as pm
        self.ap, self.pm = ap, pm
        self._orig = (ap.get_active_project, pm.read_project_meta)

    def tearDown(self):
        self.ap.get_active_project, self.pm.read_project_meta = self._orig

    def _patch(self, nexus, rec):
        self.ap.get_active_project = lambda: nexus
        self.pm.read_project_meta = lambda n, *a, **k: rec

    def test_external_is_noop(self):
        self._patch("proj", {"interaction_style": "conversational"})
        self.assertIsNone(server._apply_style_audience(None, "external"))
        self.assertIsNone(server._apply_style_audience(None, ""))

    def test_internal_folds_interaction_style(self):
        self._patch("proj", {"interaction_style": "conversational"})
        out = server._apply_style_audience(None, "internal")
        self.assertEqual(out.get("style_id"), "conversational")

    def test_internal_preserves_other_extra_context(self):
        self._patch("proj", {"interaction_style": "conversational"})
        out = server._apply_style_audience({"image_path": "/x.png"}, "internal")
        self.assertEqual(out.get("style_id"), "conversational")
        self.assertEqual(out.get("image_path"), "/x.png")

    def test_explicit_style_override_wins(self):
        # A /style one-off already on extra_context is not clobbered.
        self._patch("proj", {"interaction_style": "conversational"})
        out = server._apply_style_audience({"style_id": "from-slash"}, "internal")
        self.assertEqual(out.get("style_id"), "from-slash")

    def test_commons_is_noop(self):
        self._patch("commons", {"interaction_style": "conversational"})
        self.assertIsNone(server._apply_style_audience(None, "internal"))

    def test_legacy_general_is_noop(self):
        self._patch("general", {"interaction_style": "conversational"})
        self.assertIsNone(server._apply_style_audience(None, "internal"))

    def test_no_interaction_style_is_noop(self):
        self._patch("proj", {"interaction_style": ""})
        self.assertIsNone(server._apply_style_audience(None, "internal"))

    def test_missing_record_is_noop(self):
        self._patch("proj", None)
        self.assertIsNone(server._apply_style_audience(None, "internal"))


if __name__ == "__main__":
    unittest.main()
