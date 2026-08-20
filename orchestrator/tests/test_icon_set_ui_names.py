"""The icon set must contain every icon the UI asks for by name.

The builder only scans ``config/toolbars`` and ``config/packs`` JSON, so an
icon referenced solely from JavaScript is silently tree-shaken out and its
button renders the fallback "?" glyph at runtime. That is exactly what happened
to all four Manage Projects lifecycle buttons — Pause, Archive, Reactivate and
Restore were visually identical question marks.

These tests run against the real built artifact rather than a stub, so a future
tree-shake that drops a UI icon is caught here instead of by the user.

They do NOT rebuild ``server/static/runtime/icon-set.json`` in place, for two
reasons. That file is committed, so rebuilding it made an ordinary test run
modify the checkout — and whether it did was decided by file timestamps, which
git does not preserve, so it fired unpredictably. Worse, rebuilding first meant
the assertions only ever saw freshly generated content: a committed icon set
that was stale and missing an icon would be quietly repaired and then pass,
which is precisely the bug these tests exist to catch. The shipped file is now
read as-is, a fresh build goes to a tempdir, and the two are compared.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator import icon_set_builder as isb  # noqa: E402

_SIDEBAR_JS = Path(_REPO) / "server" / "static" / "js" / "sidebar.js"
_NODE_SHAKE = Path(_REPO) / "scripts" / "lucide-tree-shake.js"

# The only key that legitimately differs between two builds of identical input.
_VOLATILE_KEYS = {"generated_at"}

_REBUILD_HINT = (
    "Rebuild and commit it:\n"
    "    python3 -c 'from orchestrator import icon_set_builder as i; "
    "print(i.rebuild_if_stale())'"
)


def _comparable(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if k not in _VOLATILE_KEYS}


class IconSetUiNamesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # What Ora actually serves: the committed artifact, untouched.
        cls.shipped = json.loads(isb.OUT_PATH.read_text())
        # What today's sources produce, built somewhere disposable.
        cls._tmpdir = tempfile.mkdtemp(prefix="ora-icon-set-")
        fresh_path = Path(cls._tmpdir) / "icon-set.json"
        with mock.patch.object(isb, "OUT_PATH", fresh_path):
            cls.build_result = isb.rebuild_if_stale()
        cls.fresh = json.loads(fresh_path.read_text())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def test_declared_ui_icons_are_built(self):
        """Asserted against the SHIPPED set, which is what users get."""
        icons = self.shipped.get("icons") or {}
        missing = sorted(n for n in isb._UI_ICON_NAMES if n not in icons)
        self.assertEqual(
            missing, [],
            f"UI-referenced icons absent from the shipped set: {missing}. "
            f"Every button using one renders the fallback glyph. {_REBUILD_HINT}",
        )

    def test_shipped_icon_set_is_not_stale(self):
        """The committed artifact must equal a build from today's sources.

        Without this the suite could not fail for the one thing that actually
        reaches a user: a committed icon set that no longer matches the
        toolbars, packs and vendor icons it was generated from.
        """
        shipped, fresh = _comparable(self.shipped), _comparable(self.fresh)
        if shipped == fresh:
            return
        shipped_icons = set(shipped.get("icons") or {})
        fresh_icons = set(fresh.get("icons") or {})
        detail = [
            f"dropped from the shipped set: {sorted(fresh_icons - shipped_icons)}",
            f"present but no longer referenced: {sorted(shipped_icons - fresh_icons)}",
            f"changed keys: {sorted(k for k in set(shipped) | set(fresh) if shipped.get(k) != fresh.get(k))}",
        ]
        self.fail(
            "server/static/runtime/icon-set.json is out of date with its "
            "sources.\n  " + "\n  ".join(detail) + f"\n{_REBUILD_HINT}")

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
        """From the tempdir build in setUpClass — no second write anywhere."""
        self.assertEqual(self.build_result.get("unknown_names", []), [])
        self.assertEqual(self.build_result.get("missing_svgs", []), [])


if __name__ == "__main__":
    unittest.main()
