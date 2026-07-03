"""Tests for the Execution Review Phase 1 instrumentation core
(orchestrator/tool_events.py): axis vocabularies, manifest fail-closed
default, path-sensitivity resolution, protected-config paths, content
scrub, recorder sinks + redaction + stealth, telemetry health, approval
tokens, standing allows, the execution gate, and the evidence-runner
check vocabulary."""

from __future__ import annotations

import contextvars
import json
import os
import sys
import tempfile
import threading
import unittest

from pathlib import Path
_ORCH = Path(__file__).resolve().parent.parent
if str(_ORCH) not in sys.path:
    sys.path.insert(0, str(_ORCH))
_TOOLS = _ORCH / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.append(str(_TOOLS))

import tool_events  # noqa: E402


def _read_events(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


class ToolEventsBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sink = os.path.join(self.tmp.name, "tool-events.jsonl")
        self.approvals = os.path.join(self.tmp.name, "execution-approvals.json")
        self._orig_sink = tool_events.GLOBAL_SINK_DEFAULT
        self._orig_approvals = tool_events.APPROVALS_PATH
        tool_events.GLOBAL_SINK_DEFAULT = self.sink
        tool_events.APPROVALS_PATH = self.approvals
        tool_events.reset_telemetry_health()
        tool_events._queued_hashes.clear()
        self._orig_te_env = os.environ.pop("ORA_TOOL_EVENTS", None)
        tool_events.set_turn_context()  # clean context

    def tearDown(self):
        tool_events.GLOBAL_SINK_DEFAULT = self._orig_sink
        tool_events.APPROVALS_PATH = self._orig_approvals
        tool_events.reset_telemetry_health()
        tool_events._queued_hashes.clear()
        if self._orig_te_env is not None:
            os.environ["ORA_TOOL_EVENTS"] = self._orig_te_env
        self.tmp.cleanup()


class TestVocabularies(ToolEventsBase):
    def test_validate_axes_accepts_valid(self):
        self.assertEqual(tool_events.validate_axes(
            {"mutability": "read", "sensitivity": "public",
             "egress": "none"}), [])

    def test_validate_axes_rejects_typos(self):
        errors = tool_events.validate_axes(
            {"mutability": "readable", "sensitivity": "public",
             "egress": "none"})
        self.assertEqual(len(errors), 1)

    def test_fail_closed_default(self):
        axes = tool_events.manifest_axes("never-heard-of-this-action")
        self.assertEqual(axes["mutability"], "irreversible")
        self.assertEqual(axes["sensitivity"], "secret")
        self.assertTrue(axes["unknown"])

    def test_manifest_actions_carry_valid_axes(self):
        for action, entry in tool_events.ACTION_MANIFEST.items():
            self.assertEqual(tool_events.validate_axes(entry), [],
                             f"invalid axes on manifest action {action}")

    def test_max_helpers(self):
        self.assertEqual(tool_events.max_mutability("read", "external_write"),
                         "external_write")
        self.assertEqual(tool_events.max_sensitivity("private", "secret"),
                         "secret")


class TestPathResolution(ToolEventsBase):
    def test_secret_paths(self):
        for p in ("~/.ssh/id_rsa", "~/.aws/credentials",
                  "~/.config/ora/openrouter-api-key", "/x/secrets/a.txt"):
            self.assertEqual(tool_events.resolve_path_sensitivity(p), "secret", p)

    def test_tokenizer_is_not_secret(self):
        # Boundary-anchored patterns: 'token' must not match 'tokenizer'.
        self.assertNotEqual(tool_events.resolve_path_sensitivity(
            os.path.expanduser("~/ora/models/x/tokenizer.json")), "secret")

    def test_key_material_is_secret(self):
        for p in ("~/ora/server.pem", "~/ora/server.key", "~/ora/prod.pem.txt",
                  "~/ora/x.p12", "~/ora/x.pfx", "~/ora/env.local",
                  "~/ora/.env.production", "~/ora/private_keys/a",
                  "~/ora/.ssh2/known_hosts", "~/ora/id_dsa"):
            self.assertEqual(tool_events.resolve_path_sensitivity(p), "secret",
                             p)

    def test_key_material_false_positives_stay_private(self):
        # Boundary-anchored: these must NOT be classed secret.
        for p in ("~/ora/monkey.txt", "~/ora/tokenizer.json",
                  "~/ora/src/keyboard.py", "~/ora/secrets_of_success.md",
                  "~/ora/secret_santa_list.md"):
            self.assertEqual(tool_events.resolve_path_sensitivity(p), "private",
                             p)

    def test_keys_dir_and_creds_are_sensitive(self):
        for p in ("~/ora/keys/priv.txt", "~/ora/creds.txt"):
            self.assertIn(tool_events.resolve_path_sensitivity(p),
                          ("secret", "sensitive"), p)

    def test_capture_dirs_are_sensitive(self):
        self.assertEqual(tool_events.resolve_path_sensitivity(
            os.path.expanduser("~/ora/captures/x.mov")), "sensitive")
        self.assertEqual(tool_events.resolve_path_sensitivity(
            os.path.expanduser("~/ora/sessions/conv-1/captures/x.mov")),
            "sensitive")

    def test_workspace_is_private_unknown_is_sensitive(self):
        self.assertEqual(tool_events.resolve_path_sensitivity(
            os.path.expanduser("~/ora/orchestrator/boot.py")), "private")
        self.assertEqual(tool_events.resolve_path_sensitivity(
            "/opt/somewhere/else.txt"), "sensitive")

    def test_protected_config_paths(self):
        for p in ("~/ora/config/hooks/evil.json",
                  "~/ora/config/mcp-servers.json",
                  "~/ora/orchestrator/tool_events.py",
                  "~/ora/server/server.py",
                  "~/ora/data/projects/msi.json",
                  "~/sites/x/ora-project.json",
                  "~/ora/.ora/evidence.yaml"):
            self.assertTrue(tool_events.is_protected_config_path(p), p)

    def test_normal_paths_not_protected(self):
        for p in ("~/ora/modes/synthesis.md", "~/Documents/vault/note.md",
                  "~/ora/config/interface.json"):
            self.assertFalse(tool_events.is_protected_config_path(p), p)


class TestContentScrub(ToolEventsBase):
    def test_scrubs_inline_url_token(self):
        text, hit = tool_events.scrub_content(
            "git push https://user:hunter2secret@github.com/x/y.git")
        self.assertTrue(hit)
        self.assertNotIn("hunter2secret", text)

    def test_scrubs_api_keys(self):
        for sample in ("sk-abcdefghijklmnop1234",
                       "ghp_abcdefghij1234567890",
                       "AKIAIOSFODNN7EXAMPLE",
                       "api_key=verysecret123"):
            text, hit = tool_events.scrub_content(f"arg {sample} tail")
            self.assertTrue(hit, sample)
            self.assertIn("[SCRUBBED]", text)

    def test_leaves_normal_text(self):
        text, hit = tool_events.scrub_content("ls -la ~/ora")
        self.assertFalse(hit)
        self.assertEqual(text, "ls -la ~/ora")


class TestRecorder(ToolEventsBase):
    def _event(self, **over):
        base = {"event": "tool", "action": "file_read", "category": "read",
                "mutability": "read", "sensitivity": "private",
                "egress": "none", "args_redacted": {"path": "/x"},
                "exit": {"ok": True}, "enforcement_model": "in_harness"}
        base.update(over)
        return base

    def test_writes_to_global_sink_without_turn(self):
        tool_events.record(self._event())
        events = _read_events(self.sink)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["action"], "file_read")

    def test_writes_to_trace_dir_when_turn_active(self):
        trace = os.path.join(self.tmp.name, "trace")
        os.makedirs(trace)
        tool_events.set_turn_context(trace_dir=trace, conversation_id="c1",
                                     surface="chat")
        tool_events.record(self._event())
        self.assertEqual(_read_events(self.sink), [])
        events = _read_events(os.path.join(trace, "tool-events.jsonl"))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["correlation"]["conversation_id"], "c1")
        self.assertEqual(events[0]["conversation_id"], "c1")  # purge matcher

    def test_secret_redacts_to_existence_only(self):
        tool_events.record(self._event(sensitivity="secret",
                                       args_redacted={"value": "tok123"}))
        ev = _read_events(self.sink)[0]
        self.assertNotIn("args_redacted", ev)
        self.assertNotIn("reads", ev)
        self.assertEqual(ev["content_redacted"], "secret-existence-only")

    def test_sensitive_scrubs_to_descriptors(self):
        tool_events.record(self._event(sensitivity="sensitive",
                                       args_redacted={"path": "/x/secret-place"}))
        ev = _read_events(self.sink)[0]
        self.assertNotIn("secret-place", json.dumps(ev))

    def test_content_scrub_applied_to_args(self):
        tool_events.record(self._event(
            args_redacted={"command": "curl -H 'Authorization: bearer abcdef0123456789abcdef'"}))
        ev = _read_events(self.sink)[0]
        self.assertNotIn("abcdef0123456789", json.dumps(ev))

    def test_stealth_suppresses_content_events(self):
        tool_events.set_turn_context(conversation_id="c-stealth", stealth=True)
        tool_events.record(self._event())
        self.assertEqual(_read_events(self.sink), [])

    def test_stealth_gate_decision_recorded_existence_only(self):
        tool_events.set_turn_context(conversation_id="c-stealth", stealth=True)
        tool_events.record(self._event(
            event="gate", args_redacted={"command": "secret thing"},
            gate={"decision": "blocked", "why": "irreversible"}))
        events = _read_events(self.sink)
        self.assertEqual(len(events), 1)
        self.assertNotIn("secret thing", json.dumps(events[0]))
        self.assertEqual(events[0]["gate"]["decision"], "blocked")

    def test_oversized_line_truncated(self):
        # args values are per-field capped at 400 chars, so the realistic
        # oversize vector is a huge reads list (e.g., a wide RAG retrieval).
        big_reads = [{"what": f"doc-{i}-" + "x" * 200, "where": "local"}
                     for i in range(80)]
        tool_events.record(self._event(reads=big_reads))
        ev = _read_events(self.sink)[0]
        self.assertTrue(ev.get("truncated"))
        self.assertNotIn("reads", ev)  # dropped to fit the line cap

    def test_recorder_failure_sets_health_and_stamps_later_events(self):
        # Point the sink somewhere unwritable: a path UNDER a regular file.
        blocker = os.path.join(self.tmp.name, "blocker")
        with open(blocker, "w") as f:
            f.write("x")
        tool_events.GLOBAL_SINK_DEFAULT = os.path.join(blocker, "nope.jsonl")
        tool_events.record(self._event())
        health = tool_events.get_telemetry_health()
        self.assertTrue(health["incomplete"])
        self.assertGreaterEqual(health["failures"], 1)
        # Recovery: later events carry the incompleteness flag.
        tool_events.GLOBAL_SINK_DEFAULT = self.sink
        tool_events.record(self._event())
        ev = _read_events(self.sink)[0]
        self.assertTrue(ev.get("telemetry_incomplete"))

    def test_contextvars_reach_spawned_thread_via_copy_context(self):
        tool_events.set_turn_context(conversation_id="c-thread", stealth=True)
        ctx = contextvars.copy_context()
        results = []

        def _in_thread():
            results.append(tool_events.get_turn_context())

        # With the snapshot (subagent.py pattern) the stealth flag arrives...
        t = threading.Thread(target=lambda: ctx.run(_in_thread))
        t.start(); t.join()
        self.assertTrue(results[0]["stealth"])
        # ...without it, a bare thread sees no stealth flag (the leak the
        # snapshot exists to prevent).
        t2 = threading.Thread(target=_in_thread)
        t2.start(); t2.join()
        self.assertFalse(results[1]["stealth"])


class TestApprovals(ToolEventsBase):
    def test_one_shot_token_round_trip(self):
        args_hash = tool_events.normalize_args_hash("bash_execute",
                                                    {"command": "systemctl restart x"})
        tool_events.grant_approval("bash_execute", args_hash, "conv-1")
        # First matching call consumes it...
        self.assertIsNotNone(tool_events.check_and_consume_approval(
            "bash_execute", args_hash, "conv-1"))
        # ...second call finds nothing.
        self.assertIsNone(tool_events.check_and_consume_approval(
            "bash_execute", args_hash, "conv-1"))

    def test_token_does_not_match_different_args(self):
        args_hash = tool_events.normalize_args_hash("bash_execute",
                                                    {"command": "a"})
        tool_events.grant_approval("bash_execute", args_hash)
        other = tool_events.normalize_args_hash("bash_execute",
                                                {"command": "b"})
        self.assertIsNone(tool_events.check_and_consume_approval(
            "bash_execute", other))

    def test_conversation_scoped_token_requires_exact_match(self):
        h = tool_events.normalize_args_hash("x", {})
        tool_events.grant_approval("x", h, conversation_id="conv-1")
        # A call with NO conversation context must NOT consume it.
        self.assertIsNone(tool_events.check_and_consume_approval("x", h, None))
        # A call from a DIFFERENT conversation must NOT consume it.
        self.assertIsNone(tool_events.check_and_consume_approval(
            "x", h, "conv-2"))
        # Only the exact conversation consumes it.
        self.assertIsNotNone(tool_events.check_and_consume_approval(
            "x", h, "conv-1"))

    def test_unscoped_token_consumable_by_any_context(self):
        h = tool_events.normalize_args_hash("y", {})
        tool_events.grant_approval("y", h)  # no conversation scope
        self.assertIsNotNone(tool_events.check_and_consume_approval(
            "y", h, "any-conv"))

    def test_expired_token_rejected(self):
        args_hash = tool_events.normalize_args_hash("x", {})
        tool_events.grant_approval("x", args_hash, ttl_s=-1)
        self.assertIsNone(tool_events.check_and_consume_approval("x", args_hash))

    def test_standing_allow_grant_and_revoke(self):
        scope = "credential_store:github"
        self.assertFalse(tool_events.has_standing_allow(scope))
        tool_events.grant_standing_allow(scope)
        self.assertTrue(tool_events.has_standing_allow(scope))
        self.assertTrue(tool_events.revoke_standing_allow(scope))
        self.assertFalse(tool_events.has_standing_allow(scope))


class TestGate(ToolEventsBase):
    def _gate(self, **over):
        axes = {"category": "execute", "mutability": "read",
                "sensitivity": "private", "egress": "none"}
        axes.update(over.pop("axes", {}))
        return tool_events.gate("test_action", axes, **over)

    def test_reads_and_reversible_writes_allowed(self):
        self.assertTrue(self._gate().allowed)
        self.assertTrue(self._gate(
            axes={"mutability": "reversible_write"}).allowed)

    def test_irreversible_blocked(self):
        d = self._gate(axes={"mutability": "irreversible"})
        self.assertFalse(d.allowed)

    def test_unknown_blocked(self):
        d = self._gate(axes={"unknown": True})
        self.assertFalse(d.allowed)

    def test_secret_blocked(self):
        d = self._gate(axes={"sensitivity": "secret"})
        self.assertFalse(d.allowed)

    def test_sensitive_blocked_on_model_facing_surface(self):
        d = self._gate(axes={"sensitivity": "sensitive"})
        self.assertFalse(d.allowed)
        # ...but allowed on a user-initiated (non-model) surface.
        d2 = self._gate(axes={"sensitivity": "sensitive"}, model_facing=False)
        self.assertTrue(d2.allowed)

    def test_every_gate_decision_recorded(self):
        self._gate(axes={"mutability": "irreversible"})
        decisions = [e["gate"]["decision"] for e in _read_events(self.sink)
                     if e.get("event") == "gate"]
        self.assertTrue(decisions)

    def test_approval_token_unlocks_exactly_once(self):
        params = {"command": "prod-deploy"}
        d1 = self._gate(axes={"mutability": "irreversible"}, params=params)
        self.assertFalse(d1.allowed)
        args_hash = tool_events.normalize_args_hash("test_action", params)
        tool_events.grant_approval("test_action", args_hash)
        d2 = self._gate(axes={"mutability": "irreversible"}, params=params)
        self.assertTrue(d2.allowed)
        self.assertEqual(d2.decision, "approved")
        tool_events._queued_hashes.clear()
        d3 = self._gate(axes={"mutability": "irreversible"}, params=params)
        self.assertFalse(d3.allowed)

    def test_live_approver_approves_and_denies(self):
        d = self._gate(axes={"mutability": "irreversible"},
                       params={"command": "x"},
                       interactive_approver=lambda *a: True)
        self.assertTrue(d.allowed)
        d2 = self._gate(axes={"mutability": "irreversible"},
                        params={"command": "y"},
                        interactive_approver=lambda *a: False)
        self.assertFalse(d2.allowed)
        self.assertIn("denied by user", d2.message)

    def test_block_queues_paused_entry_with_kind(self):
        import oversight_queue
        orig = oversight_queue.HUMAN_QUEUE_PATH
        oversight_queue.HUMAN_QUEUE_PATH = os.path.join(self.tmp.name,
                                                        "human-queue.jsonl")
        try:
            d = self._gate(axes={"mutability": "irreversible"},
                           params={"command": "deploy"},
                           description="deploy the thing")
            self.assertFalse(d.allowed)
            self.assertEqual(d.decision, "queued")
            with open(oversight_queue.HUMAN_QUEUE_PATH) as f:
                rec = json.loads(f.readline())
            self.assertEqual(rec["kind"], "execution_gate")
            self.assertTrue(rec["name"].startswith("Gated: test_action"))
            self.assertEqual(rec["event"]["event_type"], "ExecutionGateBlocked")
        finally:
            oversight_queue.HUMAN_QUEUE_PATH = orig

    def test_repeat_block_dedupes_queue(self):
        import oversight_queue
        orig = oversight_queue.HUMAN_QUEUE_PATH
        oversight_queue.HUMAN_QUEUE_PATH = os.path.join(self.tmp.name,
                                                        "human-queue.jsonl")
        try:
            for _ in range(3):
                self._gate(axes={"mutability": "irreversible"},
                           params={"command": "same"})
            with open(oversight_queue.HUMAN_QUEUE_PATH) as f:
                lines = [l for l in f if l.strip()]
            self.assertEqual(len(lines), 1)
        finally:
            oversight_queue.HUMAN_QUEUE_PATH = orig

    def test_stealth_block_never_queues(self):
        import oversight_queue
        orig = oversight_queue.HUMAN_QUEUE_PATH
        oversight_queue.HUMAN_QUEUE_PATH = os.path.join(self.tmp.name,
                                                        "human-queue.jsonl")
        try:
            tool_events.set_turn_context(conversation_id="c-s", stealth=True)
            d = self._gate(axes={"mutability": "irreversible"},
                           params={"command": "hidden"})
            self.assertFalse(d.allowed)
            self.assertFalse(os.path.exists(oversight_queue.HUMAN_QUEUE_PATH))
        finally:
            oversight_queue.HUMAN_QUEUE_PATH = orig

    def test_queue_failure_still_blocks(self):
        import oversight_queue
        orig = oversight_queue.HUMAN_QUEUE_PATH
        blocker = os.path.join(self.tmp.name, "qblock")
        with open(blocker, "w") as f:
            f.write("x")
        oversight_queue.HUMAN_QUEUE_PATH = os.path.join(blocker, "q.jsonl")
        try:
            d = self._gate(axes={"mutability": "irreversible"},
                           params={"command": "z"})
            self.assertFalse(d.allowed)  # fail closed regardless
            self.assertIn("approval queue unavailable", d.message)
        finally:
            oversight_queue.HUMAN_QUEUE_PATH = orig


class TestResolveGateEntry(ToolEventsBase):
    def test_approve_grants_one_shot(self):
        record = {"kind": "execution_gate", "conversation_id": "c1",
                  "event": {"action": "bash_execute", "args_hash": "abc123"}}
        msg = tool_events.resolve_gate_entry(record, approve=True)
        self.assertIn("One-shot token", msg)
        self.assertIsNotNone(tool_events.check_and_consume_approval(
            "bash_execute", "abc123", "c1"))

    def test_approve_standing_scope(self):
        record = {"kind": "execution_gate",
                  "event": {"action": "credential_store", "args_hash": "h",
                            "standing_scope": "credential_store:svc"}}
        msg = tool_events.resolve_gate_entry(record, approve=True)
        self.assertIn("Standing allow", msg)
        self.assertIn("Revoke", msg)
        self.assertTrue(tool_events.has_standing_allow("credential_store:svc"))

    def test_deny_keeps_block(self):
        record = {"kind": "execution_gate",
                  "event": {"action": "bash_execute", "args_hash": "h2"}}
        msg = tool_events.resolve_gate_entry(record, approve=False,
                                             reason="not now")
        self.assertIn("Denied", msg)
        self.assertIsNone(tool_events.check_and_consume_approval(
            "bash_execute", "h2"))


class TestEvidenceVocabulary(ToolEventsBase):
    def test_valid_check(self):
        self.assertEqual(tool_events.validate_check_declaration(
            {"cmd": "npm test", "timeout": 600, "mutates": False,
             "network": "deny"}), [])

    def test_invalid_check(self):
        errors = tool_events.validate_check_declaration(
            {"timeout": "long", "network": "sometimes", "mutates": "no"})
        self.assertEqual(len(errors), 4)  # no cmd + 3 bad fields


class TestMCPAxes(ToolEventsBase):
    def test_undeclared_server_fails_closed(self):
        tool_events.reset_mcp_axes_cache()
        axes = tool_events.mcp_axes("mcp_nosuchserver_do_thing")
        self.assertTrue(axes.get("unknown"))
        self.assertEqual(axes["enforcement"], "boundary_only")


if __name__ == "__main__":
    unittest.main()
