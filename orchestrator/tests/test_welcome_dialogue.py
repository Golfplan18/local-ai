"""WELCOME Dialogue creation and exact-match copy migration."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from orchestrator import conversation_memory as cm


class WelcomeDialogueTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.sessions = Path(self._tmp.name) / "sessions"

    def tearDown(self):
        self._tmp.cleanup()

    @property
    def welcome_path(self) -> Path:
        return self.sessions / cm.WELCOME_CONVERSATION_ID / "conversation.json"

    def test_fresh_welcome_uses_dialogue_terminology(self):
        self.assertTrue(cm.ensure_welcome_thread(
            self.sessions, only_if_first_launch=False))
        envelope = json.loads(self.welcome_path.read_text(encoding="utf-8"))
        content = envelope["messages"][0]["content"]
        self.assertEqual(content, cm.WELCOME_PLACEHOLDER_BODY)
        self.assertIn("orientation Dialogue", content)
        self.assertNotIn("orientation thread", content)

    def test_exact_legacy_placeholder_self_heals(self):
        self.welcome_path.parent.mkdir(parents=True)
        self.welcome_path.write_text(json.dumps({
            "conversation_id": "welcome",
            "is_welcome": True,
            "messages": [{
                "role": "assistant",
                "content": cm._WELCOME_PLACEHOLDER_LEGACY_BODY,
            }],
        }), encoding="utf-8")

        self.assertFalse(cm.ensure_welcome_thread(
            self.sessions, only_if_first_launch=False))
        envelope = json.loads(self.welcome_path.read_text(encoding="utf-8"))
        self.assertEqual(
            envelope["messages"][0]["content"], cm.WELCOME_PLACEHOLDER_BODY)

    def test_user_edited_welcome_is_preserved(self):
        custom = "My customized welcome text"
        self.welcome_path.parent.mkdir(parents=True)
        self.welcome_path.write_text(json.dumps({
            "conversation_id": "welcome",
            "is_welcome": True,
            "messages": [{"role": "assistant", "content": custom}],
        }), encoding="utf-8")

        self.assertFalse(cm.ensure_welcome_thread(
            self.sessions, only_if_first_launch=False))
        envelope = json.loads(self.welcome_path.read_text(encoding="utf-8"))
        self.assertEqual(envelope["messages"][0]["content"], custom)


if __name__ == "__main__":
    unittest.main()
