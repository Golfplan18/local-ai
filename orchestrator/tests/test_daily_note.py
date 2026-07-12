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
import threading
import time
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
            mock.patch.object(dn._rp, "DATA_DIR_STR", str(self.data)),
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

    def _session(self, panel, display_name, tag=""):
        d = self.sessions / panel
        d.mkdir(parents=True, exist_ok=True)
        (d / "conversation.json").write_text(json.dumps(
            {"conversation_id": panel, "display_name": display_name,
             "tag": tag}))


class ClassifyTimesTests(unittest.TestCase):
    def test_classification(self):
        start, end = 1000.0, 2000.0
        self.assertEqual(dn.classify_times(1500, 1500, start, end), "created")
        self.assertEqual(dn.classify_times(500, 1500, start, end), "modified")
        self.assertIsNone(dn.classify_times(500, 2500, start, end))
        self.assertIsNone(dn.classify_times(2500, 2500, start, end))


class RuntimePathTests(unittest.TestCase):
    def test_daily_dir_uses_shared_canonical_vault_resolver(self):
        vault = Path(tempfile.gettempdir()) / "daily-note-canonical-vault"
        with mock.patch.dict(os.environ, {"ORA_VAULT": str(vault)}, clear=True):
            self.assertEqual(Path(dn.daily_dir()), vault / dn.DAILY_DIR_NAME)

    def test_conflicting_vault_aliases_are_not_silently_preferred(self):
        root = Path(tempfile.gettempdir()) / "daily-note-conflict"
        with mock.patch.dict(
            os.environ,
            {"ORA_VAULT": str(root / "a"), "ORA_VAULT_PATH": str(root / "b")},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "ORA_VAULT"):
                dn.daily_dir()


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

    def test_private_conversation_is_excluded(self):
        self._chunk("2026-06-10", "09:15", "private-conv", "Private prompt")
        self._session("private-conv", "Private title", tag="private")
        self.assertEqual(dn.collect_conversations("2026-06-10"), [])

    def test_stealth_conversation_is_excluded(self):
        self._chunk("2026-06-10", "09:15", "stealth-conv", "Stealth prompt")
        self._session("stealth-conv", "Stealth title", tag="stealth")
        self.assertEqual(dn.collect_conversations("2026-06-10"), [])

    def test_stealth_chunk_frontmatter_is_excluded_without_envelope(self):
        (self.convs / "2026-06-10_09-15_stealth.md").write_text(
            CHUNK.format(
                date="2026-06-10", panel="stealth-conv",
                gist="Stealth prompt", turn=1,
            ).replace("tags:\n", "tags:\n  - stealth\n"),
            encoding="utf-8",
        )
        self.assertEqual(dn.collect_conversations("2026-06-10"), [])


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
        self.assertIn("<!-- ora-managed-dialogue-summary:", body)
        self.assertIn('"conversation_id":"a"', body)
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


class ConversationSummaryLifecycleTests(DailyNoteBase):
    def _generated_note(self):
        self._chunk("2026-06-10", "09:15", "conv-a", "First question?")
        self._session("conv-a", "Alpha planning")
        result = dn.generate("2026-06-10")
        self.assertTrue(result.success)
        return self.vault / "Daily Notes" / "2026-06-10.md"

    def test_delete_removes_only_exact_managed_summary(self):
        target = self._generated_note()
        target.write_text(
            target.read_text() + "\nUser-authored reflection stays.\n",
            encoding="utf-8",
        )
        result = dn.reconcile_conversation_summaries(
            "conv-a", action="delete", daily_notes_dir=target.parent,
        )
        body = target.read_text(encoding="utf-8")
        self.assertEqual(result["summaries_removed"], 1)
        self.assertNotIn("Alpha planning", body)
        self.assertIn("User-authored reflection stays.", body)
        self.assertIn("conversations: 0", body)

    def test_hide_recomputes_count_from_remaining_dialogue_summaries(self):
        target = self._generated_note()
        other = dn._conversation_summary_line({
            "id": "conv-b", "name": "Beta", "exchanges": 1,
            "first": "10:00", "last": "10:00", "gist": "Other question",
        })
        body = target.read_text(encoding="utf-8")
        body = body.replace("conversations: 1", "conversations: 2")
        alpha = next(
            line for line in body.splitlines()
            if '"conversation_id":"conv-a"' in line
        )
        body = body.replace(
            alpha,
            f"{alpha}\n{other}\n- **User-authored line** stays",
        )
        target.write_text(body, encoding="utf-8")

        result = dn.reconcile_conversation_summaries(
            "conv-a", action="hide_private", daily_notes_dir=target.parent,
        )

        reconciled = target.read_text(encoding="utf-8")
        self.assertEqual(result["summaries_removed"], 1)
        self.assertIn("conversations: 1", reconciled)
        self.assertNotIn("Alpha planning", reconciled)
        self.assertIn("**Beta**", reconciled)
        self.assertIn("**User-authored line** stays", reconciled)

    def test_rename_updates_exact_title_and_provenance(self):
        target = self._generated_note()
        result = dn.reconcile_conversation_summaries(
            "conv-a",
            action="rename",
            new_display_name="New Alpha",
            previous_display_name="Alpha planning",
            daily_notes_dir=target.parent,
        )
        body = target.read_text(encoding="utf-8")
        self.assertEqual(result["summaries_renamed"], 1)
        self.assertIn("**New Alpha**", body)
        self.assertNotIn("**Alpha planning**", body)
        self.assertIn('"display_name":"New Alpha"', body)

    def test_marker_payload_cannot_inject_html_comment_terminator(self):
        line = dn._conversation_summary_line({
            "id": "conv-a", "name": "Title --> injected", "exchanges": 1,
            "first": "09:00", "last": "09:00", "gist": "question",
        })
        self.assertEqual(line.count("-->"), 2)  # visible title + real terminator
        marker = line.split("ora-managed-dialogue-summary:", 1)[1]
        self.assertEqual(marker.count("-->"), 1)
        self.assertIn("\\u003e", marker)

    def test_edited_managed_line_is_retained_and_reported(self):
        target = self._generated_note()
        body = target.read_text(encoding="utf-8")
        target.write_text(
            body.replace("**Alpha planning**", "**User edited title**"),
            encoding="utf-8",
        )
        result = dn.reconcile_conversation_summaries(
            "conv-a", action="delete", daily_notes_dir=target.parent,
        )
        self.assertTrue(result["errors"])
        self.assertIn("User edited title", target.read_text(encoding="utf-8"))

    def test_exact_legacy_line_migrates_at_runtime(self):
        target = self._generated_note()
        body = target.read_text(encoding="utf-8")
        line = next(
            item for item in body.splitlines()
            if "ora-managed-dialogue-summary" in item
        )
        visible = line.split(" <!-- ora-managed-dialogue-summary:", 1)[0]
        target.write_text(body.replace(line, visible), encoding="utf-8")
        result = dn.reconcile_conversation_summaries(
            "conv-a",
            action="rename",
            new_display_name="Migrated Alpha",
            previous_display_name="Alpha planning",
            daily_notes_dir=target.parent,
        )
        migrated = target.read_text(encoding="utf-8")
        self.assertEqual(result["legacy_summaries_migrated"], 1)
        self.assertIn("**Migrated Alpha**", migrated)
        self.assertIn("ora-managed-dialogue-summary", migrated)

    def test_edited_legacy_title_is_retained_and_reported_ambiguous(self):
        target = self._generated_note()
        body = target.read_text(encoding="utf-8")
        line = next(
            item for item in body.splitlines()
            if "ora-managed-dialogue-summary" in item
        )
        visible = line.split(" <!-- ora-managed-dialogue-summary:", 1)[0]
        target.write_text(
            body.replace(line, visible.replace("Alpha planning", "User title")),
            encoding="utf-8",
        )
        result = dn.reconcile_conversation_summaries(
            "conv-a", action="delete", daily_notes_dir=target.parent,
        )
        self.assertTrue(result["errors"])
        self.assertIn("User title", target.read_text(encoding="utf-8"))

    def test_legacy_private_summary_is_still_exactly_deletable(self):
        target = self._generated_note()
        body = target.read_text(encoding="utf-8")
        line = next(
            item for item in body.splitlines()
            if "ora-managed-dialogue-summary" in item
        )
        visible = line.split(" <!-- ora-managed-dialogue-summary:", 1)[0]
        target.write_text(body.replace(line, visible), encoding="utf-8")
        self._session("conv-a", "Alpha planning", tag="private")
        result = dn.reconcile_conversation_summaries(
            "conv-a", action="delete", daily_notes_dir=target.parent,
        )
        self.assertEqual(result["summaries_removed"], 1)
        self.assertNotIn("Alpha planning", target.read_text(encoding="utf-8"))

    def test_generate_and_delete_share_one_cross_process_lock(self):
        collection_started = threading.Event()
        release_collection = threading.Event()
        delete_finished = threading.Event()
        failures: list[BaseException] = []

        conversations = [{
            "id": "conv-race", "name": "Race title", "exchanges": 1,
            "first": "09:00", "last": "09:00", "gist": "race",
        }]

        def blocked_collect(_date):
            collection_started.set()
            if not release_collection.wait(timeout=5):
                raise TimeoutError("test collection release timed out")
            return conversations

        def run_generate():
            try:
                dn.generate("2026-06-10")
            except BaseException as exc:  # pragma: no cover - assertion aid
                failures.append(exc)

        def run_delete():
            try:
                dn.reconcile_conversation_summaries(
                    "conv-race", action="delete",
                    daily_notes_dir=self.vault / "Daily Notes",
                )
            except BaseException as exc:  # pragma: no cover - assertion aid
                failures.append(exc)
            finally:
                delete_finished.set()

        with (
            mock.patch.object(dn, "collect_conversations", side_effect=blocked_collect),
            mock.patch.object(dn, "collect_vault_activity", return_value=([], [])),
            mock.patch.object(dn, "collect_ora_activity", return_value=[]),
        ):
            generator = threading.Thread(target=run_generate)
            generator.start()
            self.assertTrue(collection_started.wait(timeout=3))
            deleter = threading.Thread(target=run_delete)
            deleter.start()
            time.sleep(0.15)
            self.assertFalse(delete_finished.is_set())
            release_collection.set()
            generator.join(timeout=5)
            deleter.join(timeout=5)

        self.assertEqual(failures, [])
        self.assertTrue(delete_finished.is_set())
        target = self.vault / "Daily Notes" / "2026-06-10.md"
        self.assertNotIn("Race title", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
