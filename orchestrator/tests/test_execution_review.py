"""Execution Review Phase 8 Chunk D — record_program_run (the programmatic record).

Covers the judge conditions + the Rev-3 folds:
  * signals FOLDED from the run's OWN per-run event log (NOT caller args) — §16-3;
  * an empty log → no-signals + `instrumentation: none`, AND the trace-local packet
    is STILL written (judge P2 — persist_packet then write_packet);
  * `enforcement_model` caller-mandatory (missing/invalid → refuse, no packet);
  * caller free-text → `producer_claim.known_limitations` (unverified);
  * `standing:true` declared-lane routing → deploy_probe lane attached + filled
    (via evidence_contract['lanes'] → route_lanes → fill_declared_lanes, judge P3),
    and a `standing:false` recipe does NOT route;
  * stealth no-op;
  * the set_turn_context/reset_turn_context per-run-context primitive (judge P2).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
import live_guard  # noqa: E402,F401 — quarantines durable oversight/telemetry writes

import tool_events as te                       # noqa: E402
import execution_review as erv                 # noqa: E402
import execution_packet as ep                  # noqa: E402
import evidence_runner as er                   # noqa: E402


def _write_events(trace_dir, events):
    with open(os.path.join(trace_dir, "tool-events.jsonl"), "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


def _read_packet(trace_dir):
    p = os.path.join(trace_dir, "execution-packet.json")
    if not os.path.exists(p):
        return None
    return json.loads(Path(p).read_text())


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.trace = os.path.join(self.tmp.name, "run-1")
        os.makedirs(self.trace)
        self._prev_events = os.environ.pop("ORA_TOOL_EVENTS", None)  # enable recording

    def tearDown(self):
        te.set_turn_context()
        if self._prev_events is not None:
            os.environ["ORA_TOOL_EVENTS"] = self._prev_events
        self.tmp.cleanup()


class TestFoldFromOwnLog(_Base):
    def test_signals_folded_from_log_not_caller(self):
        # A mutation event in the run's own sink → the packet observes any_mutation,
        # even though the caller passes no signal booleans (§16-3).
        _write_events(self.trace, [
            {"event": "file_write", "action": "file_edit", "mutated": True,
             "mutability": "reversible_write", "sensitivity": "private",
             "egress": "none"},
        ])
        out = erv.record_program_run(
            trace_dir=self.trace, output_text="the shipped prose",
            enforcement_model="boundary_only", risk_tier="standard")
        self.assertIsNotNone(out)
        pkt = _read_packet(self.trace)
        self.assertTrue(pkt["observed"]["any_mutation"])
        self.assertEqual(pkt["execution"]["enforcement_model"], "boundary_only")
        self.assertEqual(pkt["execution"]["instrumentation"], "observed")

    def test_empty_log_instrumentation_none_but_packet_written(self):
        # judge P2: an empty log → no signals + instrumentation:none, but the
        # trace-local execution-packet.json IS still written (git_only run).
        out = erv.record_program_run(
            trace_dir=self.trace, output_text="prose",
            enforcement_model="boundary_only")
        self.assertIsNotNone(out)
        pkt = _read_packet(self.trace)
        self.assertIsNotNone(pkt, "trace-local packet must be written")
        self.assertEqual(pkt["execution"]["instrumentation"], "none")
        self.assertFalse(pkt["observed"]["any_mutation"])


class TestEnforcementModelMandatory(_Base):
    def test_invalid_enforcement_refuses(self):
        out = erv.record_program_run(
            trace_dir=self.trace, output_text="p", enforcement_model="in-harness")  # bad
        self.assertIsNone(out)
        self.assertIsNone(_read_packet(self.trace))  # no packet on refusal

    def test_missing_enforcement_refuses_without_raising(self):
        # Omitting enforcement_model must REFUSE CLEANLY (mark + return None), never
        # raise — record_program_run owes its callers a "Never raises" contract, so a
        # required kwarg (TypeError at call binding) would break it. Both the omitted
        # and the explicit-None call take the same refusal path.
        marks: list = []
        with mock.patch.object(erv, "_mark_failure",
                               side_effect=lambda e, w: marks.append(w)):
            out_omitted = erv.record_program_run(
                trace_dir=self.trace, output_text="p")            # no kwarg at all
            out_none = erv.record_program_run(
                trace_dir=self.trace, output_text="p", enforcement_model=None)
        self.assertIsNone(out_omitted)
        self.assertIsNone(out_none)
        self.assertIsNone(_read_packet(self.trace))               # no packet on refusal
        self.assertIn("enforcement_model", marks)                 # failure observably marked


class TestProducerClaim(_Base):
    def test_caller_freetext_lands_in_known_limitations(self):
        erv.record_program_run(
            trace_dir=self.trace, output_text="the article prose",
            enforcement_model="boundary_only",
            producer_claim="dispatch: openrouter-forced monkey-patch")
        pkt = _read_packet(self.trace)
        pc = pkt["execution"]["producer_claim"]
        self.assertEqual(pc["summary"][:11], "the article")   # shipped prose
        self.assertIn("openrouter-forced", pc["known_limitations"])


class TestStealth(_Base):
    def test_stealth_no_record(self):
        out = erv.record_program_run(
            trace_dir=self.trace, output_text="p",
            enforcement_model="boundary_only", stealth=True)
        self.assertIsNone(out)
        self.assertIsNone(_read_packet(self.trace))


class TestStandingLaneRouting(_Base):
    """A standing:true deploy_probe recipe routes onto the packet + fills; a
    standing:false one does not (judge P3 — filter on catalog.recipes)."""

    def _make_repo(self, standing: bool):
        repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(os.path.join(repo, ".ora"))
        subprocess.run(["git", "-C", repo, "init", "-q"], check=True)
        subprocess.run(["git", "-C", repo, "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", repo, "config", "user.name", "t"], check=True)
        (Path(repo) / "x.md").write_text("# x\n")
        subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
        subprocess.run(["git", "-C", repo, "commit", "-qm",
                        "publish: harvest live content (+1 ~0 -0)"], check=True)
        (Path(repo) / ".ora" / "evidence.yaml").write_text(
            "checks: {}\n"
            "recipes:\n"
            "  deploy:\n"
            f"    lane: deploy_probe\n    target: published\n"
            f"    standing: {'true' if standing else 'false'}\n"
            "    probes: [{kind: git_heartbeat, ref: HEAD, match: 'harvest live',"
            " max_age_s: 999999999}]\n"
            "    rollback: 'none: next FULL build'\n"
            "runner: {working_dir: r, redact: x}\n", encoding="utf-8")
        return repo

    def test_standing_true_routes_and_fills(self):
        repo = self._make_repo(standing=True)
        erv.record_program_run(
            trace_dir=self.trace, output_text="prose", repo_root=repo,
            enforcement_model="boundary_only")
        pkt = _read_packet(self.trace)
        lanes = {l["lane"]: l for l in pkt["evidence_lanes"]}
        self.assertIn("deploy_probe", lanes)
        # the git_heartbeat probe PASSed (HEAD matches, not stale) → sufficient
        self.assertTrue(lanes["deploy_probe"]["sufficient"])
        self.assertEqual(
            lanes["deploy_probe"]["result"]["deploy_probe"]["verdict_counts"]["PASS"], 1)

    def test_standing_false_not_routed(self):
        repo = self._make_repo(standing=False)
        erv.record_program_run(
            trace_dir=self.trace, output_text="prose", repo_root=repo,
            enforcement_model="boundary_only")
        pkt = _read_packet(self.trace)
        lanes = [l["lane"] for l in pkt["evidence_lanes"]]
        self.assertNotIn("deploy_probe", lanes)  # standing:false → not a program-run lane


class TestTurnContextPrimitive(unittest.TestCase):
    def test_set_returns_token_reset_restores(self):
        # judge P2 primitive: capture prior, set per-run, restore exactly.
        te.set_turn_context()  # baseline: unset-ish
        prior = te.get_turn_context()["trace_dir"]
        tok = te.set_turn_context(trace_dir="/run-a", conversation_id="run-a")
        self.assertEqual(te.get_turn_context()["trace_dir"], "/run-a")
        te.reset_turn_context(tok)
        self.assertEqual(te.get_turn_context()["trace_dir"], prior)

    def test_reset_none_is_noop(self):
        te.reset_turn_context(None)  # must not raise
        te.set_turn_context()


if __name__ == "__main__":
    unittest.main()
