"""Adversarial proofs for the bounded G1.22 pre-channel tranche."""

from __future__ import annotations

import copy
import json
import os
import shlex
import sys
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

_ORCH = Path(__file__).resolve().parent.parent
if str(_ORCH) not in sys.path:
    sys.path.insert(0, str(_ORCH))
_TESTS = str(Path(__file__).resolve().parent)
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)
import live_guard  # noqa: E402,F401

import oversight_queue  # noqa: E402
import system_protection as protection  # noqa: E402
import tool_events  # noqa: E402
from tools import credential_store as credential_tool  # noqa: E402


class SystemProtectionBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=str(Path.home()))
        self.root = Path(self.tmp.name)
        self.actions = str(self.root / "actions.jsonl")
        self.approvals = str(self.root / "approvals.json")
        self.queue = str(self.root / "queue.jsonl")
        self.events = str(self.root / "tool-events.jsonl")
        self._patches = [
            mock.patch.object(protection, "_actions_path", return_value=self.actions),
            mock.patch.object(tool_events, "APPROVALS_PATH", self.approvals),
            mock.patch.object(tool_events, "GLOBAL_SINK_DEFAULT", self.events),
            mock.patch.object(oversight_queue, "HUMAN_QUEUE_PATH", self.queue),
        ]
        for patcher in self._patches:
            patcher.start()
        self.turn_token = tool_events.set_turn_context(
            conversation_id="g1-22a-test", surface="test",
        )
        tool_events._queued_hashes.clear()

    def tearDown(self):
        tool_events._queued_hashes.clear()
        tool_events.reset_turn_context(self.turn_token)
        for patcher in reversed(self._patches):
            patcher.stop()
        self.tmp.cleanup()

    def _queue_records(self):
        if not os.path.isfile(self.queue):
            return []
        with open(self.queue, encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]

    def _request(self, target: Path, action: str = "theme_delete"):
        selector = protection.path_selector(target)
        state = protection.capture_path_identity(target)
        return action, selector, state

    def _approve_latest(self):
        record = self._queue_records()[-1]
        result = tool_events.resolve_gate_entry(record, approve=True)
        self.assertIn("One-shot token", result)
        return record


class TestPolicyFloor(SystemProtectionBase):
    def test_dedicated_path_builders_reject_traversal_before_review(self):
        from orchestrator import active_configuration, project_registry

        with self.assertRaises(ValueError):
            active_configuration._config_path("../../authority")
        with self.assertRaises(project_registry.ProjectError):
            project_registry._pointer_path("../../authority")

    def test_whole_roots_raw_drives_and_channels_are_absolute_denials(self):
        roots = protection._critical_roots()
        for name, root in roots.items():
            decision = protection.classify_action(
                "delete_state", selectors=["path:" + root],
                mutability="irreversible",
            )
            self.assertEqual(decision.outcome, "deny", name)
        for selector in ("path:/dev/disk0", "path:/dev/rdisk4",
                         "path://./physicaldrive0"):
            self.assertEqual(protection.classify_action(
                "format_drive", selectors=[selector],
                mutability="irreversible",
            ).outcome, "deny")
        for action in ("telegram_send", "email_receive", "channel_send"):
            decision = protection.classify_action(
                action, selectors=["channel:test"],
                mutability="external_write", egress="external",
            )
            self.assertEqual(decision.policy_code, "channel-deferred")

    def test_missing_broad_and_noncanonical_scopes_fail_closed(self):
        self.assertEqual(protection.classify_action(
            "delete_everything", mutability="irreversible",
        ).policy_code, "missing-exact-scope")
        self.assertEqual(protection.classify_action(
            "delete_file", selectors=["path:/tmp/${TARGET}"],
            mutability="irreversible",
        ).policy_code, "unresolved-protected-scope")
        self.assertEqual(protection.classify_action(
            "credential_store", selectors=["credential:other/arbitrary"],
            mutability="irreversible", sensitivity="secret",
        ).policy_code, "noncanonical-credential-scope")
        self.assertEqual(protection.classify_action(
            "self_modification", selectors=["path:/tmp/runtime.py"],
            mutability="irreversible",
        ).outcome, "review")
        runtime_source = Path(protection._rp.ORA_HOME) / "orchestrator" / "dispatcher.py"
        self.assertEqual(protection.classify_action(
            "file_write", selectors=[protection.path_selector(runtime_source)],
            mutability="reversible_write",
        ).outcome, "deny")

    def test_opaque_server_and_slash_actions_have_no_adapter(self):
        logical = {"selector": "project:ora/tool:opaque", "kind": "logical"}
        logical["digest"] = protection.params_digest(logical)
        with self.assertRaises(protection.ProtectionDenied):
            protection.authorize_server_action(
                "project_tool_execute", selectors=[logical["selector"]],
                params={"tool": "opaque"}, pre_state=[logical],
                surface="slash_command",
            )
        self.assertEqual(self._queue_records(), [])

    def test_legacy_bulk_mutation_slash_paths_fail_before_resolver(self):
        import slash_commands

        with mock.patch.dict(sys.modules, {
            "historical.run_engram_cleaning_resolver": mock.Mock(),
            "historical.run_news_supersession_resolver": mock.Mock(),
        }):
            cleaning = slash_commands._cmd_cleaning(["resolve", "--apply"])
            news = slash_commands._cmd_news(["resolve", "--apply"])
        self.assertIn("SYSTEM PROTECTION", cleaning)
        self.assertIn("SYSTEM PROTECTION", news)


class TestApprovalAndReceipts(SystemProtectionBase):
    def test_approval_store_and_authentication_key_are_not_generic_files(self):
        for target in (
            Path(protection._rp.DATA_DIR) / "execution-approvals.json",
            Path(protection._rp.DATA_DIR) / "execution-approvals.json.auth.key",
        ):
            decision = protection.classify_tool_call(
                "file_read", {"path": str(target)},
                {"category": "read", "mutability": "read",
                 "sensitivity": "private", "egress": "none"},
            )
            self.assertEqual(decision.outcome, "deny", target)

    def test_approval_authority_refuses_recursive_patterns_and_aliases_pre_execution(self):
        import dispatcher
        from tools import file_edit, file_ops, search_files
        from tools import bash_execute
        from tools.bash_execute import resolve_shell_profile

        tool_events._grant_approval_authorized(
            "diagnostic", tool_events.normalize_args_hash("diagnostic", {}),
            "g1-22a-test",
        )
        store = Path(self.approvals)
        key = Path(self.approvals + ".auth.key")
        symlink = self.root / "approval-symlink.json"
        hardlink = self.root / "approval-hardlink.json"
        symlink.symlink_to(store)
        os.link(store, hardlink)
        read_axes = {
            "category": "read", "mutability": "read",
            "sensitivity": "private", "egress": "none",
        }

        for equivalent in (
            store,
            key,
            symlink,
            hardlink,
            self.root / "nested" / ".." / store.name,
        ):
            decision = protection.classify_tool_call(
                "file_read", {"path": str(equivalent)}, read_axes,
            )
            self.assertEqual(decision.outcome, "deny", equivalent)

        for tool_name, parameters in (
            ("search_files", {"pattern": "token", "directory": str(self.root)}),
            ("list_directory", {"path": str(self.root), "max_depth": 4}),
        ):
            decision = protection.classify_tool_call(
                tool_name, parameters, read_axes,
            )
            self.assertEqual(decision.outcome, "deny", tool_name)

        for command in (
            f"cat {self.root}/approvals.*",
            f"cat {self.root}/approvals.{{json,bak}}",
            f"rg token {self.root}",
            f"grep -rn token {self.root}",
            "cat $UNRESOLVED_APPROVAL_PATH",
            f"cat {symlink}",
            f"cat {hardlink}",
        ):
            profile = resolve_shell_profile(command, cwd=str(self.root))
            decision = protection.classify_tool_call(
                "bash_execute", {"command": command},
                {**read_axes, **profile}, shell_profile=profile,
            )
            self.assertEqual(decision.outcome, "deny", command)

        # Access depth remains exact: a non-recursive listing of an ancestor
        # that cannot itself reach the authority files remains legitimate,
        # while listing their immediate parent is denied.
        shallow_command = f"ls {self.root.parent}"
        shallow_profile = resolve_shell_profile(
            shallow_command, cwd=str(self.root),
        )
        self.assertNotEqual(protection.classify_tool_call(
            "bash_execute", {"command": shallow_command},
            {**read_axes, **shallow_profile}, shell_profile=shallow_profile,
        ).outcome, "deny")
        parent_command = f"ls {self.root}"
        parent_profile = resolve_shell_profile(
            parent_command, cwd=str(self.root),
        )
        self.assertEqual(protection.classify_tool_call(
            "bash_execute", {"command": parent_command},
            {**read_axes, **parent_profile}, shell_profile=parent_profile,
        ).outcome, "deny")

        dispatcher.reset_consecutive()
        original = dispatcher.TOOL_REGISTRY["search_files"]["handler"]
        never_execute = mock.Mock(side_effect=AssertionError("handler ran"))
        dispatcher.TOOL_REGISTRY["search_files"]["handler"] = never_execute
        try:
            result = dispatcher.dispatch(
                "search_files",
                {"pattern": "token", "directory": str(self.root)},
            )
        finally:
            dispatcher.TOOL_REGISTRY["search_files"]["handler"] = original
        self.assertIn("SYSTEM PROTECTION", result)
        never_execute.assert_not_called()

        self.assertIn("BLOCKED", file_ops.file_read(str(symlink)))
        before = store.read_bytes()
        self.assertIn("BLOCKED", file_ops.file_write(str(hardlink), "changed"))
        self.assertFalse(file_edit.edit_file(
            str(symlink), "diagnostic", "changed",
        )["success"])
        self.assertEqual(store.read_bytes(), before)
        self.assertIn("BLOCKED", search_files.grep_files(
            "token", str(self.root),
        )[0]["error"])
        self.assertIn("BLOCKED", search_files.list_directory(str(self.root)))
        with mock.patch.object(bash_execute.subprocess, "run") as run:
            refused = bash_execute.execute_command(
                f"cat {self.root}/approvals.*", cwd=str(self.root),
            )
        run.assert_not_called()
        self.assertIn("SYSTEM PROTECTION", refused["stderr"])

        # A recursive root that is lexically disjoint but contains a
        # filesystem alias is also refused before traversal starts.
        with tempfile.TemporaryDirectory(dir=str(Path.home())) as alias_root:
            nested = Path(alias_root) / "nested"
            nested.mkdir()
            (nested / "store-link.json").symlink_to(store)
            os.link(key, nested / "key-hardlink")
            aliased_tree = protection.classify_tool_call(
                "search_files",
                {"pattern": "token", "directory": alias_root},
                read_axes,
            )
            self.assertEqual(aliased_tree.outcome, "deny")

    def test_direct_shell_sink_refuses_unknown_wrappers_in_both_modes(self):
        from tools import bash_execute

        protected = shlex.quote(self.approvals)
        commands = (
            f"env cat {protected}",
            f"env FOO=1 sh -c 'cat {self.approvals}'",
            f"awk 'BEGIN{{system(\"cat {self.approvals}\")}}'",
            f"find {shlex.quote(str(self.root))} -execdir cat {protected} ';'",
            f"pandoc --filter cat {protected}",
        )
        for background in (False, True):
            for command in commands:
                with self.subTest(background=background, command=command), \
                        mock.patch.object(
                            bash_execute.subprocess, "run",
                        ) as run, mock.patch.object(
                            bash_execute.subprocess, "Popen",
                        ) as popen:
                    result = bash_execute.execute_command(
                        command, cwd=str(self.root), background=background,
                    )
                refusal = result.get("status") if background \
                    else result.get("stderr")
                self.assertIn("SYSTEM PROTECTION", refusal)
                run.assert_not_called()
                popen.assert_not_called()

    def test_signed_approval_store_tampering_fails_closed(self):
        args_hash = tool_events.normalize_args_hash("diagnostic", {"x": 1})
        tool_events._grant_approval_authorized(
            "diagnostic", args_hash, "g1-22a-test",
        )
        data = json.loads(Path(self.approvals).read_text(encoding="utf-8"))
        data["tokens"][0]["action"] = "substituted"
        Path(self.approvals).write_text(json.dumps(data), encoding="utf-8")
        tampered = Path(self.approvals).read_bytes()
        with self.assertRaisesRegex(RuntimeError, "authentication failed"):
            tool_events.check_and_consume_approval(
                "substituted", args_hash, "g1-22a-test",
            )
        self.assertEqual(Path(self.approvals).read_bytes(), tampered)
        self.assertEqual(self._queue_records(), [])

    def test_authority_empty_legacy_store_upgrades_without_granting_approval(self):
        Path(self.approvals).write_text(
            json.dumps({"tokens": [], "standing": []}), encoding="utf-8",
        )
        args_hash = tool_events.normalize_args_hash("diagnostic", {"x": 1})

        self.assertIsNone(tool_events.check_and_consume_approval(
            "diagnostic", args_hash, "g1-22a-test",
        ))

        upgraded = json.loads(Path(self.approvals).read_text(encoding="utf-8"))
        self.assertEqual(upgraded["schema_version"], 2)
        self.assertEqual(upgraded["tokens"], [])
        self.assertEqual(upgraded["standing"], [])
        self.assertEqual(upgraded["pending"], [])
        if os.name != "nt":
            self.assertEqual(Path(self.approvals).stat().st_mode & 0o777, 0o600)
        key = Path(self.approvals + ".auth.key").read_bytes()
        self.assertEqual(len(key), 32)
        self.assertEqual(
            upgraded["store_mac"], tool_events._approval_store_mac(upgraded, key),
        )
        self.assertEqual(self._queue_records(), [])

    def test_nonempty_or_malformed_legacy_stores_remain_unchanged_and_closed(self):
        cases = {
            "nonempty-tokens": {
                "tokens": [{"id": "unsigned"}], "standing": [],
            },
            "nonempty-standing": {
                "tokens": [], "standing": [{"scope": "unsigned"}],
            },
            "nonempty-pending": {
                "tokens": [], "standing": [],
                "pending": [{"nonce": "unsigned"}],
            },
            "malformed-tokens": {"tokens": {}, "standing": []},
            "malformed-standing": {"tokens": [], "standing": None},
            "malformed-pending": {
                "tokens": [], "standing": [], "pending": "unsigned",
            },
            "unknown-authority-field": {
                "tokens": [], "standing": [],
                "standing_allows": [{"scope": "unsigned"}],
            },
            "unsupported-version": {
                "schema_version": 1, "tokens": [], "standing": [],
            },
        }
        args_hash = tool_events.normalize_args_hash("diagnostic", {})

        for name, value in cases.items():
            with self.subTest(name=name):
                store = self.root / f"{name}.json"
                original = json.dumps(value).encode("utf-8")
                store.write_bytes(original)
                with mock.patch.object(tool_events, "APPROVALS_PATH", str(store)):
                    with self.assertRaisesRegex(
                        RuntimeError, "unsigned or has an unsupported schema",
                    ):
                        tool_events.check_and_consume_approval(
                            "diagnostic", args_hash, "g1-22a-test",
                        )
                self.assertEqual(store.read_bytes(), original)
                self.assertFalse(Path(str(store) + ".auth.key").exists())

    def test_legacy_store_symlink_and_non_regular_file_fail_closed(self):
        target = self.root / "legacy-target.json"
        original = json.dumps({"tokens": [], "standing": []}).encode("utf-8")
        target.write_bytes(original)
        symlink = self.root / "legacy-link.json"
        symlink.symlink_to(target)
        directory = self.root / "legacy-directory.json"
        directory.mkdir()
        args_hash = tool_events.normalize_args_hash("diagnostic", {})

        for store, message in (
            (symlink, "symlink"),
            (directory, "not a regular file"),
        ):
            with self.subTest(store=store), mock.patch.object(
                tool_events, "APPROVALS_PATH", str(store),
            ):
                with self.assertRaisesRegex(RuntimeError, message):
                    tool_events.check_and_consume_approval(
                        "diagnostic", args_hash, "g1-22a-test",
                    )

        self.assertEqual(target.read_bytes(), original)
        self.assertFalse(Path(str(symlink) + ".auth.key").exists())
        self.assertFalse(Path(str(directory) + ".auth.key").exists())

    def test_duplicate_legacy_authority_field_is_not_treated_as_empty(self):
        original = (
            b'{"tokens":[{"id":"hidden"}],"tokens":[],"standing":[]}'
        )
        Path(self.approvals).write_bytes(original)

        with self.assertRaisesRegex(RuntimeError, "duplicate approval-store field"):
            tool_events.check_and_consume_approval(
                "diagnostic", tool_events.normalize_args_hash("diagnostic", {}),
                "g1-22a-test",
            )

        self.assertEqual(Path(self.approvals).read_bytes(), original)
        self.assertFalse(Path(self.approvals + ".auth.key").exists())

    def test_concurrent_first_writers_migrate_once_without_lost_updates(self):
        Path(self.approvals).write_text(
            json.dumps({"tokens": [], "standing": []}), encoding="utf-8",
        )
        count = 8
        barrier = threading.Barrier(count)
        outcomes: list[object | None] = [None] * count

        def register(index: int) -> None:
            try:
                barrier.wait(timeout=5)
                outcomes[index] = tool_events._register_pending_approval(
                    f"concurrent-{index}", f"hash-{index}",
                    "g1-22a-test", "principal:user",
                )
            except BaseException as exc:  # surfaced by the assertion below
                outcomes[index] = exc

        threads = [
            threading.Thread(target=register, args=(index,))
            for index in range(count)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertFalse(any(isinstance(item, BaseException) for item in outcomes))
        self.assertNotIn(None, outcomes)
        self.assertEqual(len(set(outcomes)), count)
        data = tool_events._load_approvals()
        self.assertEqual(data["tokens"], [])
        self.assertEqual(data["standing"], [])
        self.assertEqual(len(data["pending"]), count)
        self.assertEqual(
            {item["action"] for item in data["pending"]},
            {f"concurrent-{index}" for index in range(count)},
        )

    def test_reviewed_selector_and_pre_state_cannot_be_rebound(self):
        target_a = self.root / "a.txt"
        target_b = self.root / "b.txt"
        alias = self.root / "current.txt"
        target_a.write_text("A", encoding="utf-8")
        target_b.write_text("B", encoding="utf-8")
        alias.symlink_to(target_a)
        params = {"path": str(alias)}
        raw_hash = tool_events.normalize_args_hash("delete_file", params)
        decision = protection.classify_action(
            "delete_file", selectors=[protection.path_selector(alias)],
            mutability="irreversible",
        )
        reviewed_state = protection.capture_selector_identity(
            decision.selectors[0]
        )
        request_a, digest_a = protection.prepare_protection_request(
            decision, params_digest=protection.params_digest(params),
            pre_state=[reviewed_state], surface="tool_dispatcher",
        )
        first = tool_events.gate(
            "delete_file",
            {"category": "write", "mutability": "irreversible",
             "sensitivity": "private", "egress": "none"},
            params=params,
            approval_binding={"request_digest": digest_a,
                              "selectors": request_a["selectors"]},
        )
        self.assertFalse(first.allowed)
        self._approve_latest()

        alias.unlink()
        alias.symlink_to(target_b)
        self.assertEqual(
            raw_hash, tool_events.normalize_args_hash("delete_file", params),
        )
        rebound_decision = protection.classify_action(
            "delete_file", selectors=[protection.path_selector(alias)],
            mutability="irreversible",
        )
        rebound_state = protection.capture_selector_identity(
            rebound_decision.selectors[0]
        )
        request_b, digest_b = protection.prepare_protection_request(
            rebound_decision, params_digest=protection.params_digest(params),
            pre_state=[rebound_state], surface="tool_dispatcher",
        )
        self.assertNotEqual(digest_a, digest_b)
        retry = tool_events.gate(
            "delete_file",
            {"category": "write", "mutability": "irreversible",
             "sensitivity": "private", "egress": "none"},
            params=params,
            approval_binding={"request_digest": digest_b,
                              "selectors": request_b["selectors"]},
        )
        self.assertFalse(retry.allowed)
        self.assertNotEqual(retry.decision, "approved")
        tokens = tool_events._load_approvals()["tokens"]
        self.assertEqual(len(tokens), 1)
        self.assertTrue(tokens[0]["used"])
        self.assertEqual(
            tokens[0]["invalidation_reason"],
            "review-request-digest-mismatch",
        )
        self.assertEqual(protection.verify_audit(), [])

    def test_exact_approval_succeeds_once_and_is_receipt_bound(self):
        target = self.root / "custom-theme"
        target.mkdir()
        (target / "theme.css").write_text("old", encoding="utf-8")
        action, selector, state = self._request(target)
        with self.assertRaises(protection.ProtectionReviewRequired):
            protection.authorize_server_action(
                action, selectors=[selector], params={"theme_id": "custom"},
                pre_state=[state],
            )
        self._approve_latest()
        execution = protection.authorize_server_action(
            action, selectors=[selector], params={"theme_id": "custom"},
            pre_state=[state],
        )
        (target / "theme.css").write_text("new", encoding="utf-8")
        terminal = protection.complete_execution(
            execution, ok=True, result={"ok": True},
            post_state=[protection.capture_path_identity(target)],
        )
        self.assertEqual(terminal["event_type"], "protected_action_completed")
        records = protection.verify_audit()
        self.assertEqual([r["event_type"] for r in records], [
            "protected_action_started", "protected_action_completed",
        ])
        with self.assertRaises(protection.ProtectionReviewRequired):
            protection.authorize_server_action(
                action, selectors=[selector], params={"theme_id": "custom"},
                pre_state=[protection.capture_path_identity(target)],
            )

    def test_cross_scope_and_forged_queue_records_cannot_authorize(self):
        one = self.root / "one"
        two = self.root / "two"
        one.write_text("1", encoding="utf-8")
        two.write_text("2", encoding="utf-8")
        action, selector_one, state_one = self._request(one)
        with self.assertRaises(protection.ProtectionReviewRequired):
            protection.authorize_server_action(
                action, selectors=[selector_one], params={"theme_id": "one"},
                pre_state=[state_one],
            )
        original = self._queue_records()[-1]
        forged = copy.deepcopy(original)
        forged["id"] = "forged-queue-id"
        self.assertIn("Unauthenticated", tool_events.resolve_gate_entry(
            forged, approve=True,
        ))
        self._approve_latest()

        _, selector_two, state_two = self._request(two)
        with self.assertRaises(protection.ProtectionReviewRequired):
            protection.authorize_server_action(
                action, selectors=[selector_two], params={"theme_id": "two"},
                pre_state=[state_two],
            )
        execution = protection.authorize_server_action(
            action, selectors=[selector_one], params={"theme_id": "one"},
            pre_state=[state_one],
        )
        protection.complete_execution(
            execution, ok=True, result={"ok": True},
            post_state=[state_one],
        )

    def test_pre_state_drift_makes_approval_stale_without_start_receipt(self):
        target = self.root / "profile.json"
        target.write_text("before", encoding="utf-8")
        action, selector, state = self._request(target, "model_profile_delete")
        with self.assertRaises(protection.ProtectionReviewRequired):
            protection.authorize_server_action(
                action, selectors=[selector], params={"name": "profile"},
                pre_state=[state],
            )
        self._approve_latest()
        target.write_text("drifted", encoding="utf-8")
        with self.assertRaises(protection.ProtectionReviewRequired):
            protection.authorize_server_action(
                action, selectors=[selector], params={"name": "profile"},
                pre_state=[protection.capture_path_identity(target)],
            )
        self.assertEqual(protection.verify_audit(), [])

    def test_drift_after_write_ahead_is_rejected_before_effect_scope(self):
        target = self.root / "profile.json"
        target.write_text("before", encoding="utf-8")
        action, selector, state = self._request(target, "model_profile_delete")
        params = {"name": "profile"}
        with self.assertRaises(protection.ProtectionReviewRequired):
            protection.authorize_server_action(
                action, selectors=[selector], params=params,
                pre_state=[state],
            )
        self._approve_latest()
        execution = protection.authorize_server_action(
            action, selectors=[selector], params=params,
            pre_state=[state],
        )
        target.write_text("raced", encoding="utf-8")
        effect_ran = False
        with self.assertRaises(protection.ProtectionDenied):
            with protection.protected_effect(execution):
                effect_ran = True
        self.assertFalse(effect_ran)
        records = protection.verify_audit()
        self.assertEqual(
            [record["event_type"] for record in records],
            ["protected_action_started"],
        )

    def test_direct_mint_and_fabricated_receipt_start_are_rejected(self):
        with self.assertRaises(PermissionError):
            tool_events.grant_approval("system_protection:theme_delete", "x")
        decision = protection.classify_action(
            "theme_delete", selectors=[protection.path_selector(self.root / "x")],
            mutability="irreversible", dedicated_action=True,
        )
        with self.assertRaises(protection.ProtectionAuditError):
            protection.begin_execution(
                decision, approval_id="fabricated",
                approval_action="system_protection:theme_delete",
                approval_args_hash="fabricated", params_digest="sha256:false",
                pre_state=[], surface="test",
            )
        self.assertFalse(os.path.exists(self.actions))

    def test_pre_state_fabrication_and_audit_tampering_fail_closed(self):
        target = self.root / "profile.json"
        target.write_text("before", encoding="utf-8")
        action, selector, state = self._request(target, "model_profile_delete")
        forged = dict(state)
        forged["content_digest"] = "sha256:" + "0" * 64
        body = dict(forged)
        body.pop("digest")
        forged["digest"] = protection.params_digest(body)
        with self.assertRaises(protection.ProtectionDenied):
            protection.authorize_server_action(
                action, selectors=[selector], params={"name": "x"},
                pre_state=[forged],
            )
        self.assertEqual(self._queue_records(), [])

        with self.assertRaises(protection.ProtectionReviewRequired):
            protection.authorize_server_action(
                action, selectors=[selector], params={"name": "x"},
                pre_state=[state],
            )
        self._approve_latest()
        execution = protection.authorize_server_action(
            action, selectors=[selector], params={"name": "x"},
            pre_state=[state],
        )
        protection.complete_execution(
            execution, ok=True, result={"ok": True}, post_state=[state],
        )
        lines = Path(self.actions).read_text(encoding="utf-8").splitlines()
        altered = json.loads(lines[0])
        altered["request"]["action"] = "substituted"
        altered.pop("record_digest")
        # Recomputing a self-declared adjacent digest is still not authority;
        # the verifier expects the protected-key HMAC.
        altered["record_digest"] = protection.params_digest(altered)
        lines[0] = json.dumps(altered, sort_keys=True, separators=(",", ":"))
        Path(self.actions).write_text("\n".join(lines) + "\n", encoding="utf-8")
        with self.assertRaises(protection.ProtectionAuditError):
            protection.verify_audit()

    def test_receipt_write_failure_blocks_before_effect(self):
        target = self.root / "theme"
        target.mkdir()
        action, selector, state = self._request(target)
        with self.assertRaises(protection.ProtectionReviewRequired):
            protection.authorize_server_action(
                action, selectors=[selector], params={"theme_id": "x"},
                pre_state=[state],
            )
        self._approve_latest()
        with mock.patch.object(
            protection._rp, "append_bytes_no_follow",
            side_effect=OSError("forced audit failure"),
        ):
            with self.assertRaises(protection.ProtectionAuditError):
                protection.authorize_server_action(
                    action, selectors=[selector], params={"theme_id": "x"},
                    pre_state=[state],
                )
        self.assertTrue(target.exists())

    def test_corrupt_approval_store_is_broken_infrastructure_not_reset(self):
        target = self.root / "theme"
        target.mkdir()
        Path(self.approvals).write_text("{not-json", encoding="utf-8")
        action, selector, state = self._request(target)
        with self.assertRaises(protection.ProtectionAuditError):
            protection.authorize_server_action(
                action, selectors=[selector], params={"theme_id": "x"},
                pre_state=[state],
            )
        self.assertEqual(
            Path(self.approvals).read_text(encoding="utf-8"), "{not-json",
        )
        self.assertTrue(target.exists())
        self.assertEqual(self._queue_records(), [])

    def test_terminal_receipt_is_single_winner_and_identity_bound(self):
        target = self.root / "theme"
        target.mkdir()
        action, selector, state = self._request(target)
        with self.assertRaises(protection.ProtectionReviewRequired):
            protection.authorize_server_action(
                action, selectors=[selector], params={"theme_id": "x"},
                pre_state=[state],
            )
        self._approve_latest()
        execution = protection.authorize_server_action(
            action, selectors=[selector], params={"theme_id": "x"},
            pre_state=[state],
        )
        fabricated_post = dict(state)
        fabricated_post["kind"] = "absent"
        fabricated_post.pop("content_digest", None)
        fabricated_post.pop("bytes", None)
        body = dict(fabricated_post)
        body.pop("digest")
        fabricated_post["digest"] = protection.params_digest(body)
        with self.assertRaises(protection.ProtectionDenied):
            protection.complete_execution(
                execution, ok=True, result={"ok": True},
                post_state=[fabricated_post],
            )
        outcomes = []

        def finish():
            try:
                protection.complete_execution(
                    execution, ok=True, result={"ok": True}, post_state=[state],
                )
                outcomes.append("ok")
            except protection.ProtectionAuditError:
                outcomes.append("rejected")

        threads = [threading.Thread(target=finish) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertCountEqual(outcomes, ["ok", "rejected"])
        with self.assertRaises(protection.ProtectionAuditError):
            protection.complete_execution(
                replace(execution, request_digest="sha256:substituted"),
                ok=True, result={}, post_state=[state],
            )


class TestCredentialBoundary(SystemProtectionBase):
    @mock.patch.object(credential_tool.provider_registry, "keyring_username_map")
    @mock.patch.object(credential_tool.keyring, "get_password")
    @mock.patch.object(credential_tool.keyring, "delete_password")
    @mock.patch.object(protection, "require_active_execution")
    def test_tool_credential_delete_failure_propagates(
        self, require_active, delete_password, get_password, username_map,
    ):
        username_map.return_value = {"openai": "openai-api-key"}
        delete_password.side_effect = RuntimeError("backend locked")
        get_password.return_value = "still-present"
        with self.assertRaisesRegex(RuntimeError, "remains present"):
            credential_tool.credential_store(
                "delete", "ora", "openai-api-key",
            )
        require_active.assert_called_once()

    def test_server_credential_delete_failure_propagates(self):
        from orchestrator import user_settings

        fake_keyring = mock.Mock()
        fake_keyring.delete_password.side_effect = RuntimeError("backend locked")
        fake_keyring.get_password.return_value = "still-present"
        with mock.patch.dict(sys.modules, {"keyring": fake_keyring}):
            with self.assertRaisesRegex(
                user_settings.SettingsError, "remains present",
            ):
                user_settings._delete_api_key_storage("openai")

    @mock.patch.object(credential_tool.provider_registry, "keyring_username_map")
    @mock.patch.object(credential_tool.keyring, "get_password")
    def test_tool_exposes_only_registry_bounded_existence(
        self, get_password, username_map,
    ):
        username_map.return_value = {"openai": "openai-api-key"}
        get_password.return_value = "never-return-this-value"
        self.assertIn("Credential present", credential_tool.credential_store(
            "status", "ora", "openai-api-key",
        ))
        self.assertNotIn("never-return", credential_tool.credential_store(
            "status", "ora", "openai-api-key",
        ))
        self.assertIn("unavailable", credential_tool.credential_store(
            "retrieve", "ora", "openai-api-key",
        ))
        self.assertIn("service must be", credential_tool.credential_store(
            "status", "other", "openai-api-key",
        ))
        self.assertIn("not declared", credential_tool.credential_store(
            "status", "ora", "arbitrary-account",
        ))

    @mock.patch.object(credential_tool.provider_registry, "keyring_username_map")
    @mock.patch.object(credential_tool.keyring, "set_password")
    def test_direct_tool_credential_mutation_has_no_effect(
        self, set_password, username_map,
    ):
        username_map.return_value = {"openai": "openai-api-key"}
        result = credential_tool.credential_store(
            "store", "ora", "openai-api-key", "secret",
        )
        self.assertIn("exact active system-protection receipt", result)
        set_password.assert_not_called()

    @mock.patch.object(credential_tool.provider_registry, "keyring_username_map")
    @mock.patch.object(credential_tool.keyring, "get_password")
    @mock.patch.object(credential_tool.keyring, "set_password")
    def test_exact_receipted_tool_credential_mutation_succeeds_once(
        self, set_password, get_password, username_map,
    ):
        username_map.return_value = {"openai": "openai-api-key"}
        get_password.side_effect = lambda *_: (
            "secret" if set_password.called else None
        )
        params = {
            "action": "store", "service": "ora",
            "username": "openai-api-key", "value": "secret",
        }
        selector = "credential:ora/openai-api-key"
        pre = protection.capture_selector_identity(selector)
        decision = protection.classify_action(
            "credential_store:store", selectors=[selector],
            mutability="irreversible", sensitivity="secret",
        )
        review, review_digest = protection.prepare_protection_request(
            decision, params_digest=protection.params_digest(params),
            pre_state=[pre], surface="tool_dispatcher",
        )
        approval_binding = {
            "request_digest": review_digest,
            "selectors": review["selectors"],
        }
        approval = tool_events.gate(
            "credential_store",
            {"category": "write", "mutability": "irreversible",
             "sensitivity": "secret", "egress": "none",
             "enforcement": "in_harness"},
            params=params, model_facing=True,
            approval_binding=approval_binding,
        )
        self.assertFalse(approval.allowed)
        self._approve_latest()
        approval = tool_events.gate(
            "credential_store",
            {"category": "write", "mutability": "irreversible",
             "sensitivity": "secret", "egress": "none",
             "enforcement": "in_harness"},
            params=params, model_facing=True,
            approval_binding=approval_binding,
        )
        self.assertTrue(approval.allowed)
        execution = protection.begin_execution(
            decision, approval_id=approval.approval_id,
            approval_action="credential_store",
            approval_args_hash=tool_events.normalize_args_hash(
                "credential_store", params,
            ),
            params_digest=protection.params_digest(params), pre_state=[pre],
            surface="tool_dispatcher",
        )
        with protection.protected_effect(execution):
            result = credential_tool.credential_store(**params)
        self.assertIn("Credential stored", result)
        set_password.assert_called_once_with(
            "ora", "openai-api-key", "secret",
        )
        post = protection.capture_selector_identity(selector)
        protection.complete_execution(
            execution, ok=True, result={"stored": True}, post_state=[post],
        )

    def test_provider_execution_resolves_only_registry_declared_identity(self):
        import boot

        registry = mock.Mock()
        registry.by_id.return_value = {
            "id": "openai", "env_var": "OPENAI_API_KEY",
            "keyring_username": "openai-api-key",
        }
        with mock.patch.object(boot, "_provider_registry", registry), \
                mock.patch.object(boot, "_provider_key", return_value="canonical") as resolver:
            self.assertEqual(boot._canonical_provider_key("openai"), "canonical")
        registry.by_id.assert_called_once_with("openai")
        resolver.assert_called_once_with(registry.by_id.return_value)
        with mock.patch.object(boot, "_provider_registry", None):
            self.assertEqual(boot._canonical_provider_key("openai"), "")


class TestSystemProtectionDocumentation(unittest.TestCase):
    def test_compound_server_deletions_declare_every_mutated_state_file(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / "server" / "app.py").read_text(encoding="utf-8")
        for token in (
            "settings_path = _user_settings._SETTINGS_PATH",
            "_sp.path_selector(settings_path)",
            "_sp.capture_path_identity(settings_path)",
            "_sp.path_selector(V3_THEMES_INDEX)",
            "_sp.capture_path_identity(V3_THEMES_INDEX)",
            "_sp.path_selector(ac.ACTIVE_POINTER_PATH)",
            "_sp.capture_path_identity(ac.ACTIVE_POINTER_PATH)",
        ):
            self.assertIn(token, source)

    def test_canonical_tracker_program_and_registry_preserve_tranche_boundary(self):
        root = Path(__file__).resolve().parents[2]
        vault = Path(
            os.environ.get(
                "ORA_VAULT",
                os.environ.get("ORA_VAULT_PATH", Path.home() / "Documents" / "vault"),
            )
        ) / "Projects" / "Ora"
        canonical = (
            vault / "Framework — System Protection and Outbound Security.md"
        ).read_text(encoding="utf-8")
        for token in (
            "single mechanical authority",
            "A protected effect occurs only after Ora classifies",
            "Approval cannot authorize",
            "HMAC-SHA-256 chain",
            "Public or caller-created approval records are rejected",
            "versioned HMAC-SHA-256-authenticated object",
            "Protection is reachability-based rather than spelling-based",
            "existing symlink/hardlink aliases",
            "inline task-approval marker in Dialogue history is never an authority record",
            "exact queue record and task fingerprint",
            "normalized selector set and exact authenticated pre-state",
            "exact linked Dialogue and Principal",
            "one immutable manifest-byte snapshot",
            "Semantic external-effect metadata",
            "known shell profile must describe every executable",
            "utility-bearing `env`",
            "before approval consumption",
            "bounded terminal `env` inspection",
            "present=false",
            "provider registry's declared environment or OS-keyring coordinates",
            "Standalone Programming",
            "installs no clock, scheduled cleanup, recovery sweep, cron job, or LaunchAgent",
            "Full G1.22 remains open",
            "Telegram and email credentials",
            "G1.24 retains ownership",
        ):
            self.assertIn(token, canonical)
        self.assertNotIn(
            "Full G1.22 is accepted",
            canonical,
        )

        records = "\n".join(
            (vault / name).read_text(encoding="utf-8")
            for name in (
                "Working — Ora Setup and Refinement.md",
                "Working — Framework — Ora Project Integration Program.md",
                "Registry — Ora Overview and Document Registry.md",
            )
        )
        for token in (
            "G1.19 is independently accepted",
            "G1.22A IMPLEMENTED / JUDGMENT PENDING",
            "G1.22A SECURITY CORRECTION SUBMITTED",
            "G1.22A RESIDUAL AUTHORITY CORRECTION SUBMITTED",
            "G1.22A SHELL-WRAPPER CORRECTION SUBMITTED",
            "fc731394128bcad5350c77d87248707274228c4c",
            "7fe125d9fa87e41bcb64be4bdc9db6967c1a9329",
            "independent re-judgment pending",
            "full G1.22 can pass",
            "G1.21 remains blocked on G1.17",
            "Static Windows refusal is fail-closed",
        ):
            self.assertIn(token, records)

        evidence = (
            root / "outputs" / "g1-22a" / "closeout-evidence.md"
        ).read_text(encoding="utf-8")
        for token in (
            "python3 -m pytest -q \\",
            "orchestrator/tests/test_g1_22a_system_protection.py",
            "python3 -m py_compile \\",
            "python3 scripts/verify-implementation.py --check drift",
            "fc731394128bcad5350c77d87248707274228c4c",
            "7fe125d9fa87e41bcb64be4bdc9db6967c1a9329",
            "eb202f3c4a99a6e011ee468e2b21470fb8b8e7e4",
            '"wrapped_subprocess_reached": false',
            "7 passed, 36 subtests passed",
            "git diff f7eb86a43f2c9c8970ea780908dc85abf83d29f2..HEAD --check",
            "git diff 7333a312685b7e8045a475392092c82bfca31ad0..7fe125d9fa87e41bcb64be4bdc9db6967c1a9329 --check",
            "git diff ac6a5236f1879bfce6591e7af7661c5dfbf7bea2..8a29cb4b51 --check",
            "git diff 63ad64b3d5..7e1f04fd4e --check",
            "git diff 7e1f04fd4e..44f53fc4d6 --check",
            "git diff d101a6c00a..eb202f3c4a --check",
            "G1.21 and G1.22B remain held",
        ):
            self.assertIn(token, evidence)


if __name__ == "__main__":
    unittest.main()
