"""Focused G1.21 proofs for the one manual Fastmail email action."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
if str(ORCHESTRATOR) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import email_channel  # noqa: E402
import oversight_queue  # noqa: E402
import runtime_hygiene  # noqa: E402
import system_protection  # noqa: E402
import tool_events  # noqa: E402
import triggers  # noqa: E402


class ProviderDouble:
    def __init__(self):
        self.calls = []

    def send(self, message, *, on_provider_contact=None):
        if on_provider_contact is not None:
            on_provider_contact()
        self.calls.append(message)
        return {"provider_message_id": "double-1"}


class FailingAfterContactProvider(ProviderDouble):
    def send(self, message, *, on_provider_contact=None):
        if on_provider_contact is not None:
            on_provider_contact()
        raise RuntimeError("provider rejected the submission")


class EmailBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "config.json").write_text(json.dumps({
            "channel": {"email": {
                "enabled": True,
                "mask_mailbox": "sender@example.com",
                "recipient_allowlist": ["recipient@example.com"],
            }},
        }), encoding="utf-8")
        self.data = root / "data"
        self.data.mkdir()
        self.actions = str(root / "actions.jsonl")
        self.approvals = str(root / "approvals.json")
        self.queue_path = str(root / "queue.jsonl")
        self.events = str(root / "events.jsonl")
        self.patches = [
            mock.patch.object(runtime_hygiene._rp, "DATA_DIR_STR", str(self.data)),
            mock.patch.object(tool_events, "APPROVALS_PATH", self.approvals),
            mock.patch.object(tool_events, "GLOBAL_SINK_DEFAULT", self.events),
            mock.patch.object(oversight_queue, "HUMAN_QUEUE_PATH", self.queue_path),
            mock.patch.object(system_protection, "_actions_path", return_value=self.actions),
            mock.patch.object(email_channel._runtime_paths, "ORA_HOME", root),
        ]
        for patcher in self.patches:
            patcher.start()
        self.turn = tool_events.set_turn_context(
            conversation_id="g1-21-test", surface="test",
        )
        tool_events._queued_hashes.clear()
        self.service = triggers.TriggerService(
            queue=runtime_hygiene.DeadlineQueue(self.data / "runtime-hygiene"),
            executor=lambda work: work(),
        )
        self.provider = ProviderDouble()
        self.action = {
            "kind": "email_send", "to": ["recipient@example.com"],
            "subject": "Exact subject", "body": "Exact body",
            "from_email": "sender@example.com",
        }

    def tearDown(self):
        tool_events._queued_hashes.clear()
        tool_events.reset_turn_context(self.turn)
        for patcher in reversed(self.patches):
            patcher.stop()
        self.tmp.cleanup()

    def create_active(self):
        self.service.create({
            "trigger_id": "mail", "name": "Manual email",
            "cause": "manual", "condition": {}, "action": self.action,
        })
        review = self.service.activation_review("mail")
        self.service.activate("mail", expected_spec_digest=review["spec_digest"])

    def approve_latest(self):
        entry = oversight_queue.list_paused()[-1]
        return tool_events.resolve_gate_entry(entry.to_dict(), approve=True)


class EmailSliceTests(EmailBase):
    def test_inspection_resolves_persona_and_does_not_call_provider(self):
        message = email_channel.prepare_message(self.action)
        self.assertIn("Sent by Ora, an AI assistant", message.visible_body)
        self.assertIn("X-Ora-Assistant:\r\n Ora;", message.mime.decode())
        self.assertEqual(self.provider.calls, [])

    def test_only_email_send_is_opened(self):
        opened = system_protection.classify_action(
            "email_send", selectors=["email:provider/fastmail"],
            mutability="read", sensitivity="public", egress="none",
        )
        self.assertEqual(opened.outcome, "review")
        for action in ("email_receive", "telegram_send", "channel_send"):
            self.assertEqual(system_protection.classify_action(
                action, selectors=["email:provider/fastmail"],
                mutability="external_write", egress="external",
            ).outcome, "deny")

    def test_unauthorized_request_queues_and_exact_reissue_sends_once(self):
        self.create_active()
        with mock.patch.object(email_channel, "_default_provider", return_value=self.provider):
            self.service.run_manual("mail", request_id="blocked")
            self.assertEqual(self.provider.calls, [])
            self.assertEqual(len(oversight_queue.list_paused()), 1)
            self.approve_latest()
            self.service.run_manual("mail", request_id="approved")
        self.assertEqual(len(self.provider.calls), 1)
        rows = self.service.firings("mail", limit=0)
        self.assertEqual(rows[0]["outcome"], "sent")
        self.assertTrue(rows[0]["receipt"]["provider_contacted"])
        audit = [json.loads(line) for line in Path(self.actions).read_text().splitlines()]
        self.assertEqual(
            [row["event_type"] for row in audit if row.get("execution_id")],
            ["protected_action_started", "protected_action_completed"],
        )

    def test_rollback_before_provider_contact_revokes_and_retires(self):
        self.create_active()
        self.service.run_manual("mail", request_id="blocked")
        self.assertEqual(len(oversight_queue.list_paused()), 1)
        result = self.service.rollback("mail")
        self.assertEqual(result["status"], "retired")
        self.assertEqual(result["rollback"]["queue_cards_removed"], 1)
        self.assertEqual(oversight_queue.list_paused(), [])
        self.assertEqual(self.provider.calls, [])

    def test_rollback_after_provider_contact_is_not_recall(self):
        self.create_active()
        with mock.patch.object(email_channel, "_default_provider", return_value=self.provider):
            self.service.run_manual("mail", request_id="blocked")
            self.approve_latest()
            self.service.run_manual("mail", request_id="approved")
        with self.assertRaises(triggers.TriggerConflict) as caught:
            self.service.rollback("mail")
        self.assertIn("cannot recall", str(caught.exception))

    def test_provider_failure_after_contact_remains_non_recallable(self):
        self.create_active()
        failing = FailingAfterContactProvider()
        with mock.patch.object(email_channel, "_default_provider", return_value=failing):
            self.service.run_manual("mail", request_id="blocked")
            self.approve_latest()
            self.service.run_manual("mail", request_id="approved")
        firing = self.service.firings("mail", limit=0)[0]
        self.assertEqual(firing["status"], "failed")
        self.assertTrue(firing["receipt"]["provider_contacted"])
        with self.assertRaises(triggers.TriggerConflict):
            self.service.rollback("mail")

    def test_email_trigger_cannot_be_scheduled(self):
        with self.assertRaises(triggers.TriggerInputRequired) as caught:
            triggers.normalize_spec({
                "trigger_id": "scheduled-mail", "name": "No schedule",
                "cause": "calendar", "condition": {"schedule": {
                    "timezone": "UTC", "local_time": "09:00", "cadence": "daily",
                    "weekdays": [], "start_date": "2026-01-01",
                    "missed_policy": "run_once", "grace_seconds": 300,
                }}, "runtime_justification": "time is the provider cause and no event exists",
                "action": self.action,
            })
        self.assertIn("manual-only", str(caught.exception))

    def test_recipient_outside_configured_allowlist_is_refused(self):
        action = dict(self.action, to=["outside@example.com"])
        with self.assertRaises(email_channel.EmailInputError) as caught:
            email_channel.prepare_message(action)
        self.assertIn("recipient_allowlist", str(caught.exception))

    def test_missing_credential_does_not_mark_provider_contact(self):
        marks = []
        provider = email_channel.FastmailJMAPProvider(token=None)
        with mock.patch.object(email_channel, "keyring") as keyring:
            with self.assertRaises(system_protection.ProtectionDenied):
                provider.send(email_channel.prepare_message(self.action),
                              on_provider_contact=lambda: marks.append(True))
        self.assertEqual(marks, [])

    def test_jmap_send_requires_both_creation_results(self):
        good = [
            ["Email/set", {"created": {"ora-draft": {"id": "draft-1"}}}, "draft"],
            ["EmailSubmission/set", {
                "created": {"ora-submission": {"id": "submission-1"}},
            }, "submission"],
        ]
        email_channel.FastmailJMAPProvider._validate_method_responses(
            good, expected=("Email/set", "EmailSubmission/set"),
            required_created_ids=("ora-draft", "ora-submission"),
        )
        for index in range(2):
            incomplete = json.loads(json.dumps(good))
            incomplete[index][1]["created"] = {}
            with self.assertRaises(email_channel.EmailChannelError):
                email_channel.FastmailJMAPProvider._validate_method_responses(
                    incomplete, expected=("Email/set", "EmailSubmission/set"),
                    required_created_ids=("ora-draft", "ora-submission"),
                )

    def test_rollback_lock_blocks_a_run_admitted_at_the_same_time(self):
        self.create_active()
        self.service.run_manual("mail", request_id="blocked")
        self.approve_latest()
        entered = threading.Event()
        release = threading.Event()
        run_done = threading.Event()
        run_errors = []

        def blocking_rollback(action, trigger_id):
            entered.set()
            self.assertTrue(release.wait(2))
            return {"tokens_revoked": 1, "queue_cards_removed": 0}

        with mock.patch.object(email_channel, "rollback_authority",
                               side_effect=blocking_rollback):
            rollback_result = []
            rollback_errors = []

            def do_rollback():
                try:
                    rollback_result.append(self.service.rollback("mail"))
                except Exception as exc:  # pragma: no cover - assertion below
                    rollback_errors.append(exc)

            rollback_thread = threading.Thread(target=do_rollback)
            rollback_thread.start()
            self.assertTrue(entered.wait(2))

            def do_run():
                try:
                    self.service.run_manual("mail", request_id="racing")
                except Exception as exc:
                    run_errors.append(exc)
                finally:
                    run_done.set()

            run_thread = threading.Thread(target=do_run)
            run_thread.start()
            self.assertFalse(run_done.wait(0.1))
            release.set()
            rollback_thread.join(2)
            run_thread.join(2)

        self.assertEqual(rollback_errors, [])
        self.assertEqual(rollback_result[0]["status"], "retired")
        self.assertTrue(run_done.is_set())
        self.assertTrue(any(isinstance(exc, triggers.TriggerConflict)
                            for exc in run_errors))
        self.assertEqual(self.provider.calls, [])


if __name__ == "__main__":
    unittest.main()
