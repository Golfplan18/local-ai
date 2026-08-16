"""The icon set must contain every icon the UI asks for by name.

The builder only scans ``config/toolbars`` and ``config/packs`` JSON, so an
icon referenced solely from JavaScript is silently tree-shaken out and its
button renders the fallback "?" glyph at runtime. That is exactly what happened
to all four Manage Projects lifecycle buttons — Pause, Archive, Reactivate and
Restore were visually identical question marks.

These tests fail on the real built artifact rather than a stub, so a future
tree-shake that drops a UI icon is caught here instead of by the user.
"""
from __future__ import annotations

import json
import os
import re
import sys
import unittest
from pathlib import Path

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator import icon_set_builder as isb  # noqa: E402

_SIDEBAR_JS = Path(_REPO) / "server" / "static" / "js" / "sidebar.js"
_NODE_SHAKE = Path(_REPO) / "scripts" / "lucide-tree-shake.js"


class IconSetUiNamesTests(unittest.TestCase):
    def setUp(self):
        isb.rebuild_if_stale()
        self.payload = json.loads(isb.OUT_PATH.read_text())

    def test_declared_ui_icons_are_built(self):
        icons = self.payload.get("icons") or {}
        missing = sorted(n for n in isb._UI_ICON_NAMES if n not in icons)
        self.assertEqual(
            missing, [],
            f"UI-referenced icons absent from the built set: {missing}. "
            "Every button using one renders the fallback glyph.",
        )

    def test_every_icon_the_sidebar_requests_is_declared(self):
        """resolveProjectActionIcon('name') calls must be covered.

        Catches the failure at its source: adding a new lifecycle button
        without declaring its icon fails here rather than shipping a "?" box.
        """
        js = _SIDEBAR_JS.read_text(encoding="utf-8")
        requested = set(re.findall(r"resolveProjectActionIcon\(\s*'([a-z0-9-]+)'", js))
        self.assertTrue(requested, "expected to find icon requests in sidebar.js")
        undeclared = sorted(requested - set(isb._UI_ICON_NAMES))
        self.assertEqual(
            undeclared, [],
            f"sidebar.js requests {undeclared} but they are not in "
            "icon_set_builder._UI_ICON_NAMES, so the build will drop them.",
        )

    def test_node_and_python_builders_declare_the_same_names(self):
        """The Node script is the canonical manual rebuild path.

        If it disagrees, a manual `node lucide-tree-shake.js` silently
        reintroduces the missing-icon bug the Python builder just fixed.
        """
        js = _NODE_SHAKE.read_text(encoding="utf-8")
        m = re.search(r"var UI_ICON_NAMES = \[(.*?)\];", js, re.S)
        self.assertIsNotNone(m, "UI_ICON_NAMES not found in lucide-tree-shake.js")
        node_names = set(re.findall(r"'([a-z0-9-]+)'", m.group(1)))
        self.assertEqual(node_names, set(isb._UI_ICON_NAMES))

    def test_builder_reports_no_unknown_or_missing(self):
        result = isb.rebuild_if_stale()
        self.assertEqual(result.get("unknown_names", []), [])
        self.assertEqual(result.get("missing_svgs", []), [])


if __name__ == "__main__":
    unittest.main()
