"""Tests for G1.33 project membership on the conversation envelope.

Covers ``project_ids`` end-to-end in ``conversation_memory``:
  - set on a NEW envelope from ``save_turn_spatial_state``
  - default empty (== General) and legacy backfill
  - preserved on existing envelopes (membership is edited via the modal)
  - ``set_conversation_projects`` cleaning / dedupe / General-is-implicit
  - surfaced by ``iter_conversations``
  - inherited by ``fork_conversation``

Plus the ``vault_export`` Master Matrix default-path resolver (the
``Engrams/`` -> ``Administration/`` fix that was silently zeroing nexus).
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import threading
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator import conversation_memory as cm  # noqa: E402
from orchestrator import vault_export as ve  # noqa: E402


class ProjectMembershipTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _read(self, conv_id):
        return cm.load_conversation_json(conv_id, sessions_root=self.root)

    def test_new_envelope_sets_project_ids(self):
        cm.save_turn_spatial_state(
            "c1", "hello", "hi", project_ids=["book"], sessions_root=self.root
        )
        self.assertEqual(self._read("c1")["project_ids"], ["book"])

    def test_new_envelope_defaults_empty(self):
        cm.save_turn_spatial_state("c2", "hello", "hi", sessions_root=self.root)
        self.assertEqual(self._read("c2")["project_ids"], [])

    def test_new_envelope_strips_default_aliases_and_duplicates(self):
        cm.save_turn_spatial_state(
            "c2b",
            "hello",
            "hi",
            project_ids=["book", " Commons ", "GENERAL", "book", " law "],
            sessions_root=self.root,
        )
        self.assertEqual(self._read("c2b")["project_ids"], ["book", "law"])

    def test_existing_envelope_preserves_membership(self):
        cm.save_turn_spatial_state(
            "c3", "u1", "a1", project_ids=["book"], sessions_root=self.root
        )
        # A later turn passing a different project must NOT overwrite — the
        # creation binding is sticky; membership changes go through the modal.
        cm.save_turn_spatial_state(
            "c3", "u2", "a2", project_ids=["other"], sessions_root=self.root
        )
        self.assertEqual(self._read("c3")["project_ids"], ["book"])

    def test_legacy_envelope_backfills_empty(self):
        # An envelope written before this field existed.
        conv_dir = self.root / "c4"
        conv_dir.mkdir(parents=True)
        (conv_dir / "conversation.json").write_text(
            json.dumps({"conversation_id": "c4", "tag": "", "messages": []}),
            encoding="utf-8",
        )
        cm.save_turn_spatial_state("c4", "u", "a", sessions_root=self.root)
        self.assertEqual(self._read("c4")["project_ids"], [])

    def test_set_conversation_projects_cleans(self):
        cm.save_turn_spatial_state("c5", "u", "a", sessions_root=self.root)
        cm.set_conversation_projects(
            "c5",
            ["book", "book", "commons", "", "  ", "other"],
            sessions_root=self.root,
        )
        # Exact-duplicate "book" deduped; "commons"/empty stripped (Commons
        # is the implicit baseline, never stored); order preserved.
        self.assertEqual(self._read("c5")["project_ids"], ["book", "other"])

    def test_set_conversation_projects_cleans_legacy_general(self):
        cm.save_turn_spatial_state("c5b", "u", "a", sessions_root=self.root)
        cm.set_conversation_projects(
            "c5b",
            ["book", "book", "general", "", "  ", "other"],
            sessions_root=self.root,
        )
        # Legacy id "general" is stripped the same way, permanently.
        self.assertEqual(self._read("c5b")["project_ids"], ["book", "other"])

    def test_set_conversation_projects_missing_returns_none(self):
        self.assertIsNone(
            cm.set_conversation_projects("nope", ["x"], sessions_root=self.root)
        )

    def test_iter_conversations_surfaces_project_ids(self):
        cm.save_turn_spatial_state(
            "c6", "u", "a", project_ids=["book", "law"], sessions_root=self.root
        )
        rows = {r["conversation_id"]: r for r in cm.iter_conversations(self.root)}
        self.assertEqual(rows["c6"]["project_ids"], ["book", "law"])

    def test_iter_conversations_filters_mixed_explicit_sentinels(self):
        conv_dir = self.root / "c6b"
        conv_dir.mkdir(parents=True)
        (conv_dir / "conversation.json").write_text(
            json.dumps({
                "conversation_id": "c6b",
                "messages": [],
                "project_ids": ["commons", "book", "general", "book"],
            }),
            encoding="utf-8",
        )
        rows = {r["conversation_id"]: r for r in cm.iter_conversations(self.root)}
        self.assertEqual(rows["c6b"]["project_ids"], ["book"])
        healed = json.loads((conv_dir / "conversation.json").read_text(encoding="utf-8"))
        self.assertEqual(healed["project_ids"], ["book"])

    def test_full_envelope_load_heals_mixed_memberships_on_disk(self):
        conv_dir = self.root / "c6-load"
        conv_dir.mkdir(parents=True)
        path = conv_dir / "conversation.json"
        path.write_text(
            json.dumps({
                "conversation_id": "c6-load",
                "messages": [],
                "project_ids": ["commons", "book", "general", "book"],
            }),
            encoding="utf-8",
        )
        loaded = cm.load_conversation_json("c6-load", sessions_root=self.root)
        self.assertEqual(loaded["project_ids"], ["book"])
        self.assertEqual(json.loads(path.read_text())["project_ids"], ["book"])

    def test_non_membership_mutations_also_heal_mixed_memberships(self):
        mutations = (
            lambda cid: cm.mark_conversation_read(cid, sessions_root=self.root),
            lambda cid: cm.mark_conversation_errored(cid, "x", sessions_root=self.root),
            lambda cid: cm.clear_conversation_error(cid, sessions_root=self.root),
            lambda cid: cm.set_display_name(cid, "Renamed", sessions_root=self.root),
            lambda cid: cm.set_conversation_pinned(cid, True, sessions_root=self.root),
            lambda cid: cm.set_conversation_closed(cid, True, sessions_root=self.root),
        )
        for index, mutate in enumerate(mutations):
            cid = f"c6-mutate-{index}"
            conv_dir = self.root / cid
            conv_dir.mkdir(parents=True)
            path = conv_dir / "conversation.json"
            path.write_text(
                json.dumps({
                    "conversation_id": cid,
                    "messages": [],
                    "project_ids": ["general", "book", "commons", "book"],
                }),
                encoding="utf-8",
            )
            with self.subTest(mutation=index):
                self.assertIsNotNone(mutate(cid))
                self.assertEqual(json.loads(path.read_text())["project_ids"], ["book"])

    def test_errored_envelope_can_preserve_exact_unacknowledged_retry_input(self):
        cm.save_turn_spatial_state(
            "retry-envelope", "prior user", "prior assistant",
            sessions_root=self.root,
        )

        path = cm.mark_conversation_errored(
            "retry-envelope",
            "conversation envelope persistence failed",
            sessions_root=self.root,
            timestamp="2026-08-10T12:00:00",
            interrupted_input="exact unacknowledged prompt",
            interrupted_submission_id="pending-exact",
        )

        self.assertIsNotNone(path)
        envelope = self._read("retry-envelope")
        self.assertEqual(envelope["last_status"], "errored")
        self.assertEqual(
            envelope["interrupted_input"], "exact unacknowledged prompt",
        )
        self.assertEqual(
            envelope["interrupted_submission_id"], "pending-exact",
        )
        self.assertEqual(envelope["interrupted_at"], "2026-08-10T12:00:00")

    def test_cross_module_heal_cannot_erase_concurrent_turn(self):
        orchestrator_dir = str(pathlib.Path(_REPO) / "orchestrator")
        if orchestrator_dir not in sys.path:
            sys.path.insert(0, orchestrator_dir)
        import conversation_memory as top_level_cm

        self.assertIsNot(top_level_cm, cm)
        cid = "c6-race"
        conv_dir = self.root / cid
        conv_dir.mkdir(parents=True)
        path = conv_dir / "conversation.json"
        path.write_text(
            json.dumps({
                "conversation_id": cid,
                "messages": [],
                "project_ids": ["commons"],
            }),
            encoding="utf-8",
        )

        heal_at_write = threading.Event()
        release_heal = threading.Event()
        turn_done = threading.Event()
        errors: list[BaseException] = []
        original_write = top_level_cm._atomic_write_envelope

        def delayed_heal_write(target, data):
            heal_at_write.set()
            release_heal.wait(timeout=5)
            return original_write(target, data)

        def heal():
            try:
                top_level_cm.load_conversation_json(cid, sessions_root=self.root)
            except BaseException as exc:  # pragma: no cover - regression diagnostics
                errors.append(exc)

        def append_turn():
            try:
                cm.save_turn_spatial_state(
                    cid, "new user turn", "new assistant turn", sessions_root=self.root
                )
            except BaseException as exc:  # pragma: no cover - regression diagnostics
                errors.append(exc)
            finally:
                turn_done.set()

        top_level_cm._atomic_write_envelope = delayed_heal_write
        try:
            heal_thread = threading.Thread(target=heal)
            heal_thread.start()
            self.assertTrue(heal_at_write.wait(timeout=5))
            turn_thread = threading.Thread(target=append_turn)
            turn_thread.start()
            # The append must wait rather than write underneath the stale heal.
            self.assertFalse(turn_done.wait(timeout=0.2))
            release_heal.set()
            heal_thread.join(timeout=5)
            turn_thread.join(timeout=5)
        finally:
            release_heal.set()
            top_level_cm._atomic_write_envelope = original_write

        self.assertFalse(errors)
        stored = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(stored["project_ids"], [])
        self.assertEqual(
            [message["content"] for message in stored["messages"]],
            ["new user turn", "new assistant turn"],
        )

    def test_missing_project_ids_is_canonical_outward_without_disk_churn(self):
        cid = "c6-missing"
        conv_dir = self.root / cid
        conv_dir.mkdir(parents=True)
        path = conv_dir / "conversation.json"
        original = json.dumps({"conversation_id": cid, "messages": []})
        path.write_text(original, encoding="utf-8")

        loaded = cm.load_conversation_json(cid, sessions_root=self.root)
        self.assertEqual(loaded["project_ids"], [])
        self.assertEqual(path.read_text(encoding="utf-8"), original)
        self.assertFalse(pathlib.Path(str(path) + ".lock").exists())

    def test_heal_lock_timeout_still_returns_canonical_snapshot(self):
        cid = "c6-lock-timeout"
        conv_dir = self.root / cid
        conv_dir.mkdir(parents=True)
        path = conv_dir / "conversation.json"
        raw = {
            "conversation_id": cid,
            "messages": [],
            "project_ids": ["commons", "book", "general"],
        }
        path.write_text(json.dumps(raw), encoding="utf-8")

        class TimedOutLock:
            def __enter__(self):
                raise TimeoutError("busy")

            def __exit__(self, *_args):
                return False

        original_locked_file = cm._rp.locked_file
        cm._rp.locked_file = lambda _path: TimedOutLock()
        try:
            loaded = cm.load_conversation_json(cid, sessions_root=self.root)
        finally:
            cm._rp.locked_file = original_locked_file

        self.assertEqual(loaded["project_ids"], ["book"])
        # The failed best-effort heal leaves disk untouched for a later retry.
        self.assertEqual(json.loads(path.read_text()), raw)

    def test_existing_envelope_lazily_heals_default_sentinels_on_save(self):
        conv_dir = self.root / "c6c"
        conv_dir.mkdir(parents=True)
        (conv_dir / "conversation.json").write_text(
            json.dumps({
                "conversation_id": "c6c",
                "messages": [],
                "project_ids": ["general", "book", "commons"],
            }),
            encoding="utf-8",
        )
        cm.save_turn_spatial_state("c6c", "u", "a", sessions_root=self.root)
        self.assertEqual(self._read("c6c")["project_ids"], ["book"])

    def test_fork_inherits_project_ids(self):
        cm.save_turn_spatial_state(
            "parent", "u", "a", project_ids=["book"], sessions_root=self.root
        )
        new_id = cm.fork_conversation(
            "parent", "child", sessions_root=self.root
        )
        self.assertIsNotNone(new_id)
        self.assertEqual(self._read("child")["project_ids"], ["book"])

    def test_fork_filters_legacy_default_memberships(self):
        cm.save_turn_spatial_state(
            "parent-mixed", "u", "a", project_ids=["book"], sessions_root=self.root
        )
        parent_path = self.root / "parent-mixed" / "conversation.json"
        parent = json.loads(parent_path.read_text(encoding="utf-8"))
        parent["project_ids"] = ["general", "book", "commons"]
        parent_path.write_text(json.dumps(parent), encoding="utf-8")
        cm.fork_conversation("parent-mixed", "child-mixed", sessions_root=self.root)
        self.assertEqual(self._read("child-mixed")["project_ids"], ["book"])


class EffectiveDialogueHistoryTests(unittest.TestCase):
    """Fork ancestry is resolved read-only from immutable message cutoffs."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _turn(self, conversation_id, index):
        cm.save_turn_spatial_state(
            conversation_id,
            f"{conversation_id}-u{index}",
            f"{conversation_id}-a{index}",
            sessions_root=self.root,
        )

    @staticmethod
    def _contents(history):
        return [message["content"] for message in history]

    def test_child_stops_at_cutoff_and_never_copies_parent_messages(self):
        for index in range(3):
            self._turn("root", index)
        cm.fork_conversation(
            "root", "child", fork_point_turn_index=1,
            sessions_root=self.root,
        )
        self._turn("child", 0)
        self._turn("root", 3)  # Later parent activity must not leak.
        cm.set_conversation_closed("root", True, sessions_root=self.root)

        history = cm.resolve_effective_conversation_history(
            "child", sessions_root=self.root,
        )
        self.assertEqual(self._contents(history), [
            "root-u0", "root-a0", "root-u1", "root-a1",
            "child-u0", "child-a0",
        ])
        child_on_disk = json.loads(
            (self.root / "child" / "conversation.json").read_text()
        )
        self.assertEqual(
            self._contents(child_on_disk["messages"]),
            ["child-u0", "child-a0"],
        )

    def test_nested_fork_uses_child_local_display_index_without_leaks(self):
        for index in range(3):
            self._turn("root", index)
        cm.fork_conversation(
            "root", "child", fork_point_turn_index=1,
            sessions_root=self.root,
        )
        self._turn("child", 0)
        grandchild = cm.fork_conversation(
            "child", "grandchild", fork_point_turn_index=0,
            sessions_root=self.root,
        )
        # The child UI displays one local turn, so index 0 persists a two-
        # message local cutoff rather than indexing into effective ancestry.
        self.assertEqual(grandchild["fork_point_message_count"], 2)
        self._turn("grandchild", 0)
        self._turn("child", 1)
        self._turn("root", 3)

        history = cm.resolve_effective_conversation_history(
            "grandchild", sessions_root=self.root,
        )
        self.assertEqual(self._contents(history), [
            "root-u0", "root-a0", "root-u1", "root-a1",
            "child-u0", "child-a0",
            "grandchild-u0", "grandchild-a0",
        ])

    def test_archived_closed_parent_remains_readable(self):
        self._turn("root", 0)
        cm.fork_conversation("root", "child", sessions_root=self.root)
        cm.set_conversation_closed("root", True, sessions_root=self.root)
        archive = self.root / "archived"
        archive.mkdir()
        (self.root / "root").rename(archive / "root")

        history = cm.resolve_effective_conversation_history(
            "child", sessions_root=self.root,
        )
        self.assertEqual(self._contents(history), ["root-u0", "root-a0"])

    def test_orphan_malformed_cutoff_and_cycle_drop_unsafe_ancestry_read_only(self):
        def write(conversation_id, body):
            path = self.root / conversation_id / "conversation.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(body), encoding="utf-8")
            return path

        local = [
            {"role": "user", "content": "local-u"},
            {"role": "assistant", "content": "local-a"},
        ]
        orphan = write("orphan", {
            "conversation_id": "orphan", "messages": local,
            "parent_conversation_id": "missing",
            "fork_point_message_count": 0,
        })
        malformed = write("malformed", {
            "conversation_id": "malformed", "messages": local,
            "parent_conversation_id": "missing",
            "fork_point_message_count": "two",
        })
        cycle_a = write("cycle-a", {
            "conversation_id": "cycle-a", "messages": local,
            "parent_conversation_id": "cycle-b",
            "fork_point_message_count": 2,
        })
        cycle_b = write("cycle-b", {
            "conversation_id": "cycle-b", "messages": [
                {"role": "user", "content": "other-u"},
                {"role": "assistant", "content": "other-a"},
            ],
            "parent_conversation_id": "cycle-a",
            "fork_point_message_count": 2,
        })
        cycle_b_before = cycle_b.read_bytes()

        for conversation_id, path, expected_diagnostic in (
            ("orphan", orphan, "missing or unreadable"),
            ("malformed", malformed, "malformed fork_point"),
            ("cycle-a", cycle_a, "cycle detected"),
        ):
            before = path.read_bytes()
            diagnostics = []
            history = cm.resolve_effective_conversation_history(
                conversation_id,
                sessions_root=self.root,
                diagnostics=diagnostics,
            )
            self.assertEqual(
                self._contents(history), ["local-u", "local-a"],
                conversation_id,
            )
            self.assertTrue(
                any(expected_diagnostic in item for item in diagnostics),
                diagnostics,
            )
            self.assertEqual(path.read_bytes(), before)
        self.assertEqual(cycle_b.read_bytes(), cycle_b_before)


class MasterMatrixPathTests(unittest.TestCase):
    def test_administration_is_primary_candidate(self):
        # Regression: the hard-coded default used the non-existent Engrams/
        # path, zeroing every export's nexus. Administration/ must lead.
        self.assertIn("Administration", str(ve._MASTER_MATRIX_CANDIDATES[0]))

    def test_default_path_prefers_existing_candidate(self):
        original = ve._MASTER_MATRIX_CANDIDATES
        try:
            with tempfile.TemporaryDirectory() as d:
                missing = pathlib.Path(d) / "missing.md"
                present = pathlib.Path(d) / "present.md"
                present.write_text("x", encoding="utf-8")
                ve._MASTER_MATRIX_CANDIDATES = (missing, present)
                self.assertEqual(ve._default_master_matrix_path(), present)
                # When none exist, fall back to the first (canonical) candidate.
                ve._MASTER_MATRIX_CANDIDATES = (missing,)
                self.assertEqual(ve._default_master_matrix_path(), missing)
        finally:
            ve._MASTER_MATRIX_CANDIDATES = original


if __name__ == "__main__":
    unittest.main()
