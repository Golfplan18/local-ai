"""Tests for resolution_chain.py — multi-turn resolution discussion.

Covers:
  - Marker detection (positive + negative)
  - Marker payload parsing (queue_id + alternative)
  - Options block rendering (option 3 only when alternative is substantive)
  - start_resolution: creates conversation envelope, links queue entry
  - continue_resolution: numeric input commits; free text continues discussion
  - Mocked summarizer returning ALTERNATIVE block → option 3 appears
  - Resolved discussion conversation gets "(resolved)" suffix
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = os.path.dirname(HERE)
if ORCH not in sys.path:
    sys.path.insert(0, ORCH)


def _patch_paths(test_case: unittest.TestCase, tmpdir: str) -> dict:
    paths = {
        "data_dir": os.path.join(tmpdir, "oversight"),
        "queue": os.path.join(tmpdir, "oversight/human-queue.jsonl"),
        "reeval": os.path.join(tmpdir, "oversight/reeval-queue.jsonl"),
        "sessions": os.path.join(tmpdir, "sessions"),
        "ped_pointer_dir": os.path.join(tmpdir, "oversight"),
    }
    os.makedirs(paths["data_dir"], exist_ok=True)
    os.makedirs(paths["sessions"], exist_ok=True)
    import oversight_queue
    import oversight_actions
    import ped_watcher
    test_case._patches = [
        mock.patch.object(oversight_queue, "OVERSIGHT_DATA_DIR", paths["data_dir"]),
        mock.patch.object(oversight_queue, "REEVAL_QUEUE_PATH", paths["reeval"]),
        mock.patch.object(oversight_queue, "SESSIONS_ROOT", paths["sessions"]),
        mock.patch.object(oversight_queue, "HUMAN_QUEUE_PATH", paths["queue"]),
        mock.patch.object(oversight_actions, "HUMAN_QUEUE_PATH", paths["queue"]),
        mock.patch.object(oversight_actions, "OVERSIGHT_DATA_DIR", paths["data_dir"]),
        mock.patch.object(ped_watcher, "OVERSIGHT_DATA_DIR", paths["data_dir"]),
    ]
    for p in test_case._patches:
        p.start()
    return paths


# ---------- Marker detection ----------

class TestIsResolutionContinuation(unittest.TestCase):

    def test_no_history(self):
        from resolution_chain import is_resolution_continuation
        self.assertIsNone(is_resolution_continuation([]))
        self.assertIsNone(is_resolution_continuation(None))  # type: ignore

    def test_marker_in_last_assistant_message(self):
        from resolution_chain import is_resolution_continuation
        history = [
            {"role": "user", "content": "/discuss"},
            {
                "role": "assistant",
                "content": (
                    "What's your concern?\n\n"
                    '<!-- ora-resolution: {"queue_id": "abc123", "alternative": "alt text"} -->'
                ),
            },
        ]
        ctx = is_resolution_continuation(history)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.queue_id, "abc123")
        self.assertEqual(ctx.last_alternative, "alt text")

    def test_no_marker_returns_none(self):
        from resolution_chain import is_resolution_continuation
        history = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello, no marker here"},
        ]
        self.assertIsNone(is_resolution_continuation(history))

    def test_malformed_payload_returns_none(self):
        from resolution_chain import is_resolution_continuation
        history = [{
            "role": "assistant",
            "content": "<!-- ora-resolution: {bad json -->",
        }]
        self.assertIsNone(is_resolution_continuation(history))


# ---------- Options block rendering ----------

class TestOptionsBlock(unittest.TestCase):

    def test_options_without_alternative_omits_option_3(self):
        from resolution_chain import _render_options_block
        text = _render_options_block(alternative="")
        self.assertIn("1. Approve as proposed", text)
        self.assertIn("2. Deny", text)
        self.assertNotIn("3. Apply this alternative", text)

    def test_options_with_alternative_shows_option_3(self):
        from resolution_chain import _render_options_block
        alt = "Use a different definition: customer adoption is measured by repeat purchase rate."
        text = _render_options_block(alternative=alt)
        self.assertIn("3. Apply this alternative", text)
        self.assertIn("repeat purchase rate", text)


# ---------- _split_response ----------

class TestSplitResponse(unittest.TestCase):

    def test_extracts_alternative(self):
        from resolution_chain import _split_response
        response = (
            "I think your concern is valid. Here's what I'd propose.\n\n"
            "ALTERNATIVE:\n"
            "Apply a redefinition that emphasizes repeat-purchase rather than first-purchase."
        )
        discussion, alternative = _split_response(response)
        self.assertIn("Here's what I'd propose", discussion)
        self.assertIn("repeat-purchase", alternative)

    def test_none_placeholder_treated_as_empty(self):
        from resolution_chain import _split_response
        response = "Some discussion.\n\nALTERNATIVE:\n(none)"
        _, alternative = _split_response(response)
        self.assertEqual(alternative, "")

    def test_no_alternative_block_returns_full_response(self):
        from resolution_chain import _split_response
        response = "Just discussion text, no structured tail."
        discussion, alternative = _split_response(response)
        self.assertEqual(alternative, "")
        self.assertIn("Just discussion", discussion)


# ---------- start_resolution ----------

class TestStartResolution(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ora-rc-start-")
        self.paths = _patch_paths(self, self.tmp)
        # Seed a paused entry
        import oversight_queue
        with mock.patch.object(
            oversight_queue, "_generate_name", return_value="Redefinition: testproj",
        ):
            self.entry = oversight_queue.add_entry({
                "event": {
                    "event_type": "MilestoneClaimed",
                    "project_nexus": "testproj",
                    "milestone_text": "Initial draft is complete",
                },
                "verdict": {"reasoning": "Underlying definition was wrong."},
                "redefinition": True,
            }, config={})

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unknown_id_raises(self):
        from resolution_chain import start_resolution
        with self.assertRaises(ValueError):
            start_resolution("does-not-exist", sessions_root=self.paths["sessions"])

    def test_creates_conversation_with_seed_message(self):
        from resolution_chain import start_resolution, MARKER_PATTERN
        result = start_resolution(self.entry.id, sessions_root=self.paths["sessions"])
        self.assertIn("conversation_id", result)
        self.assertFalse(result.get("reused"))

        env_path = os.path.join(
            self.paths["sessions"], result["conversation_id"], "conversation.json",
        )
        self.assertTrue(os.path.isfile(env_path))
        with open(env_path) as f:
            env = json.load(f)
        self.assertEqual(env["display_name"], "Resolve: Redefinition: testproj")
        self.assertEqual(len(env["messages"]), 1)
        first = env["messages"][0]
        self.assertEqual(first["role"], "assistant")
        self.assertIn("Underlying definition", first["content"])
        self.assertIn("Resolution options", first["content"])
        self.assertIsNotNone(MARKER_PATTERN.search(first["content"]))

    def test_re_open_returns_existing_conversation(self):
        from resolution_chain import start_resolution
        first = start_resolution(self.entry.id, sessions_root=self.paths["sessions"])
        second = start_resolution(self.entry.id, sessions_root=self.paths["sessions"])
        self.assertEqual(first["conversation_id"], second["conversation_id"])
        self.assertTrue(second.get("reused"))

    def test_links_discussion_to_queue_entry(self):
        from resolution_chain import start_resolution
        from oversight_queue import find_paused_by_id
        result = start_resolution(self.entry.id, sessions_root=self.paths["sessions"])
        e = find_paused_by_id(self.entry.id)
        self.assertEqual(e.discussion_conversation_id, result["conversation_id"])
        self.assertEqual(e.engagement, "discussing")


# ---------- continue_resolution ----------

class TestContinueResolution(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ora-rc-cont-")
        self.paths = _patch_paths(self, self.tmp)
        import oversight_queue
        with mock.patch.object(
            oversight_queue, "_generate_name", return_value="Redefinition: alpha",
        ):
            self.entry = oversight_queue.add_entry({
                "event": {
                    "event_type": "MilestoneClaimed",
                    "project_nexus": "alpha",
                },
                "verdict": {"reasoning": "..."},
                "redefinition": True,
            }, config={})

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_input_1_attempts_approve_as_proposed(self):
        from resolution_chain import continue_resolution, ContinuationContext
        ctx = ContinuationContext(queue_id=self.entry.id, last_alternative="")
        # Mock approve_redefinition to return success
        with mock.patch("redefinition_handler.approve_redefinition") as m_approve:
            from redefinition_handler import RedefinitionResult
            m_approve.return_value = RedefinitionResult(
                success=True,
                archived_path="/tmp/archived.md",
                new_ped_path="/tmp/new.md",
                reeval_task_id="reeval-x",
            )
            text = continue_resolution(ctx, [], "1")
        m_approve.assert_called_once()
        self.assertIn("Approved as proposed", text)

    def test_input_2_attempts_deny(self):
        from resolution_chain import continue_resolution, ContinuationContext
        ctx = ContinuationContext(queue_id=self.entry.id, last_alternative="")
        with mock.patch("redefinition_handler.deny_redefinition") as m_deny:
            from redefinition_handler import RedefinitionResult
            m_deny.return_value = RedefinitionResult(success=True)
            history = [
                {"role": "user", "content": "I disagree because the metric is fine."},
                {"role": "assistant", "content": "noted"},
            ]
            text = continue_resolution(ctx, history, "2")
        m_deny.assert_called_once()
        # Reason was extracted from the user history (passed as kwarg)
        _, kwargs = m_deny.call_args
        self.assertIn("metric is fine", kwargs.get("reason", ""))
        self.assertIn("Denied", text)

    def test_input_3_without_alternative_returns_warning(self):
        from resolution_chain import continue_resolution, ContinuationContext
        ctx = ContinuationContext(queue_id=self.entry.id, last_alternative="")
        text = continue_resolution(ctx, [], "3")
        self.assertIn("no alternative content", text)

    def test_input_3_with_alternative_applies_it(self):
        from resolution_chain import continue_resolution, ContinuationContext
        ctx = ContinuationContext(
            queue_id=self.entry.id,
            last_alternative="Apply this revised definition...",
        )
        with mock.patch("redefinition_handler.approve_redefinition") as m_approve:
            from redefinition_handler import RedefinitionResult
            m_approve.return_value = RedefinitionResult(
                success=True,
                archived_path="/tmp/a.md",
                new_ped_path="/tmp/n.md",
                reeval_task_id="re-1",
            )
            text = continue_resolution(ctx, [], "3")
        # Confirm the alternative was passed as proposed_definition
        _, kwargs = m_approve.call_args
        self.assertIn("revised definition", kwargs.get("proposed_definition", "") or "")
        self.assertIn("Applied alternative", text)

    def test_free_text_continues_discussion_with_marker(self):
        from resolution_chain import (
            continue_resolution, ContinuationContext, MARKER_PATTERN,
        )
        ctx = ContinuationContext(queue_id=self.entry.id, last_alternative="")
        with mock.patch("resolution_chain._generate_discussion_turn") as m_disc:
            m_disc.return_value = (
                "Here's my response.\n\n"
                "**Resolution options:**\n1. Approve as proposed\n2. Deny\n\n"
                "Type 1, 2, or 3 to commit. Anything else continues the discussion.\n\n"
                '<!-- ora-resolution: {"queue_id": "' + self.entry.id + '", "alternative": ""} -->'
            )
            text = continue_resolution(ctx, [], "what about X?")
        self.assertIn("response", text)
        self.assertIsNotNone(MARKER_PATTERN.search(text))


# ---------- Resolved suffix ----------

class TestResolvedSuffix(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ora-rc-resolve-")
        self.sessions_root = os.path.join(self.tmp, "sessions")
        os.makedirs(self.sessions_root, exist_ok=True)
        # Override the resolution_chain default sessions root
        self._patch = mock.patch.dict(os.environ, {"HOME": self.tmp})
        self._patch.start()
        # Create a conversation envelope to mark
        self.cid = "resolve-xyz"
        conv_dir = os.path.join(self.sessions_root, self.cid)
        os.makedirs(conv_dir, exist_ok=True)
        with open(os.path.join(conv_dir, "conversation.json"), "w") as f:
            json.dump({
                "conversation_id": self.cid,
                "display_name": "Resolve: my entry",
                "tag": "",
                "created": "...",
                "messages": [],
            }, f)
        # Move into a place the function will find — create the path
        # ~/ora/sessions/<cid>/conversation.json
        self.real_root = os.path.join(self.tmp, "ora", "sessions")
        os.makedirs(self.real_root, exist_ok=True)
        shutil.copytree(
            os.path.join(self.sessions_root, self.cid),
            os.path.join(self.real_root, self.cid),
        )

    def tearDown(self):
        self._patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_appends_resolved_suffix(self):
        import resolution_chain
        resolution_chain._mark_conversation_resolved(self.cid)
        env_path = os.path.join(self.real_root, self.cid, "conversation.json")
        with open(env_path) as f:
            env = json.load(f)
        self.assertEqual(env["display_name"], "Resolve: my entry (resolved)")

    def test_idempotent(self):
        import resolution_chain
        resolution_chain._mark_conversation_resolved(self.cid)
        resolution_chain._mark_conversation_resolved(self.cid)
        env_path = os.path.join(self.real_root, self.cid, "conversation.json")
        with open(env_path) as f:
            env = json.load(f)
        self.assertEqual(env["display_name"], "Resolve: my entry (resolved)")


if __name__ == "__main__":
    unittest.main()
