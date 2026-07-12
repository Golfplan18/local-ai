"""Tests for daily_note — auto-generated vault daily note (temporal index).

Paths are redirected into a tempdir via module constants + ORA_VAULT_PATH.

Run::

    /opt/homebrew/bin/python3 -m unittest orchestrator.tests.test_daily_note -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))
sys.path.insert(0, str(ORCHESTRATOR.parent))

from orchestrator.tools import daily_note as dn  # noqa: E402

CHUNK = """---
nexus:
type: chat
tags:
date created: {date}
date modified: {date}
---

## Context

Local AI session on {date}, panel '{panel}', model test-model. Turn {turn} of an ongoing conversation. The user asked: {gist}

## Exchange

**User:**

{gist}

**Assistant:**

Reply text.
"""


class DailyNoteBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.vault = root / "vault"
        self.convs = root / "conversations"
        self.sessions = root / "sessions"
        self.data = root / "data"
        for d in (self.vault, self.convs, self.sessions, self.data):
            d.mkdir()

        self.patches = [
            mock.patch.object(dn, "CONVERSATIONS_DIR", str(self.convs)),
            mock.patch.object(dn, "SESSIONS_DIR", str(self.sessions)),
            mock.patch.object(dn, "DATA_DIR", str(self.data)),
            mock.patch.dict(os.environ, {"ORA_VAULT_PATH": str(self.vault)}),
        ]
        for p in self.patches:
            p.start()
        self.addCleanup(self.tmp.cleanup)
        for p in self.patches:
            self.addCleanup(p.stop)

    def _chunk(self, date, hhmm, panel, gist, turn=1, slug="x"):
        name = f"{date}_{hhmm.replace(':', '-')}_{slug}.md"
        (self.convs / name).write_text(
            CHUNK.format(date=date, panel=panel, gist=gist, turn=turn))

    def _session(self, panel, display_name):
        d = self.sessions / panel
        d.mkdir(parents=True, exist_ok=True)
        (d / "conversation.json").write_text(json.dumps(
            {"conversation_id": panel, "display_name": display_name}))


class ClassifyTimesTests(unittest.TestCase):
    def test_classification(self):
        start, end = 1000.0, 2000.0
        self.assertEqual(dn.classify_times(1500, 1500, start, end), "created")
        self.assertEqual(dn.classify_times(500, 1500, start, end), "modified")
        self.assertIsNone(dn.classify_times(500, 2500, start, end))
        self.assertIsNone(dn.classify_times(2500, 2500, start, end))


class CollectConversationsTests(DailyNoteBase):
    def test_groups_chunks_by_panel(self):
        self._chunk("2026-06-10", "09:15", "proj-alpha", "First question?", slug="a1")
        self._chunk("2026-06-10", "10:30", "proj-alpha", "Follow-up.", turn=2, slug="a2")
        self._chunk("2026-06-10", "11:00", "other-conv", "Different topic.", slug="b1")
        self._chunk("2026-06-11", "08:00", "proj-alpha", "Wrong day.", slug="c1")
        self._session("proj-alpha", "Alpha planning")

        convs = dn.collect_conversations("2026-06-10")
        self.assertEqual(len(convs), 2)
        alpha = next(c for c in convs if c["id"] == "proj-alpha")
        self.assertEqual(alpha["name"], "Alpha planning")
        self.assertEqual(alpha["exchanges"], 2)
        self.assertEqual(alpha["first"], "09:15")
        self.assertEqual(alpha["last"], "10:30")
        self.assertEqual(alpha["gist"], "First question?")
        other = next(c for c in convs if c["id"] == "other-conv")
        self.assertEqual(other["name"], "other-conv")  # no envelope → id fallback

    def test_recovered_chunk_uses_yaml_conversation_id(self):
        (self.convs / "2026-06-10_14-44_recovered_x.md").write_text(
            "---\nconversation_id: main\nstatus: errored\n---\n# Recovered\n")
        convs = dn.collect_conversations("2026-06-10")
        self.assertEqual(len(convs), 1)
        self.assertEqual(convs[0]["id"], "main")


class RenderNoteTests(unittest.TestCase):
    def test_full_note_shape(self):
        body = dn.render_note(
            "2026-06-10",
            [{"id": "a", "name": "Alpha", "exchanges": 2,
              "first": "09:15", "last": "10:30", "gist": "First question?"}],
            ["New Note"], ["Old Note"],
            ["Oversight events: 3× FrameworkComplete"])
        self.assertIn("type: daily-note", body)
        self.assertIn("date: 2026-06-10", body)
        self.assertIn("[[2026-06-09]] · [[2026-06-11]]", body)
        self.assertIn("## Dialogues", body)
        self.assertIn("**Alpha** — 2 exchanges, 09:15–10:30", body)
        self.assertIn("[[New Note]]", body)
        self.assertIn("[[Old Note]]", body)
        self.assertIn("3× FrameworkComplete", body)

    def test_empty_sections_omitted(self):
        body = dn.render_note("2026-06-10", [], [], [], [])
        self.assertNotIn("## Dialogues", body)
        self.assertNotIn("## Vault activity", body)
        self.assertNotIn("## Ora activity", body)
        self.assertIn("[[2026-06-09]]", body)  # nav always present


class GitVaultActivityTests(DailyNoteBase):
    def _git(self, *args, env=None):
        import subprocess
        e = dict(os.environ)
        if env:
            e.update(env)
        subprocess.run(["git", "-C", str(self.vault), *args],
                       capture_output=True, check=True, env=e)

    def test_git_history_drives_activity(self):
        date_env = {"GIT_AUTHOR_DATE": "2026-06-10T10:00:00",
                    "GIT_COMMITTER_DATE": "2026-06-10T10:00:00"}
        self._git("init", "-q")
        self._git("config", "user.email", "t@t")
        self._git("config", "user.name", "t")
        (self.vault / "Pre-existing.md").write_text("v1")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "seed",
                  env={"GIT_AUTHOR_DATE": "2026-06-01T10:00:00",
                       "GIT_COMMITTER_DATE": "2026-06-01T10:00:00"})
        (self.vault / "Born Today.md").write_text("new")
        (self.vault / "Reference — Em Dash Name.md").write_text("non-ascii path")
        (self.vault / "Pre-existing.md").write_text("v2")
        msi = self.vault / "MSI News"
        msi.mkdir()
        (msi / "mirror-article.md").write_text("synced")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "day work", env=date_env)

        created, modified = dn.collect_vault_activity("2026-06-10")
        self.assertEqual(created, ["Born Today", "Reference — Em Dash Name"])
        self.assertEqual(modified, ["Pre-existing"])  # MSI News excluded

    def test_non_git_vault_falls_back_to_stat_scan(self):
        self.assertIsNone(dn.collect_vault_activity_git("2026-06-10"))
        (self.vault / "Fresh.md").write_text("x")
        today = datetime.now().strftime("%Y-%m-%d")
        created, _ = dn.collect_vault_activity(today)
        self.assertIn("Fresh", created)


class GenerateTests(DailyNoteBase):
    def test_generates_yesterday_by_default(self):
        res = dn.generate()
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        self.assertTrue(res.success)
        self.assertTrue((self.vault / "Daily Notes" / f"{yesterday}.md").exists())

    def test_skip_existing_unless_forced(self):
        first = dn.generate("2026-06-10")
        self.assertTrue(first.success)
        target = self.vault / "Daily Notes" / "2026-06-10.md"
        target.write_text("user edited this")
        second = dn.generate("2026-06-10")
        self.assertEqual(target.read_text(), "user edited this")
        self.assertTrue(second.stats.get("skipped"))
        forced = dn.generate("2026-06-10", force=True)
        self.assertTrue(forced.success)
        self.assertIn("type: daily-note", target.read_text())

    def test_vault_activity_for_today(self):
        # Files created in the test are born "today" — generate today's
        # note and they must appear as Created wikilinks. The Daily Notes
        # folder itself is excluded from the scan.
        (self.vault / "Fresh Note.md").write_text("# hi")
        today = datetime.now().strftime("%Y-%m-%d")
        res = dn.generate(today)
        body = (self.vault / "Daily Notes" / f"{today}.md").read_text()
        self.assertIn("[[Fresh Note]]", body)
        self.assertNotIn(f"[[{today}]] —", body)
        self.assertTrue(res.success)

    def test_ora_activity_from_jsonl(self):
        ov = self.data / "oversight"
        ov.mkdir()
        (ov / "events.jsonl").write_text(json.dumps(
            {"event_type": "FrameworkComplete", "emitted_at": "2026-06-10T12:00:00Z"}) + "\n")
        (self.data / "maintenance-results.jsonl").write_text(json.dumps(
            {"task": "orphan_cleanup", "ran_at": "2026-06-10T13:00:00Z",
             "success": True, "message": "ok"}) + "\n")
        dn.generate("2026-06-10")
        body = (self.vault / "Daily Notes" / "2026-06-10.md").read_text()
        self.assertIn("1× FrameworkComplete", body)
        self.assertIn("orphan_cleanup — ok", body)

    def test_invalid_date_fails_safely(self):
        res = dn.generate("not-a-date")
        self.assertFalse(res.success)

    def test_task_entry_point_returns_result_shape(self):
        res = dn.task_daily_note()
        for attr in ("success", "message", "stats", "alerts", "duration_seconds"):
            self.assertTrue(hasattr(res, attr))


if __name__ == "__main__":
    unittest.main()
