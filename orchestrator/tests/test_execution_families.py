"""Execution Review Phase 8 Chunk C — deploy_probe + render_inspect fillers.

Covers:
  * deploy_probe verdict truth table per kind (page/sitemap/feed/headers/
    git_heartbeat) incl. 403/timeout/missing-header/local-ref staleness →
    tri-state PASS/FAIL/INDETERMINATE;
  * all-PASS sufficiency; mandatory rollback rendered; probe events recorded;
  * ⚖ C1 — per kind, a sanitized probe ref survives BOTH the redaction path
    (explicit sensitivity:public event) AND manifest_axes("deploy_probe:<kind>")
    (non-fail-closed);
  * ⚖ C2 — git_heartbeat runs ZERO `git fetch`;
  * renderer: informational header, no bare INSUFFICIENT token, durable_summary
    counts-only; lane result is scrub-conformant (JSON-primitive, URL under `ref`).
"""
from __future__ import annotations

import json
import os
import sys
import unittest
import unittest.mock as mock
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import tool_events as te                       # noqa: E402
import execution_families as ef                # noqa: E402
import execution_packet as ep                  # noqa: E402
import execution_persistence as epersist       # noqa: E402
import evidence_runner as er                   # noqa: E402


def _lane(name, target):
    return ep.EvidenceLane(target=target, lane=name)


def _pkt_with(lane):
    p = ep.ExecutionPacket(task_id="t")
    p.evidence_lanes = [lane]
    return p


class _Recipe:
    def __init__(self, **k):
        self.__dict__.update(k)


def _fake_fetch(status=None, body="", headers=None, error=None):
    d = {"url": "u", "markdown": body, "title": None, "channel": "httpx",
         "fetched_at": "t", "status_code": status, "headers": headers}
    if error:
        d["error"] = error
    return d


class TestContentVerdict(unittest.TestCase):
    def test_truth_table(self):
        self.assertEqual(ef._content_verdict(_fake_fetch(200, "has slug-x"), "slug-x")[0], "PASS")
        self.assertEqual(ef._content_verdict(_fake_fetch(200, "nope"), "slug-x")[0], "FAIL")
        self.assertEqual(ef._content_verdict(_fake_fetch(200, "anything"), None)[0], "PASS")
        self.assertEqual(ef._content_verdict(_fake_fetch(404), None)[0], "FAIL")
        self.assertEqual(ef._content_verdict(_fake_fetch(403), None)[0], "INDETERMINATE")
        self.assertEqual(ef._content_verdict(_fake_fetch(429), None)[0], "INDETERMINATE")
        self.assertEqual(ef._content_verdict(_fake_fetch(503), None)[0], "INDETERMINATE")
        self.assertEqual(ef._content_verdict(_fake_fetch(None, error="timeout"), None)[0],
                         "INDETERMINATE")


class TestHeadersVerdict(unittest.TestCase):
    def test_fresh_stale_missing(self):
        v, _, _ = ef._headers_verdict(_fake_fetch(200, headers={"age": "10"}), "age", 3600)
        self.assertEqual(v, "PASS")
        v, _, _ = ef._headers_verdict(_fake_fetch(200, headers={"age": "99999"}), "age", 3600)
        self.assertEqual(v, "FAIL")
        v, _, _ = ef._headers_verdict(_fake_fetch(200, headers={}), "age", 3600)
        self.assertEqual(v, "INDETERMINATE")     # header absent
        v, _, _ = ef._headers_verdict(_fake_fetch(403), "age", 3600)
        self.assertEqual(v, "INDETERMINATE")     # non-200


class TestDeployProbeFiller(unittest.TestCase):
    def test_all_pass_sufficient(self):
        recipe = _Recipe(probes=[{"kind": "page", "url": "https://x/p",
                                  "must_contain": "ok"}],
                         rollback="none: next FULL build")
        lane = _lane("deploy_probe", "published")
        pkt = _pkt_with(lane)
        with mock.patch.object(ef, "_http_fetch",
                               return_value=_fake_fetch(200, "all ok here")):
            summary = ef.fill_deploy_probe_lane(pkt, lane, fill_ctx={"recipe": recipe})
        self.assertTrue(lane.sufficient)
        self.assertEqual(summary["verdict_counts"]["PASS"], 1)
        self.assertEqual(summary["rollback"], "none: next FULL build")

    def test_any_indeterminate_not_sufficient(self):
        recipe = _Recipe(probes=[{"kind": "page", "url": "https://x/p"}],
                         rollback="ref: rollback-runbook")
        lane = _lane("deploy_probe", "published")
        pkt = _pkt_with(lane)
        with mock.patch.object(ef, "_http_fetch", return_value=_fake_fetch(403)):
            ef.fill_deploy_probe_lane(pkt, lane, fill_ctx={"recipe": recipe})
        self.assertFalse(lane.sufficient)

    def test_stealth_no_fill(self):
        recipe = _Recipe(probes=[{"kind": "page", "url": "https://x"}], rollback="x")
        lane = _lane("deploy_probe", "published")
        pkt = _pkt_with(lane)
        out = ef.fill_deploy_probe_lane(pkt, lane, fill_ctx={"recipe": recipe,
                                                             "stealth": True})
        self.assertIsNone(out)
        self.assertIsNone(lane.sufficient)

    def test_failing_probe_beyond_render_cap_not_sufficient(self):
        # ⚖ code-review P1: the _LANE_PROBE_CAP render bound must NEVER limit
        # execution/sufficiency. Declare cap+1 probes where the LAST (beyond the
        # render cap) FAILs — it must still run + count, so the lane is NOT
        # sufficient, and the stored rows are capped with probes_truncated True.
        n = ef._LANE_PROBE_CAP + 1
        probes = [{"kind": "page", "url": f"https://x/p{i}", "must_contain": "ok"}
                  for i in range(n)]
        recipe = _Recipe(probes=probes, rollback="none: x")
        lane = _lane("deploy_probe", "published")
        pkt = _pkt_with(lane)
        calls = {"n": 0}

        def fetch(url, timeout_s):
            calls["n"] += 1
            # every probe passes EXCEPT the last-declared one (beyond the cap)
            body = "" if calls["n"] == n else "ok"
            return _fake_fetch(200, body)

        with mock.patch.object(ef, "_http_fetch", side_effect=fetch):
            summary = ef.fill_deploy_probe_lane(pkt, lane, fill_ctx={"recipe": recipe})
        self.assertEqual(calls["n"], n)                 # ALL probes ran
        self.assertFalse(lane.sufficient)               # the beyond-cap FAIL counts
        self.assertEqual(summary["verdict_counts"]["FAIL"], 1)
        self.assertEqual(len(summary["probes"]), ef._LANE_PROBE_CAP)  # rows capped
        self.assertTrue(summary["probes_truncated"])

    def test_url_sanitized_in_result(self):
        recipe = _Recipe(probes=[{"kind": "page",
                                  "url": "https://x/p?sig=SECRETSIG&a=1"}],
                         rollback="x")
        lane = _lane("deploy_probe", "published")
        pkt = _pkt_with(lane)
        with mock.patch.object(ef, "_http_fetch", return_value=_fake_fetch(200)):
            summary = ef.fill_deploy_probe_lane(pkt, lane, fill_ctx={"recipe": recipe})
        ref = summary["probes"][0]["ref"]
        self.assertNotIn("SECRETSIG", ref)
        self.assertIn("stripped", ref)


class TestC2GitHeartbeatNoFetch(unittest.TestCase):
    def test_local_ref_no_fetch(self):
        # ⚖ C2: git_heartbeat inspects the LOCAL ref only — never a `git fetch`.
        calls = []

        def fake_git(repo, args, **k):
            calls.append(args)
            return 0, str(1_000_000_000)   # an old commit ts

        with mock.patch.object(ef._er, "_git", side_effect=fake_git):
            v, reason, age = ef._git_heartbeat_verdict("/repo", "origin/main",
                                                       "publish", 999999999999)
        self.assertEqual(v, "PASS")
        # Only a `log` read was issued — no `fetch` anywhere.
        self.assertTrue(all(a[0] == "log" for a in calls))
        self.assertFalse(any("fetch" in a for a in calls))

    def test_stale_local_ref_fails(self):
        with mock.patch.object(ef._er, "_git",
                               return_value=(0, str(1_000_000_000))):
            v, _, _ = ef._git_heartbeat_verdict("/repo", "origin/main", "x", 60)
        self.assertEqual(v, "FAIL")

    def test_no_matching_commit_indeterminate(self):
        with mock.patch.object(ef._er, "_git", return_value=(0, "")):
            v, _, _ = ef._git_heartbeat_verdict("/repo", "origin/main", "x", 60)
        self.assertEqual(v, "INDETERMINATE")


class TestC1ManifestAndRedaction(unittest.TestCase):
    """⚖ C1: for every kind, a sanitized ref survives BOTH the redaction path AND
    a manifest lookup (non-fail-closed)."""

    KINDS = ("page", "sitemap", "feed", "headers", "git_heartbeat")

    def test_manifest_axes_not_fail_closed_per_kind(self):
        for kind in self.KINDS:
            axes = te.manifest_axes(f"deploy_probe:{kind}")
            self.assertNotIn("unknown", axes, kind)   # fail-closed sets unknown=True
            self.assertEqual(axes["sensitivity"], "public", kind)

    def test_redaction_keeps_ref_on_explicit_public_event(self):
        # _redact_for_record keys off the EVENT's sensitivity (public here) → keeps
        # reads[]. A missing sensitivity would default to secret and strip them.
        for kind in self.KINDS:
            evt = {"event": "deploy_probe", "action": f"deploy_probe:{kind}",
                   "sensitivity": "public",
                   "reads": [{"what": "https://x/probe", "where": "network"}]}
            red = te._redact_for_record(dict(evt))
            self.assertIn("reads", red, kind)
            self.assertEqual(red["reads"][0]["what"], "https://x/probe", kind)

    def test_probe_event_recorded_public_with_ref(self):
        import tempfile
        prev = os.environ.pop("ORA_TOOL_EVENTS", None)   # enable recording hermetically
        try:
            with tempfile.TemporaryDirectory() as d:
                te.set_turn_context(trace_dir=d, conversation_id="c1")
                try:
                    ef._record_probe_event("page", "https://x/p", "PASS", "200")
                finally:
                    te.set_turn_context()
                path = os.path.join(d, "tool-events.jsonl")
                lines = Path(path).read_text().splitlines()
                evts = [json.loads(x) for x in lines if x.strip()]
                dp = [e for e in evts if e.get("action") == "deploy_probe:page"]
                self.assertTrue(dp)
                self.assertEqual(dp[0]["sensitivity"], "public")
                self.assertEqual(dp[0]["correlation"]["conversation_id"], "c1")
        finally:
            if prev is not None:
                os.environ["ORA_TOOL_EVENTS"] = prev


class TestDeployProbeRender(unittest.TestCase):
    def test_informational_header_no_insufficient_token(self):
        lane = _lane("deploy_probe", "published")
        lane.result = {"deploy_probe": {"probes": [{"kind": "page", "ref": "u",
                       "verdict": "FAIL", "reason": "404"}],
                       "rollback": "x", "verdict_counts": {"PASS": 0, "FAIL": 1,
                       "INDETERMINATE": 0}}}
        lane.sufficient = False
        pkt = _pkt_with(lane)
        text = ep.render_for_review(pkt)
        self.assertIn("DEPLOY PROBE (informational", text)
        self.assertNotIn("INSUFFICIENT", text)   # the bare token never appears

    def test_durable_summary_counts_only(self):
        lane = _lane("deploy_probe", "published")
        lane.result = {"deploy_probe": {"probes": [{"kind": "page",
                       "ref": "https://secret.example/p", "verdict": "PASS",
                       "reason": "200"}], "rollback": "sensitive-runbook-detail",
                       "verdict_counts": {"PASS": 1, "FAIL": 0, "INDETERMINATE": 0}}}
        lane.sufficient = True
        pkt = _pkt_with(lane)
        text = ep.render_for_review(pkt, durable_summary=True)
        self.assertIn("DEPLOY PROBE", text)
        self.assertNotIn("secret.example", text)          # no refs
        self.assertNotIn("sensitive-runbook-detail", text)   # no rollback free-text

    def test_lane_result_scrub_conformant(self):
        # deploy_probe result must be JSON-primitive with URLs under `ref` so the
        # durable scrub covers it; verdict tokens survive as structural keys.
        lane = _lane("deploy_probe", "published")
        lane.result = {"deploy_probe": {"probes": [{"kind": "page",
                       "ref": "https://x/p?token=SEKRET", "verdict": "PASS",
                       "reason": "200"}], "rollback": "r",
                       "verdict_counts": {"PASS": 1}}}
        lane.sufficient = True
        pkt = ep.ExecutionPacket(task_id="t")
        pkt.evidence_lanes = [lane]
        red = epersist.redact_for_durable(pkt, max_sensitivity="public")
        self.assertIsNotNone(red)   # fail-closed would return None
        # walk the redacted lane; verdict token preserved, no crash
        rl = red.evidence_lanes[0].result["deploy_probe"]
        self.assertEqual(rl["probes"][0]["verdict"], "PASS")


class TestRenderInspectFiller(unittest.TestCase):
    def test_owed_when_no_such_check(self):
        recipe = _Recipe(check="missing-check")

        class _Cat:
            checks = {}
        lane = _lane("render_inspect", "artifacts")
        pkt = _pkt_with(lane)
        out = ef.fill_render_inspect_lane(
            pkt, lane, fill_ctx={"recipe": recipe, "catalog": _Cat(),
                                 "repo_root": "/x", "runner": er,
                                 "context_pkg": {}})
        self.assertIsNone(out)
        self.assertIsNone(lane.sufficient)   # stays owed

    def test_unrun_check_stays_owed_not_failed(self):
        # ⚖ pre-check fold: when the named check does NOT run (_run_named_check
        # returns None — SEC-2 base-unknown / lifecycle failure), the lane stays
        # OWED (sufficient None), never a false FAILED (sufficient False).
        class _Check:
            name = "render-validity"

        class _Cat:
            checks = {"render-validity": _Check()}
        lane = _lane("render_inspect", "artifacts")
        pkt = _pkt_with(lane)
        with mock.patch.object(ef, "_run_named_check", return_value=None):
            out = ef.fill_render_inspect_lane(
                pkt, lane, fill_ctx={"recipe": _Recipe(check="render-validity"),
                                     "catalog": _Cat(), "repo_root": "/x",
                                     "runner": er, "context_pkg": {}})
        self.assertIsNone(out)
        self.assertIsNone(lane.sufficient)   # owed, NOT False


if __name__ == "__main__":
    unittest.main()
