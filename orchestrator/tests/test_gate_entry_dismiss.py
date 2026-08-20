"""A review-queue card must never become unresolvable.

Eleven execution-gate cards sat in the live queue from 2026-08-11 until they
were archived by hand: their approval requests had been consumed without the
cards being removed, so Approve and Deny both dead-ended at "[Unauthenticated
…]" and nothing in any surface could clear them. These tests pin the two
halves of that failure — a removal that fails silently, and a queue with no
way back — and the rule that keeps Dismiss from becoming a way to skip review.

Run::

    /opt/homebrew/bin/python3 -m pytest orchestrator/tests/test_gate_entry_dismiss.py -q
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import live_guard  # noqa: E402,F401  — arm the oversight write quarantine

import oversight_queue as oq  # noqa: E402
import tool_events  # noqa: E402
from orchestrator import resolution_chain  # noqa: E402


ACTION = "system_protection:dialogue_delete"
ARGS_HASH = "sha256:" + "a" * 64
NONCE = "n" * 48


class GateCardBase(unittest.TestCase):
    """A real queue file and a real approvals store, both in a tempdir."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.queue_path = self.root / "human-queue.jsonl"
        self.approvals = self.root / "execution-approvals.json"

        patchers = [
            mock.patch.object(tool_events, "APPROVALS_PATH", str(self.approvals)),
            mock.patch.object(oq, "_queue_path", lambda: str(self.queue_path)),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    # -- fixtures -------------------------------------------------------

    def write_card(self, *, entry_id="card-1", kind="execution_gate",
                   selector="dialogue:doomed", with_request=True,
                   consumed=False):
        """One queue card, optionally with the approval request behind it.

        The request is issued and bound through the real runtime helpers —
        the approvals store is schema-versioned and signed, so a hand-written
        one would only prove that a forged store is rejected.
        """
        nonce = None
        if with_request and kind in oq.GATE_KINDS:
            nonce = tool_events._register_pending_approval(
                ACTION, ARGS_HASH, None, "principal:user",
                review_request_digest=None, review_selectors=(selector,))
        record = {
            "kind": kind,
            "name": f"Gated: {ACTION}",
            "conversation_id": None,
            "event": {
                "event_type": "ExecutionGateBlocked",
                "action": ACTION,
                "args_hash": ARGS_HASH,
                "approval_nonce": nonce,
                "conversation_id": None,
                "principal_id": "principal:user",
                "review_request_digest": None,
                "review_selectors": [selector],
                "description": f"dialogue_delete: {selector}",
            },
            "verdict": {"verdict": "GATED", "reasoning": "irreversible"},
            "redefinition": False,
            "context_summary": {},
            "queued_at": "2026-08-11T14:18:46.097751+00:00",
            "id": entry_id,
            "engagement": "discussing",
            "discussion_conversation_id": f"resolve-{entry_id}",
        }
        with self.queue_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
        if nonce:
            bound = tool_events._bind_pending_queue(nonce, entry_id, record)
            self.assertTrue(bound, "fixture failed to bind its approval request")
            if consumed:
                spent = tool_events._consume_pending_approval(
                    {"id": entry_id, "kind": kind, "event": record["event"],
                     "conversation_id": None},
                    principal_id="principal:user")
                self.assertIsNotNone(spent, "fixture failed to spend the request")
        return record

    def queue_rows(self):
        if not self.queue_path.exists():
            return []
        return [json.loads(l) for l in
                self.queue_path.read_text(encoding="utf-8").splitlines() if l.strip()]


class SpentDetection(GateCardBase):

    def test_a_live_request_reads_as_resolvable(self):
        self.write_card()
        entry = oq.find_paused_by_id("card-1")
        self.assertFalse(oq.gate_entry_is_spent(entry))

    def test_a_consumed_request_reads_as_spent(self):
        """The exact 2026-08-11 state: approval consumed, card still listed."""
        self.write_card(consumed=True)
        entry = oq.find_paused_by_id("card-1")
        self.assertTrue(oq.gate_entry_is_spent(entry))

    def test_a_missing_request_reads_as_spent(self):
        self.write_card(with_request=False)
        entry = oq.find_paused_by_id("card-1")
        self.assertTrue(oq.gate_entry_is_spent(entry))

    def test_the_check_never_consumes_what_it_inspects(self):
        """A read-only check that spent its subject would create the bug."""
        self.write_card()
        entry = oq.find_paused_by_id("card-1")
        for _ in range(3):
            self.assertFalse(oq.gate_entry_is_spent(entry))
        stored = json.loads(self.approvals.read_text())
        self.assertFalse(stored["pending"][0]["consumed"])

    def test_a_redefinition_entry_is_never_spent(self):
        """Dismiss must not reach entries with their own resolution path."""
        self.write_card(entry_id="ped-1", kind="")
        entry = oq.find_paused_by_id("ped-1")
        self.assertFalse(oq.gate_entry_is_spent(entry))


class DismissRules(GateCardBase):

    def test_a_spent_card_can_finally_be_cleared(self):
        self.write_card(consumed=True)
        ok, message = oq.dismiss_spent_gate_entry("card-1")
        self.assertTrue(ok, message)
        self.assertEqual(self.queue_rows(), [])

    def test_a_live_card_is_refused(self):
        """Dismiss is a garbage collector, not a way to skip a review."""
        self.write_card()
        ok, message = oq.dismiss_spent_gate_entry("card-1")
        self.assertFalse(ok)
        self.assertIn("can still be approved or denied", message)
        self.assertEqual(len(self.queue_rows()), 1)

    def test_a_redefinition_entry_is_refused(self):
        self.write_card(entry_id="ped-1", kind="")
        ok, message = oq.dismiss_spent_gate_entry("ped-1")
        self.assertFalse(ok)
        self.assertIn("execution-gate", message)
        self.assertEqual(len(self.queue_rows()), 1)

    def test_an_unknown_id_is_refused(self):
        ok, message = oq.dismiss_spent_gate_entry("nope")
        self.assertFalse(ok)
        self.assertIn("No review-queue entry", message)

    def test_dismissing_one_card_leaves_the_others(self):
        for index in range(3):
            self.write_card(entry_id=f"card-{index}",
                            consumed=(index == 1))
        ok, _ = oq.dismiss_spent_gate_entry("card-1")
        self.assertTrue(ok)
        self.assertEqual([r["id"] for r in self.queue_rows()],
                         ["card-0", "card-2"])


class SilentRemovalFailure(GateCardBase):
    """The half of the bug that reported success while the card survived."""

    def _resolve(self):
        return resolution_chain._maybe_commit_gate_entry(
            "card-1", "resolve-card-1", approve=True,
            principal_id="principal:user")

    def test_a_skipped_removal_is_reported_not_swallowed(self):
        self.write_card()
        # Exactly what a Stealth context does: authority spent, card kept.
        with mock.patch.object(oq, "remove_by_id", return_value=False):
            message = self._resolve()
        self.assertIn("Approved", message)
        self.assertIn("could not be removed", message)
        self.assertIn("Dismiss", message)
        self.assertEqual(len(self.queue_rows()), 1)

    def test_a_successful_removal_says_nothing_extra(self):
        self.write_card()
        message = self._resolve()
        self.assertIn("Approved", message)
        self.assertNotIn("could not be removed", message)
        self.assertEqual(self.queue_rows(), [])

    def test_the_stranded_card_is_then_dismissable(self):
        """End to end: the 2026-08-11 dead end now has a way out."""
        self.write_card()
        with mock.patch.object(oq, "remove_by_id", return_value=False):
            self._resolve()
        entry = oq.find_paused_by_id("card-1")
        self.assertTrue(oq.gate_entry_is_spent(entry),
                        "approval was consumed, so the card is now spent")
        ok, _ = oq.dismiss_spent_gate_entry("card-1")
        self.assertTrue(ok)
        self.assertEqual(self.queue_rows(), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
