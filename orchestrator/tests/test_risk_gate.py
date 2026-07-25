"""Execution Review Phase 2 — risk_gate unit tests (classifier, /risk parse,
fingerprint, task tokens, task-gate marker, route_observed fold)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_ORCH = Path(__file__).resolve().parent.parent
if str(_ORCH) not in sys.path:
    sys.path.insert(0, str(_ORCH))
_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
import live_guard  # noqa: E402,F401 — quarantines durable oversight/telemetry writes

import risk_gate as rg  # noqa: E402
import tool_events as te  # noqa: E402


class TestTierOrdering(unittest.TestCase):
    def test_tier_max(self):
        self.assertEqual(rg.tier_max("light", "irreversible"), "irreversible")
        self.assertEqual(rg.tier_max("standard", "high-risk"), "high-risk")
        self.assertEqual(rg.tier_max("", None), rg.DEFAULT_TIER)
        self.assertEqual(rg.tier_max("light", "standard", "light"), "standard")

    def test_tier_at_least(self):
        self.assertTrue(rg.tier_at_least("irreversible", "standard"))
        self.assertFalse(rg.tier_at_least("light", "standard"))


class TestStageAFloor(unittest.TestCase):
    def test_irreversible_intents_floor_irreversible(self):
        for txt in ("deploy this to production",
                    "send an email to the client list",
                    "git push --force to origin",
                    "publish the article now",
                    "charge the customer's card $40",
                    "drop table users",
                    "force-push the rebased branch"):
            floor, fired = rg.stage_a_floor(txt)
            self.assertEqual(floor, "irreversible", txt)
            self.assertTrue(fired)

    def test_external_write_intents_floor_high_risk(self):
        for txt in ("open a pull request for this",
                    "push the branch to origin",
                    "upload the build to the S3 bucket"):
            floor, _ = rg.stage_a_floor(txt)
            self.assertEqual(floor, "high-risk", txt)

    def test_ordinary_text_no_floor(self):
        for txt in ("explain this function",
                    "summarize the architecture",
                    "what are the tradeoffs of event sourcing"):
            floor, fired = rg.stage_a_floor(txt)
            self.assertIsNone(floor, txt)
            self.assertEqual(fired, [])

    def test_irreversible_wins_over_external_write(self):
        floor, _ = rg.stage_a_floor("commit and push then deploy to production")
        self.assertEqual(floor, "irreversible")


class TestModeTierHeading(unittest.TestCase):
    def test_extracts_heading(self):
        body = "# Mode\n\n## RISK TIER\nhigh-risk\n\n## DEFAULT GEAR\n4\n"
        self.assertEqual(rg.extract_mode_risk_tier(body), "high-risk")

    def test_absent_returns_none(self):
        self.assertIsNone(rg.extract_mode_risk_tier("# Mode\n\n## DEFAULT GEAR\n3"))
        self.assertIsNone(rg.extract_mode_risk_tier(None))

    def test_unknown_value_returns_none(self):
        self.assertIsNone(rg.extract_mode_risk_tier("## RISK TIER\nbananas\n"))


class TestClassify(unittest.TestCase):
    def test_default_is_standard(self):
        r = rg.classify_tier("explain this function")
        self.assertEqual(r["risk_tier"], "standard")
        self.assertTrue(r["default_used"])

    def test_trivial_text_defaults_light(self):
        r = rg.classify_tier("hi there", is_trivial_text=True)
        self.assertEqual(r["risk_tier"], "light")

    def test_stage_a_floor_raises(self):
        r = rg.classify_tier("send this as an email to everyone")
        self.assertEqual(r["risk_tier"], "irreversible")
        self.assertEqual(r["source"], "floors")

    def test_mode_floor_applies(self):
        r = rg.classify_tier("do the analysis",
                             mode_text="## RISK TIER\nhigh-risk\n")
        self.assertEqual(r["risk_tier"], "high-risk")

    def test_sticky_raises_but_never_lowers_floor(self):
        # sticky light must not pull an irreversible floor down (condition 2)
        r = rg.classify_tier("deploy to production", sticky_floor="light")
        self.assertEqual(r["risk_tier"], "irreversible")
        # sticky high-risk raises an otherwise-standard turn
        r2 = rg.classify_tier("analyze the data", sticky_floor="high-risk")
        self.assertEqual(r2["risk_tier"], "high-risk")

    def test_explicit_override_may_lower(self):
        r = rg.classify_tier("deploy to production",
                             explicit_override="high-risk")
        self.assertEqual(r["risk_tier"], "high-risk")
        self.assertEqual(r["override"], "high-risk")

    def test_never_raises(self):
        with mock.patch.object(rg, "stage_a_floor", side_effect=ValueError("x")):
            r = rg.classify_tier("anything")
        self.assertEqual(r["risk_tier"], rg.FAILSAFE_TIER)
        self.assertIn("classify", r["error"])


class TestRiskPrefix(unittest.TestCase):
    def test_inline_override_extracted(self):
        cleaned, tier = rg.strip_risk_prefix("/risk high-risk deploy the site")
        self.assertEqual(cleaned, "deploy the site")
        self.assertEqual(tier, "high-risk")

    def test_bare_command_left_intact(self):
        cleaned, tier = rg.strip_risk_prefix("/risk standard")
        self.assertEqual(cleaned, "/risk standard")
        self.assertIsNone(tier)

    def test_unknown_tier_passes_as_text(self):
        cleaned, tier = rg.strip_risk_prefix("/risk bananas do the thing")
        self.assertEqual(cleaned, "/risk bananas do the thing")
        self.assertIsNone(tier)

    def test_non_risk_untouched(self):
        cleaned, tier = rg.strip_risk_prefix("explain /risk levels to me")
        self.assertEqual(cleaned, "explain /risk levels to me")
        self.assertIsNone(tier)

    def test_sticky_parse(self):
        self.assertEqual(rg.parse_sticky_risk("/risk standard"), "standard")
        self.assertEqual(rg.parse_sticky_risk("/risk auto"), "auto")
        self.assertIsNone(rg.parse_sticky_risk("/risk high-risk do it"))
        self.assertTrue(rg.is_risk_command("/risk light"))

    def test_sticky_confirmation_uses_dialogue_terminology(self):
        with mock.patch.object(rg, "set_sticky"):
            reply = rg.handle_risk_command("/risk standard", "dialogue-1")
        self.assertIn("for this Dialogue", reply)
        self.assertNotIn("for this conversation", reply)


class TestFingerprint(unittest.TestCase):
    def test_same_task_same_fp(self):
        a = rg.task_fingerprint(conversation_id="c1", prompt="Deploy the site")
        b = rg.task_fingerprint(conversation_id="c1", prompt="deploy the  site ")
        self.assertEqual(a, b)  # whitespace + case normalized

    def test_different_target_differs(self):
        a = rg.task_fingerprint(conversation_id="c1", prompt="save it",
                                output_target="file:/a.md")
        b = rg.task_fingerprint(conversation_id="c1", prompt="save it",
                                output_target="file:/b.md")
        self.assertNotEqual(a, b)

    def test_different_conversation_differs(self):
        a = rg.task_fingerprint(conversation_id="c1", prompt="x")
        b = rg.task_fingerprint(conversation_id="c2", prompt="x")
        self.assertNotEqual(a, b)

    def test_attachment_differs(self):
        a = rg.task_fingerprint(conversation_id="c1", prompt="x", attachments=["h1"])
        b = rg.task_fingerprint(conversation_id="c1", prompt="x", attachments=["h2"])
        self.assertNotEqual(a, b)

    def test_mode_and_surface_bind(self):
        a = rg.task_fingerprint(conversation_id="c1", prompt="x", mode_id="m1",
                                surface="chat")
        b = rg.task_fingerprint(conversation_id="c1", prompt="x", mode_id="m2",
                                surface="chat")
        self.assertNotEqual(a, b)


class TestTaskTokens(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._patch = mock.patch.object(
            te, "APPROVALS_PATH", os.path.join(self._tmp, "approvals.json"))
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def test_grant_check_consume_cycle(self):
        fp = rg.task_fingerprint(conversation_id="c1", prompt="deploy")
        self.assertFalse(rg.has_valid_task_token(fp))
        rg.grant_task_token(fp)
        self.assertTrue(rg.has_valid_task_token(fp))
        # consume is one-shot
        self.assertIsNotNone(rg.consume_task_token(fp))
        self.assertFalse(rg.has_valid_task_token(fp))
        self.assertIsNone(rg.consume_task_token(fp))

    def test_cross_conversation_isolation_via_fingerprint(self):
        # Different conversations produce different fingerprints, so a token
        # for one cannot admit the other (scoping is by fingerprint).
        fp_c1 = rg.task_fingerprint(conversation_id="c1", prompt="deploy")
        fp_c2 = rg.task_fingerprint(conversation_id="c2", prompt="deploy")
        self.assertNotEqual(fp_c1, fp_c2)
        rg.grant_task_token(fp_c1)
        self.assertTrue(rg.has_valid_task_token(fp_c1))
        self.assertFalse(rg.has_valid_task_token(fp_c2))

    def test_different_task_not_admitted(self):
        fp1 = rg.task_fingerprint(conversation_id="c1", prompt="deploy A")
        fp2 = rg.task_fingerprint(conversation_id="c1", prompt="deploy B")
        rg.grant_task_token(fp1)
        self.assertFalse(rg.has_valid_task_token(fp2))

    def test_double_grant_is_one_shot(self):
        # Adversarial fold: two approvals of the same task must not leave two
        # live tokens (which would admit the irreversible task twice).
        fp = rg.task_fingerprint(conversation_id="c1", prompt="deploy")
        rg.grant_task_token(fp)
        rg.grant_task_token(fp)
        self.assertIsNotNone(rg.consume_task_token(fp))
        self.assertIsNone(rg.consume_task_token(fp))  # only ONE live token

    def test_framework_style_approve_then_consume(self):
        # Adversarial fold: framework path mints via handle_task_gate_reply
        # (a real conversation) but consumes with conversation_id None — must
        # still admit (fingerprint-scoped, not token-conversation-scoped).
        fp = rg.task_fingerprint(conversation_id=None, prompt="send email",
                                 surface="framework")
        rg.handle_task_gate_reply({"fp": fp, "queue_id": None}, "1", "c9")
        self.assertIsNotNone(rg.consume_task_token(fp))


class TestEvaluateHoldFailClosed(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._patches = [
            mock.patch.object(te, "APPROVALS_PATH",
                              os.path.join(self._tmp, "a.json")),
            mock.patch.object(rg._rp, "DATA_DIR_STR", self._tmp),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def test_internal_error_holds_irreversible(self):
        # Adversarial fold (blocker): an I/O error in the token check must
        # NOT skip the hold — evaluate_hold fails CLOSED for irreversible.
        with mock.patch.object(rg, "consume_task_token",
                               side_effect=OSError("disk")), \
             mock.patch.object(rg, "write_task_gate_card", return_value=None):
            reply, fp = rg.evaluate_hold("irreversible", conversation_id="c1",
                                         prompt="deploy prod", surface="chat")
        self.assertIsNotNone(reply)  # held, not skipped
        self.assertIsNotNone(rg.read_task_gate_marker(reply))

    def test_non_irreversible_never_holds(self):
        reply, _ = rg.evaluate_hold("high-risk", conversation_id="c1",
                                    prompt="x", surface="chat")
        self.assertIsNone(reply)


class TestTierAliases(unittest.TestCase):
    def test_high_alias(self):
        _, tier = rg.strip_risk_prefix("/risk high deploy it")
        self.assertEqual(tier, "high-risk")
        self.assertEqual(rg.parse_sticky_risk("/risk high"), "high-risk")

    def test_other_aliases(self):
        _, t1 = rg.strip_risk_prefix("/risk irrev send email")
        self.assertEqual(t1, "irreversible")
        _, t2 = rg.strip_risk_prefix("/risk low chat")
        self.assertEqual(t2, "light")


class TestTaskGateCopy(unittest.TestCase):
    def test_approval_uses_dialogue_terminology(self):
        record = {"event": {"fingerprint": "fp", "conversation_id": "d1",
                            "principal_id": "principal:user"}}
        with mock.patch.object(rg, "grant_task_token"):
            reply = rg.resolve_task_gate_entry(record, approve=True)
        self.assertIn("origin Dialogue", reply)
        self.assertNotIn("origin conversation", reply)


class TestStageABroadened(unittest.TestCase):
    def test_realistic_irreversible_phrasings(self):
        for txt in ("ship it to prod",
                    "email the customers about the outage",
                    "cut a release",
                    "wire $500 to the vendor",
                    "go live with the new pricing",
                    "send this to the list"):
            floor, _ = rg.stage_a_floor(txt)
            self.assertEqual(floor, "irreversible", txt)


class TestRevision2Folds(unittest.TestCase):
    """Judge Revision-2 findings — folded and regression-guarded."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._patches = [
            mock.patch.object(te, "APPROVALS_PATH",
                              os.path.join(self._tmp, "a.json")),
            mock.patch.object(rg._rp, "DATA_DIR_STR", self._tmp),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def test_token_stores_conversation_for_purge(self):
        # P1: the token must store its granting conversation_id so the
        # stealth closeout purge can match it — while consumption stays
        # fingerprint-only.
        fp = rg.task_fingerprint(conversation_id="cS", prompt="deploy")
        rg.grant_task_token(fp, "cS")
        data = te._load_approvals()
        tok = [t for t in data["tokens"] if t["args_hash"] == fp][0]
        self.assertEqual(tok["conversation_id"], "cS")
        # consume ignores the stored conversation (fp-only)
        self.assertIsNotNone(rg.consume_task_token(fp))

    def test_framework_deliverable_resume_marker(self):
        # P1: approving a mid-elicitation deliverable hold must re-attach the
        # framework marker so the flow is not stranded.
        import framework_elicitation as fe
        fp = rg.task_fingerprint(conversation_id=None, prompt="send email",
                                 surface="framework")
        reply = rg.handle_task_gate_reply(
            {"fp": fp, "queue_id": None,
             "resume": {"fw": "corpus-formalization.md", "mode": "C-Design"}},
            "1", "c9")
        cont = fe.is_continuation([{"role": "assistant", "content": reply}])
        self.assertIsNotNone(cont)
        self.assertEqual(cont.mode, "C-Design")
        self.assertTrue(rg.has_valid_task_token(fp))

    def test_route_observed_turn_scoped(self):
        # P1: the global-sink fold must exclude events before this turn.
        import json as _j
        p = os.path.join(self._tmp, "sink.jsonl")
        with open(p, "w") as f:
            f.write(_j.dumps({"conversation_id": "cR",
                              "ts": "2020-01-01T00:00:00+00:00",
                              "mutability": "irreversible", "mutated": True}) + "\n")
        turn_ts = rg.now_ts()
        s = rg.fold_route_observed(p, conversation_id="cR", turn_ts=turn_ts)
        self.assertFalse(s["any_mutation"])
        self.assertEqual(s["events_scanned"], 0)

    def test_framework_deliverable_token_survives_summarizer_drift(self):
        # Revision-2 adversarial blocker: the framework-deliverable token is
        # fingerprinted by the STABLE framework+mode identity, so an approved
        # deliverable still admits on the continue-turn even though the
        # summarizer reworded/reordered the bullets (different deliverable
        # text). Mirrors _produce_deliverable's _stable_id.
        def stable_fp():
            return rg.task_fingerprint(
                conversation_id=None, prompt="framework-deliverable::cff.md::O-Render",
                surface="framework", mode_id="cff.md/O-Render")
        # hold-turn computes fp, approval mints it…
        fp_hold = stable_fp()
        rg.grant_task_token(fp_hold)
        # continue-turn recomputes the fp from the SAME stable id (bullets
        # drifted, but they don't enter the fingerprint) and consumes it.
        reply, fp_resume = rg.evaluate_hold(
            "irreversible", conversation_id=None,
            prompt="framework-deliverable::cff.md::O-Render", surface="framework",
            mode_id="cff.md/O-Render")
        self.assertIsNone(reply)  # admitted, not re-held
        self.assertEqual(fp_hold, fp_resume)

    def test_framework_token_conversation_isolated(self):
        # Rev-3 finding 1: the framework-deliverable fingerprint binds the
        # conversation, so an approval in one conversation cannot admit the
        # same framework/mode deliverable in another.
        fp_a = rg.task_fingerprint(
            conversation_id="convA", prompt="framework-deliverable::demo::all",
            surface="framework", mode_id="demo/all")
        fp_b = rg.task_fingerprint(
            conversation_id="convB", prompt="framework-deliverable::demo::all",
            surface="framework", mode_id="demo/all")
        self.assertNotEqual(fp_a, fp_b)
        rg.grant_task_token(fp_a, "convA")
        self.assertTrue(rg.has_valid_task_token(fp_a))
        self.assertFalse(rg.has_valid_task_token(fp_b))

    def test_framework_hold_carries_both_markers(self):
        # Rev-3 finding 2: a framework-deliverable hold reply carries BOTH the
        # task-gate marker AND the ora-framework marker (siblings, not nested)
        # so a sidebar/slash approval + single "continue" re-enters delivery.
        import framework_elicitation as fe
        reply = rg.build_task_gate_prompt(
            "irreversible", "fpX", "q1",
            resume={"fw": "corpus-formalization.md", "mode": "C-Design"})
        self.assertIsNotNone(rg.read_task_gate_marker(reply))       # task-gate
        self.assertIsNotNone(fe.is_continuation(                    # framework
            [{"role": "assistant", "content": reply}]))
        self.assertEqual(reply.count("<!--"), 2)  # two sibling comments

    def test_sidebar_approval_then_continue_falls_through(self):
        # Rev-3 finding 2: after a queue/sidebar approval mints the token, the
        # origin "continue" is NOT handled by the task-gate reply (returns
        # None) so it falls through to is_continuation, which re-enters.
        marker_ctx = {"fp": "fpX", "queue_id": "q1",
                      "resume": {"fw": "cff.md", "mode": "O-Render"}}
        rg.grant_task_token("fpX", "convO")  # sidebar-minted
        self.assertIsNone(rg.handle_task_gate_reply(marker_ctx, "continue", "convO"))

    def test_card_persists_resume(self):
        # Rev-3 finding 2: the queue card event carries the resume payload.
        captured = {}

        def _fake_add(rec, config=None):
            captured.update(rec)
            from types import SimpleNamespace
            return SimpleNamespace(id="q9")
        import oversight_queue
        with mock.patch.object(oversight_queue, "add_entry", _fake_add):
            rg.write_task_gate_card("irreversible", "fp1", "c1", "framework",
                                    "desc", resume={"fw": "x.md", "mode": "M"})
        self.assertEqual(captured["event"]["resume"], {"fw": "x.md", "mode": "M"})

    def test_hold_message_skipped_from_summarizer_input(self):
        # Rev-3 adversarial fold: a risk-gate hold reply (task-gate marker +
        # approve/cancel prose) is scaffolding, not elicited facts — it must
        # be skipped wholesale from the elicitation summarizer's input.
        import framework_elicitation as fe
        hold = rg.build_task_gate_prompt(
            "irreversible", "fpX", "q1", resume={"fw": "cff.md", "mode": "O-Render"})
        hist = [{"role": "user", "content": "produce the deliverable"},
                {"role": "assistant", "content": hold},
                {"role": "user", "content": "continue"}]
        formatted = fe._format_conversation(hist, "continue")
        self.assertNotIn("ora-task-gate", formatted)
        self.assertNotIn("approve and proceed", formatted)

    def test_route_fold_matches_seeded_conversation(self):
        # Rev-3 adversarial fold: the framework paths seed the turn context so
        # their tool events carry the conversation_id; the fold then matches.
        import json as _j
        p = os.path.join(self._tmp, "sink.jsonl")
        with open(p, "w") as f:
            f.write(_j.dumps({"conversation_id": "main",
                              "ts": "2099-01-01T00:00:00+00:00",
                              "mutability": "irreversible", "mutated": True}) + "\n")
        s = rg.fold_route_observed(p, conversation_id="main",
                                   turn_ts="2000-01-01T00:00:00+00:00")
        self.assertTrue(s["any_mutation"])
        self.assertEqual(s["events_scanned"], 1)

    def test_hold_nonce_prevents_same_conversation_cross_task_reuse(self):
        # Rev-4 finding: a per-hold nonce makes each held deliverable a
        # distinct token, so a materially different later deliverable in the
        # SAME conversation/framework/mode cannot reuse an earlier approval.
        fp_a = rg.task_fingerprint(
            conversation_id="convA", surface="framework", mode_id="demo/all",
            prompt="framework-deliverable::demo::all::NONCE_A")
        fp_b = rg.task_fingerprint(
            conversation_id="convA", surface="framework", mode_id="demo/all",
            prompt="framework-deliverable::demo::all::NONCE_B")
        self.assertNotEqual(fp_a, fp_b)
        rg.grant_task_token(fp_a, "convA")          # approved deliverable A
        self.assertTrue(rg.has_valid_task_token(fp_a))
        self.assertFalse(rg.has_valid_task_token(fp_b))  # B can't reuse

    def test_content_nonce_reorder_stable_material_distinct(self):
        # Rev-4: the framework nonce is a hash of the normalized WORD MULTISET
        # of the whole deliverable text (mirrors _produce_deliverable).
        # Bullet/word reordering → identical nonce (approved deliverable still
        # produces on resume); materially different words → distinct nonce
        # (holds — cannot reuse an earlier live approval, even a pivot).
        import hashlib as _hl
        import re as _re

        def dnonce(text):
            return _hl.sha1(" ".join(sorted(
                _re.findall(r"\w+", (text or "").lower()))).encode(
                "utf-8", "replace")).hexdigest()[:12]

        a = "o-render Produce...\n- workflow: invoice\n- source: ERP export"
        a_reordered = "o-render Produce...\n- source: ERP EXPORT\n- workflow: invoice"
        b_material = "o-render Produce...\n- publish to all subscribers"
        self.assertEqual(dnonce(a), dnonce(a_reordered))     # drift → same
        self.assertNotEqual(dnonce(a), dnonce(b_material))   # pivot → distinct
        # empty-fact deliverable is not a constant nonce (carries mode words)
        self.assertNotEqual(dnonce("o-render Produce... (no facts)"),
                            _hl.sha1(b"").hexdigest()[:12])
        # distinct nonce → distinct fingerprint → B can't reuse A's token
        fp_a = rg.task_fingerprint(
            conversation_id="c1", surface="framework", mode_id="demo/all",
            prompt=f"framework-deliverable::demo::all::{dnonce(a)}")
        fp_b = rg.task_fingerprint(
            conversation_id="c1", surface="framework", mode_id="demo/all",
            prompt=f"framework-deliverable::demo::all::{dnonce(b_material)}")
        rg.grant_task_token(fp_a, "c1")
        self.assertFalse(rg.has_valid_task_token(fp_b))  # pivot-to-B holds

    def test_resume_marker_has_no_nested_comment(self):
        # The resume payload must be DATA, never an embedded HTML-comment
        # marker (a nested '-->' would break the outer ora-task-gate comment).
        reply = rg.build_task_gate_prompt(
            "irreversible", "fp1", "q1",
            resume={"fw": "x.md", "mode": "M"})
        # the outer marker still parses cleanly
        self.assertIsNotNone(rg.read_task_gate_marker(reply))
        self.assertEqual(reply.count("ora-task-gate"), 1)


class TestTaskGateMarker(unittest.TestCase):
    def test_roundtrip(self):
        reply = rg.build_task_gate_prompt("irreversible", "fp123", "q9")
        self.assertIn("irreversible", reply)
        payload = rg.read_task_gate_marker(reply)
        self.assertEqual(payload["fp"], "fp123")
        self.assertEqual(payload["queue_id"], "q9")

    def test_continuation_scan(self):
        hist = [{"role": "user", "content": "deploy"},
                {"role": "assistant", "content": rg.build_task_gate_prompt(
                    "irreversible", "fpX", None)}]
        ctx = rg.is_task_gate_continuation(hist)
        self.assertEqual(ctx["fp"], "fpX")

    def test_no_marker_returns_none(self):
        hist = [{"role": "assistant", "content": "normal reply"}]
        self.assertIsNone(rg.is_task_gate_continuation(hist))


class TestShouldHold(unittest.TestCase):
    def test_holds_irreversible_without_token(self):
        self.assertTrue(rg.should_hold("irreversible", has_token=False))
        self.assertFalse(rg.should_hold("irreversible", has_token=True))
        self.assertFalse(rg.should_hold("high-risk", has_token=False))
        self.assertFalse(rg.should_hold("standard", has_token=False))


class TestRouteObserved(unittest.TestCase):
    def _write_events(self, path, events):
        with open(path, "w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")

    def test_fold_trace_file(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "tool-events.jsonl")
        self._write_events(p, [
            {"mutability": "reversible_write", "mutated": True,
             "sensitivity": "private", "egress": "none",
             "gate": {"decision": "allowed"}},
            {"mutability": "read", "reads": [{"what": "x"}],
             "sensitivity": "public", "egress": "local"},
        ])
        s = rg.fold_route_observed(p)
        self.assertTrue(s["any_mutation"])
        self.assertEqual(s["max_mutability"], "reversible_write")
        self.assertTrue(s["reads_present"])
        self.assertEqual(s["max_egress"], "local")
        self.assertEqual(s["gate_outcomes"], {"allowed": 1})

    def test_global_sink_scoped_by_conversation(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "sink.jsonl")
        self._write_events(p, [
            {"conversation_id": "c1", "ts": "2026-07-03T10:00:00Z",
             "mutability": "irreversible", "mutated": True},
            {"conversation_id": "c2", "ts": "2026-07-03T10:00:00Z",
             "mutability": "read"},
        ])
        s = rg.fold_route_observed(p, conversation_id="c1")
        self.assertEqual(s["max_mutability"], "irreversible")
        self.assertEqual(s["events_scanned"], 1)  # c2 excluded

    def test_missing_path_safe(self):
        s = rg.fold_route_observed("/nonexistent/x.jsonl")
        self.assertFalse(s["any_mutation"])

    def test_record_divergence_for_light_mutation(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "tool-events.jsonl")
        self._write_events(p, [{"mutability": "external_write", "mutated": True}])
        with mock.patch.object(te, "record") as m_rec:
            out = rg.record_route_observed(d, risk_tier="light")
        self.assertIsNotNone(out["divergence"])
        self.assertTrue(m_rec.called)

    def test_record_never_raises(self):
        # bad turn_key type → still returns a dict
        out = rg.record_route_observed(object())
        self.assertIn("signals", out)


class TestSourceReadSignal(unittest.TestCase):
    """Execution Review Phase 3 — the §6 signal-2 source-read
    over-approximation folded from the tool-event log (judge conditions 1+2)."""

    def _write(self, events):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "tool-events.jsonl")
        with open(p, "w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
        return p

    @staticmethod
    def _read_ev(action, *, sensitivity="private", reads=None, ok=True,
                 decision="allowed", mutability="read"):
        ev = {"action": action, "mutability": mutability,
              "sensitivity": sensitivity,
              "exit": {"ok": ok}, "gate": {"decision": decision}}
        if reads is not None:
            ev["reads"] = reads
        return ev

    _SUBSTANTIVE = "This is a substantive grounded answer well over the floor."
    _TRIVIAL = "ok"

    # ── the core over-approximation ─────────────────────────────────────────
    def test_strong_channel_substantive_output_suspected(self):
        p = self._write([self._read_ev(
            "web_fetch", sensitivity="public",
            reads=[{"what": "https://x.example/a", "where": "network",
                    "content_hash": "abc123"}])])
        s = rg.fold_route_observed(p, output_text=self._SUBSTANTIVE)
        self.assertTrue(s["source_read_suspected"])
        self.assertEqual(s["source_read_channels"], ["web_fetch"])

    def test_ambiguous_local_substantive_suspected(self):
        # Q1=A: over-approximate local reads to source.
        p = self._write([self._read_ev(
            "file_read", reads=[{"what": "/w/note.md", "where": "local",
                                 "content_hash": "d00d"}])])
        s = rg.fold_route_observed(p, output_text=self._SUBSTANTIVE)
        self.assertTrue(s["source_read_suspected"])

    def test_ambiguous_local_trivial_output_not_suspected(self):
        # An ambiguous local read whose output is a trivial ack (read-to-edit)
        # does NOT suspect — the substantive floor applies to local-only turns.
        p = self._write([self._read_ev(
            "file_read", reads=[{"what": "/w/x", "where": "local"}])])
        s = rg.fold_route_observed(p, output_text=self._TRIVIAL)
        self.assertFalse(s["source_read_suspected"])

    def test_strong_channel_short_output_suspected(self):
        # §6 asymmetry: a strong channel + a terse grounded answer must NOT be
        # under-routed by the length floor (finding [4]).
        p = self._write([self._read_ev(
            "web_fetch", sensitivity="public",
            reads=[{"what": "https://x", "where": "network"}])])
        s = rg.fold_route_observed(p, output_text="4.1%")
        self.assertTrue(s["source_read_suspected"])

    def test_strong_channel_empty_output_not_suspected(self):
        p = self._write([self._read_ev(
            "web_fetch", sensitivity="public",
            reads=[{"what": "https://x", "where": "network"}])])
        s = rg.fold_route_observed(p, output_text="   ")
        self.assertFalse(s["source_read_suspected"])

    def test_mcp_read_counts_as_source(self):
        # Finding [0]/[3]: an instrumented read-only MCP call is opaque external
        # source contact and must trip signal 2 (event=='mcp' + mutability read).
        p = self._write([{"event": "mcp", "action": "mcp_docs_search",
                          "mutability": "read", "sensitivity": "private",
                          "exit": {"ok": True}, "gate": {"decision": "allowed"}}])
        s = rg.fold_route_observed(p, output_text=self._SUBSTANTIVE)
        self.assertTrue(s["source_read_suspected"])
        self.assertIn("mcp_docs_search", s["source_read_channels"])

    def test_mcp_read_short_output_suspected(self):
        # Judge code-review condition: MCP is a STRONG channel, so a terse
        # grounded answer after a successful MCP read must still suspect (not be
        # dropped by the 24-char substantive floor).
        p = self._write([{"event": "mcp", "action": "mcp_db_query",
                          "mutability": "read", "sensitivity": "private",
                          "exit": {"ok": True}, "gate": {"decision": "allowed"}}])
        s = rg.fold_route_observed(p, output_text="Yes.")
        self.assertTrue(s["source_read_suspected"])

    def test_mcp_read_empty_output_not_suspected(self):
        # Strong-channel semantics: an empty output still does not suspect.
        p = self._write([{"event": "mcp", "action": "mcp_db_query",
                          "mutability": "read", "sensitivity": "private",
                          "exit": {"ok": True}, "gate": {"decision": "allowed"}}])
        s = rg.fold_route_observed(p, output_text="   ")
        self.assertFalse(s["source_read_suspected"])

    def test_mcp_write_not_source(self):
        p = self._write([{"event": "mcp", "action": "mcp_github_create_issue",
                          "mutability": "external_write", "mutated": True,
                          "sensitivity": "private", "exit": {"ok": True},
                          "gate": {"decision": "allowed"}}])
        s = rg.fold_route_observed(p, output_text=self._SUBSTANTIVE)
        self.assertFalse(s["source_read_suspected"])

    def test_rag_read_substantive_suspected(self):
        # Judge Q3: rag_read trips signal 2 on substantive RAG-grounded output.
        p = self._write([self._read_ev(
            "rag_read", reads=[{"what": "chromadb:knowledge", "where": "local",
                                "chars": 900}])])
        s = rg.fold_route_observed(p, output_text=self._SUBSTANTIVE)
        self.assertTrue(s["source_read_suspected"])
        self.assertIn("rag_read", s["source_read_channels"])

    def test_no_source_read_not_suspected(self):
        # A pure mutation turn (file_write) with substantive output.
        p = self._write([{"action": "file_write", "mutability": "reversible_write",
                          "mutated": True, "sensitivity": "private",
                          "exit": {"ok": True}, "gate": {"decision": "allowed"}}])
        s = rg.fold_route_observed(p, output_text=self._SUBSTANTIVE)
        self.assertFalse(s["source_read_suspected"])
        self.assertEqual(s["source_candidate_reads"], [])

    # ── output-unavailable fallback ─────────────────────────────────────────
    def test_output_none_strong_channel_suspected(self):
        p = self._write([self._read_ev(
            "knowledge_search",
            reads=[{"what": "chromadb:knowledge:q", "where": "local"}])])
        s = rg.fold_route_observed(p, output_text=None)
        self.assertTrue(s["source_read_suspected"])  # strong → over-route

    def test_output_none_ambiguous_only_not_suspected(self):
        p = self._write([self._read_ev(
            "file_read", reads=[{"what": "/w/x", "where": "local"}])])
        s = rg.fold_route_observed(p, output_text=None)
        self.assertFalse(s["source_read_suspected"])

    # ── judge condition 1: actually-ran + allowlist ─────────────────────────
    def test_blocked_read_is_not_a_source_read(self):
        p = self._write([self._read_ev(
            "web_fetch", sensitivity="public", decision="blocked",
            reads=[{"what": "https://x", "where": "network"}])])
        s = rg.fold_route_observed(p, output_text=self._SUBSTANTIVE)
        self.assertFalse(s["source_read_suspected"])
        self.assertEqual(s["source_read_channels"], [])

    def test_queued_read_is_not_a_source_read(self):
        p = self._write([self._read_ev(
            "web_fetch", sensitivity="public", decision="queued",
            reads=[{"what": "https://x", "where": "network"}])])
        s = rg.fold_route_observed(p, output_text=self._SUBSTANTIVE)
        self.assertFalse(s["source_read_suspected"])

    def test_failed_read_exit_not_ok_excluded(self):
        p = self._write([self._read_ev(
            "web_fetch", sensitivity="public", ok=False,
            reads=[{"what": "https://x", "where": "network"}])])
        s = rg.fold_route_observed(p, output_text=self._SUBSTANTIVE)
        self.assertFalse(s["source_read_suspected"])

    def test_telemetry_actions_excluded(self):
        # task_tier / acceptance_criteria / route_observed carry mutability
        # read but must never count as source reads.
        for action in ("task_tier", "acceptance_criteria", "route_observed"):
            p = self._write([{"action": action, "mutability": "read",
                              "sensitivity": "public", "exit": {"ok": True},
                              "gate": {"decision": "allowed"}}])
            s = rg.fold_route_observed(p, output_text=self._SUBSTANTIVE)
            self.assertFalse(s["source_read_suspected"], action)

    def test_shell_read_counts_as_ambiguous(self):
        p = self._write([{"action": "bash:read", "mutability": "read",
                          "sensitivity": "private", "exit": {"ok": True},
                          "gate": {"decision": "allowed"}}])
        s = rg.fold_route_observed(p, output_text=self._SUBSTANTIVE)
        self.assertTrue(s["source_read_suspected"])
        self.assertIn("bash:read", s["source_read_channels"])

    # ── judge condition 2: public-safe candidate shape ──────────────────────
    def test_public_read_keeps_what(self):
        p = self._write([self._read_ev(
            "web_fetch", sensitivity="public",
            reads=[{"what": "https://x.example/a", "where": "network",
                    "content_hash": "abc123"}])])
        s = rg.fold_route_observed(p, output_text=self._SUBSTANTIVE)
        cand = s["source_candidate_reads"][0]
        self.assertEqual(cand["what"], "https://x.example/a")
        self.assertEqual(cand["content_hash"], "abc123")
        self.assertEqual(cand["action"], "web_fetch")

    def test_private_read_drops_what(self):
        p = self._write([self._read_ev(
            "file_read", sensitivity="private",
            reads=[{"what": "/w/secret_plan.md", "where": "local",
                    "content_hash": "d00d"}])])
        s = rg.fold_route_observed(p, output_text=self._SUBSTANTIVE)
        cand = s["source_candidate_reads"][0]
        self.assertNotIn("what", cand)          # path never rides into summary
        self.assertEqual(cand["content_hash"], "d00d")  # hash is safe
        self.assertEqual(cand["where"], "local")

    def test_sensitive_read_drops_what(self):
        p = self._write([self._read_ev(
            "file_read", sensitivity="sensitive",
            reads=[{"what": "[SENSITIVE PATH]", "where": "local"}])])
        s = rg.fold_route_observed(p, output_text=self._SUBSTANTIVE)
        cand = s["source_candidate_reads"][0]
        self.assertNotIn("what", cand)

    def test_fold_max_sensitivity_reflects_read(self):
        # Condition 2 basis: the fold's max_sensitivity rises with a sensitive
        # read, and record_route_observed stamps that onto the event (below).
        p = self._write([self._read_ev(
            "file_read", sensitivity="sensitive",
            reads=[{"what": "[SENSITIVE PATH]", "where": "local"}])])
        s = rg.fold_route_observed(p, output_text=self._SUBSTANTIVE)
        self.assertEqual(s["max_sensitivity"], "sensitive")

    def test_record_route_observed_stamps_folded_sensitivity(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "tool-events.jsonl")
        with open(p, "w") as f:
            f.write(json.dumps(self._read_ev(
                "file_read", sensitivity="sensitive",
                reads=[{"what": "[SENSITIVE PATH]", "where": "local"}])) + "\n")
        with mock.patch.object(te, "record") as m_rec:
            rg.record_route_observed(d, risk_tier="standard",
                                     output_text=self._SUBSTANTIVE)
        self.assertTrue(m_rec.called)
        rec = m_rec.call_args[0][0]
        self.assertEqual(rec["sensitivity"], "sensitive")  # not hardcoded public
        # nested payload is public-safe regardless.
        for cand in rec["route_signals"]["source_candidate_reads"]:
            self.assertNotIn("what", cand)

    def test_secret_fold_caps_event_at_sensitive(self):
        # Finding [1]: a secret event in the window must NOT stamp the
        # route_observed record 'secret' (that would half-apply the
        # existence-only contract to a persisting public-safe payload) — cap at
        # 'sensitive'.
        d = tempfile.mkdtemp()
        p = os.path.join(d, "tool-events.jsonl")
        with open(p, "w") as f:
            # a secret op in the same window (e.g. credential_store) + a real
            # web read that grounds the output.
            f.write(json.dumps({"action": "credential_store",
                                "mutability": "reversible_write",
                                "sensitivity": "secret", "exit": {"ok": True},
                                "gate": {"decision": "allowed"}}) + "\n")
            f.write(json.dumps(self._read_ev(
                "web_fetch", sensitivity="public",
                reads=[{"what": "https://x", "where": "network"}])) + "\n")
        with mock.patch.object(te, "record") as m_rec:
            rg.record_route_observed(d, risk_tier="standard",
                                     output_text=self._SUBSTANTIVE)
        rec = m_rec.call_args[0][0]
        self.assertEqual(rec["route_signals"]["max_sensitivity"], "secret")
        self.assertEqual(rec["sensitivity"], "sensitive")  # capped, not secret

    def test_record_promotes_suspected_to_top_level(self):
        # Finding [5]: the routing verdict rides at top level (and the
        # truncation keep-set) so it survives a byte-truncated record.
        d = tempfile.mkdtemp()
        p = os.path.join(d, "tool-events.jsonl")
        with open(p, "w") as f:
            f.write(json.dumps(self._read_ev(
                "web_fetch", sensitivity="public",
                reads=[{"what": "https://x", "where": "network"}])) + "\n")
        with mock.patch.object(te, "record") as m_rec:
            rg.record_route_observed(d, risk_tier="standard",
                                     output_text=self._SUBSTANTIVE)
        rec = m_rec.call_args[0][0]
        self.assertTrue(rec["source_read_suspected"])  # top-level, not only nested
        self.assertTrue(rec["route_signals"]["source_read_suspected"])

    # ── additive shape / never-raises ───────────────────────────────────────
    def test_additive_shape_preserves_phase2_keys(self):
        p = self._write([self._read_ev(
            "web_fetch", sensitivity="public",
            reads=[{"what": "https://x", "where": "network"}])])
        s = rg.fold_route_observed(p, output_text=self._SUBSTANTIVE)
        for k in ("any_mutation", "max_mutability", "reads_present",
                  "max_sensitivity", "max_egress", "gate_outcomes",
                  "events_scanned", "source_read_suspected",
                  "source_read_channels", "source_candidate_reads",
                  "source_candidate_reads_truncated"):
            self.assertIn(k, s)
        self.assertTrue(s["reads_present"])  # Phase-2 boolean still fires

    def test_candidates_capped_and_flagged(self):
        # A very heavy turn's candidate list is bounded + flagged so the whole
        # route_signals block can't be truncated away past MAX_LINE_BYTES; the
        # routing boolean is unaffected by the cap.
        many = [self._read_ev(
            "web_fetch", sensitivity="public",
            reads=[{"what": f"https://x/{i}", "where": "network",
                    "content_hash": f"h{i}"}])
            for i in range(rg._MAX_SOURCE_CANDIDATES + 20)]
        p = self._write(many)
        s = rg.fold_route_observed(p, output_text=self._SUBSTANTIVE)
        self.assertTrue(s["source_read_suspected"])           # signal intact
        self.assertTrue(s["source_candidate_reads_truncated"])  # flagged, not silent
        self.assertEqual(len(s["source_candidate_reads"]),
                         rg._MAX_SOURCE_CANDIDATES)

    def test_output_text_default_none_back_compat(self):
        # Existing positional callers (no output_text) still work.
        p = self._write([self._read_ev(
            "web_fetch", sensitivity="public",
            reads=[{"what": "https://x", "where": "network"}])])
        s = rg.fold_route_observed(p)  # no output_text
        self.assertTrue(s["source_read_suspected"])  # strong-channel fallback


class TestSticky(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._patch = mock.patch.object(rg._rp, "DATA_DIR_STR", self._tmp)
        self._sticky_patch = mock.patch.object(
            rg, "_sticky_path", lambda: os.path.join(
                self._tmp, "risk-sticky.json",
            ),
        )
        self._patch.start()
        self._sticky_patch.start()

    def tearDown(self):
        self._sticky_patch.stop()
        self._patch.stop()

    def test_set_get_clear(self):
        self.assertIsNone(rg.get_sticky("c1"))
        rg.set_sticky("c1", "high-risk")
        self.assertEqual(rg.get_sticky("c1"), "high-risk")
        rg.set_sticky("c1", "auto")
        self.assertIsNone(rg.get_sticky("c1"))

    def test_set_replaces_store_symlink_without_reading_or_writing_target(self):
        sticky = rg._sticky_path()
        os.makedirs(os.path.dirname(sticky), exist_ok=True)
        outside = os.path.join(os.path.dirname(sticky), "outside.json")
        with open(outside, "w", encoding="utf-8") as stream:
            json.dump({"foreign": "irreversible"}, stream)
        os.symlink(outside, sticky)

        rg.set_sticky("c1", "standard")

        with open(outside, encoding="utf-8") as stream:
            self.assertEqual(json.load(stream), {"foreign": "irreversible"})
        self.assertFalse(os.path.islink(sticky))
        self.assertEqual(rg.get_sticky("c1"), "standard")
        self.assertIsNone(rg.get_sticky("foreign"))

    def test_set_ignores_predictable_legacy_temp_symlink(self):
        sticky = rg._sticky_path()
        os.makedirs(os.path.dirname(sticky), exist_ok=True)
        outside = os.path.join(os.path.dirname(sticky), "outside.tmp")
        with open(outside, "w", encoding="utf-8") as stream:
            stream.write("sentinel")
        os.symlink(outside, sticky + ".tmp")

        rg.set_sticky("c1", "high-risk")

        with open(outside, encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "sentinel")
        self.assertEqual(rg.get_sticky("c1"), "high-risk")

    def test_handle_bare_command(self):
        msg = rg.handle_risk_command("/risk standard", "c1")
        self.assertIsNotNone(msg)
        self.assertEqual(rg.get_sticky("c1"), "standard")
        clear = rg.handle_risk_command("/risk auto", "c1")
        self.assertIn("cleared", clear)
        self.assertIsNone(rg.get_sticky("c1"))

    def test_handle_returns_none_for_non_command(self):
        self.assertIsNone(rg.handle_risk_command("/risk high-risk deploy", "c1"))
        self.assertIsNone(rg.handle_risk_command("hello", "c1"))

    def test_assign_merges_sticky_but_floor_wins(self):
        rg.set_sticky("c1", "light")
        with mock.patch.object(rg._te, "record"):
            r = rg.assign_tier("deploy to production", "c1", record=False)
        self.assertEqual(r["risk_tier"], "irreversible")  # sticky light can't lower


class TestAssignAndResolve(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._p1 = mock.patch.object(rg._rp, "DATA_DIR_STR", self._tmp)
        self._p2 = mock.patch.object(
            te, "APPROVALS_PATH", os.path.join(self._tmp, "approvals.json"))
        self._p3 = mock.patch.object(
            rg, "_sticky_path", lambda: os.path.join(
                self._tmp, "risk-sticky.json",
            ),
        )
        self._p1.start(); self._p2.start(); self._p3.start()

    def tearDown(self):
        self._p3.stop(); self._p2.stop(); self._p1.stop()

    def test_assign_records_task_tier(self):
        with mock.patch.object(rg._te, "record") as m_rec:
            r = rg.assign_tier("analyze this", "c1", record=True)
        self.assertEqual(r["risk_tier"], "standard")
        self.assertTrue(m_rec.called)
        self.assertEqual(m_rec.call_args[0][0]["event"], "task_tier")

    def test_resolve_approve_mints_token(self):
        fp = rg.task_fingerprint(conversation_id="c1", prompt="deploy")
        rec = {"kind": "task_gate",
               "event": {"fingerprint": fp, "conversation_id": "c1",
                         "principal_id": "principal:user"}}
        msg = rg.resolve_task_gate_entry(rec, approve=True)
        self.assertIn("approved", msg.lower())
        self.assertTrue(rg.has_valid_task_token(fp, "c1"))

    def test_resolve_deny_records_no_token(self):
        fp = rg.task_fingerprint(conversation_id="c1", prompt="deploy")
        rec = {"kind": "task_gate",
               "event": {"fingerprint": fp, "conversation_id": "c1",
                         "principal_id": "principal:user"}}
        with mock.patch.object(rg._te, "record"):
            msg = rg.resolve_task_gate_entry(rec, approve=False, reason="nope")
        self.assertIn("denied", msg.lower())
        self.assertFalse(rg.has_valid_task_token(fp, "c1"))


if __name__ == "__main__":
    unittest.main()
