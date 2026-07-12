"""Tests for the G1.33 server-side project filter on GET /api/conversations.

General (absent / "general") is all-inclusive; a project narrows the
pinned/unread/active groups to its threads, while errored + pending stay
global (they pierce the filter — the locked switcher spec).
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (_REPO, os.path.join(_REPO, "server"), os.path.join(_REPO, "orchestrator")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from orchestrator.embedding import install_test_stub  # noqa: E402
install_test_stub()
import server  # noqa: E402  (server imports conversation_memory as a top-level module)
# Import the SAME top-level instance the endpoint reads, not
# orchestrator.conversation_memory (a separate module object with its own
# _DEFAULT_SESSIONS_ROOT) — otherwise patching the root wouldn't redirect it.
import conversation_memory as cm  # noqa: E402


class ConversationsProjectFilterTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self._orig_root = cm._DEFAULT_SESSIONS_ROOT
        cm._DEFAULT_SESSIONS_ROOT = self.root
        cm.save_turn_spatial_state("c-general", "u", "a", sessions_root=self.root)
        cm.save_turn_spatial_state("c-book", "u", "a", project_ids=["book"], sessions_root=self.root)
        cm.save_turn_spatial_state("c-law", "u", "a", project_ids=["law"], sessions_root=self.root)
        self.client = server.app.test_client()

    def tearDown(self):
        cm._DEFAULT_SESSIONS_ROOT = self._orig_root
        self._tmp.cleanup()

    def _ids(self, payload):
        ids = set()
        for grp in ("pinned", "errored", "pending", "unread", "active"):
            for r in payload.get(grp, []):
                ids.add(r["conversation_id"])
        return ids

    def test_commons_shows_all(self):
        for url in ("/api/conversations", "/api/conversations?project_id=commons"):
            payload = json.loads(self.client.get(url).data)
            ids = self._ids(payload)
            self.assertIn("c-general", ids)
            self.assertIn("c-book", ids)
            self.assertIn("c-law", ids)

    def test_legacy_general_shows_all(self):
        payload = json.loads(self.client.get("/api/conversations?project_id=general").data)
        ids = self._ids(payload)
        self.assertIn("c-general", ids)
        self.assertIn("c-book", ids)
        self.assertIn("c-law", ids)

    def test_project_filters_to_subset(self):
        payload = json.loads(self.client.get("/api/conversations?project_id=book").data)
        ids = self._ids(payload)
        self.assertIn("c-book", ids)
        self.assertNotIn("c-law", ids)
        self.assertNotIn("c-general", ids)

    def test_errored_pierces_filter(self):
        # Mark c-law (in project 'law') errored; it must still appear when
        # filtering to 'book' — errored is global.
        p = self.root / "c-law" / "conversation.json"
        data = json.loads(p.read_text())
        data["last_status"] = "errored"
        p.write_text(json.dumps(data))
        payload = json.loads(self.client.get("/api/conversations?project_id=book").data)
        errored_ids = {r["conversation_id"] for r in payload.get("errored", [])}
        self.assertIn("c-law", errored_ids)
        self.assertIn("c-book", self._ids(payload))  # book's own thread still shows


if __name__ == "__main__":
    unittest.main()
