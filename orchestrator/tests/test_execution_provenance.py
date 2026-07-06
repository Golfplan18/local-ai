"""Execution Review Phase 8 Chunk A — collect_provenance lane + library guard.

Covers the judge-required conditions from the Rev-4 design gate:
  * worker-thread ContextVar propagation — a claim-verify-style worker's web
    event lands in the TURN trace sink with the turn's conversation_id;
  * a STEALTH-context worker records NOTHING;
  * BYTE-budgeted event batching — very-long-URL fixtures, every emitted line
    under MAX_LINE_BYTES, zero read descriptors lost;
plus sanitize_url, the guard suppression flag, registry build rules
(injected / secret-existence-only / sensitive-descriptor / hash-verified
re-read), the Level-1-never-sufficient truth table, Level-2 semantics,
renderer framing (informational on mixed turns; durable_summary suppression),
and the persistence extensions (lane scrub, fail-closed, OQ-3 tier,
note_ref stamping is covered in test_execution_persistence additions).
"""

from __future__ import annotations

import contextvars
import json
import os
import sys
import tempfile
import unittest
import unittest.mock as mock
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import tool_events as te                      # noqa: E402
import execution_provenance as eprov          # noqa: E402
import execution_packet as ep                 # noqa: E402
import execution_persistence as epersist      # noqa: E402
from tools import web_search as ws            # noqa: E402
from tools import web_fetch as wf             # noqa: E402

_ENV_KEYS = ("ORA_TOOL_EVENTS", "ORA_TOOL_EVENTS_PATH",
             "ORA_PROVENANCE_CLAIM_MAP")


class _EventEnvMixin(unittest.TestCase):
    """Hermetic env + turn-context handling (the P7 save/clear/restore
    pattern, proven under hostile ambient env)."""

    def setUp(self):
        super().setUp()
        self._saved = {k: os.environ.get(k) for k in _ENV_KEYS}
        os.environ.pop("ORA_TOOL_EVENTS", None)          # recording ON
        self.tmp = tempfile.TemporaryDirectory()
        self.trace_dir = os.path.join(self.tmp.name, "trace")
        os.makedirs(self.trace_dir, exist_ok=True)
        self.global_sink = os.path.join(self.tmp.name, "global-sink.jsonl")
        os.environ["ORA_TOOL_EVENTS_PATH"] = self.global_sink
        self._ctx_token = te._TURN_CTX.set(None)

    def tearDown(self):
        te._TURN_CTX.reset(self._ctx_token)
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()
        super().tearDown()

    @staticmethod
    def _lines(path):
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    def _trace_events(self):
        return self._lines(os.path.join(self.trace_dir, "tool-events.jsonl"))


class TestSanitizeUrl(unittest.TestCase):
    def test_credential_params_stripped(self):
        cases = {
            "https://x.com/a?sig=SECRETSAS&b=1": "sig",
            "https://x.com/a?X-Amz-Signature=abc123": "x-amz-signature",
            "https://x.com/a?X-Goog-Signature=abc123": "x-goog-signature",
            "https://x.com/a?key=k123&q=ok": "key",
            "https://x.com/a?api_key=k123": "api_key",
            "https://x.com/a?access_token=t123": "access_token",
        }
        for url in cases:
            out = te.sanitize_url(url)
            self.assertNotIn("SECRETSAS", out)
            self.assertNotIn("abc123", out)
            self.assertNotIn("k123", out)
            self.assertNotIn("t123", out)
            # Either the URL-param strip marker survives, or scrub_content's
            # own token patterns re-matched the stripped form ([SCRUBBED]) —
            # belt-over-belt; both prove the credential never rides through.
            self.assertTrue("…[stripped]" in out or "[SCRUBBED]" in out, out)

    def test_plain_url_untouched(self):
        url = "https://example.com/path?page=2&q=inflation"
        self.assertEqual(te.sanitize_url(url), url)

    def test_sanitizer_failure_fails_closed(self):
        with mock.patch.object(te, "scrub_content",
                               side_effect=RuntimeError("boom")):
            out = te.sanitize_url("https://example.com/x")
        self.assertNotIn("example.com", out)
        self.assertIn("withheld", out)


class TestByteBudgetedBatching(_EventEnvMixin):
    def test_long_urls_split_under_cap_nothing_lost(self):
        te.set_turn_context(trace_dir=self.trace_dir, conversation_id="conv-b")
        # 40 reads with multi-KB query strings — a count cap of 24 would emit
        # a first event far beyond MAX_LINE_BYTES.
        reads = [{"what": f"https://e.com/{i}?" + "q" * 3000,
                  "where": "network", "chars": 100} for i in range(40)]
        te.record_web_reads("web_search", reads)
        raw = open(os.path.join(self.trace_dir, "tool-events.jsonl"),
                   encoding="utf-8").read().splitlines()
        self.assertGreater(len(raw), 1, "expected multiple batch_part events")
        total = 0
        for line in raw:
            self.assertLess(len(line.encode("utf-8")), te.MAX_LINE_BYTES,
                            "an emitted line crossed MAX_LINE_BYTES")
            ev = json.loads(line)
            self.assertIn("reads", ev, "reads[] was truncated away")
            total += len(ev["reads"])
            if len(raw) > 1:
                self.assertIn("batch_part", ev)
        self.assertEqual(total, 40, "read descriptors were lost across parts")

    def test_pathological_single_what_is_capped_with_hash_tail(self):
        te.set_turn_context(trace_dir=self.trace_dir, conversation_id="c")
        te.record_web_reads("web_fetch", [{"what": "https://e.com/" + "z" * 9000,
                                           "where": "network"}])
        evs = self._trace_events()
        self.assertEqual(len(evs), 1)
        what = evs[0]["reads"][0]["what"]
        self.assertLess(len(what), 600)
        self.assertIn("…[capped sha256:", what)

    def test_suppression_flag_kills_recording(self):
        te.set_turn_context(trace_dir=self.trace_dir, conversation_id="c")
        with te.suppress_library_recording():
            te.record_web_reads("web_search", [{"what": "q", "where": "network"}])
        self.assertEqual(self._trace_events(), [])


class TestWorkerThreadContext(_EventEnvMixin):
    """The judge-P1 conditions: worker events must carry the TURN context."""

    def test_worker_event_lands_in_turn_trace_with_conversation_id(self):
        te.set_turn_context(trace_dir=self.trace_dir,
                            conversation_id="conv-worker", stealth=False)

        def worker():
            te.record_web_reads("web_search",
                                [{"what": "https://e.com/a", "where": "network"}])

        with ThreadPoolExecutor(max_workers=1) as ex:
            ctx = contextvars.copy_context()
            ex.submit(ctx.run, worker).result()

        evs = self._trace_events()
        self.assertEqual(len(evs), 1, "worker event did not reach the TURN sink")
        self.assertEqual(evs[0].get("conversation_id"), "conv-worker")
        self.assertEqual(self._lines(self.global_sink), [],
                         "worker event misfiled to the global sink")

    def test_bare_submit_misfiles_proving_copy_context_is_load_bearing(self):
        # The NEGATIVE control for the P1: without copy_context the worker's
        # ContextVar is empty → the event misfiles to the global sink with no
        # conversation_id. This is the exact defect the fold closes.
        te.set_turn_context(trace_dir=self.trace_dir,
                            conversation_id="conv-worker", stealth=False)

        def worker():
            te.record_web_reads("web_search",
                                [{"what": "https://e.com/a", "where": "network"}])

        with ThreadPoolExecutor(max_workers=1) as ex:
            ex.submit(worker).result()

        self.assertEqual(self._trace_events(), [])
        misfiled = self._lines(self.global_sink)
        self.assertEqual(len(misfiled), 1)
        self.assertFalse(misfiled[0].get("conversation_id"))

    def test_stealth_worker_records_nothing(self):
        te.set_turn_context(trace_dir=self.trace_dir,
                            conversation_id="conv-s", stealth=True)

        def worker():
            te.record_web_reads("web_fetch",
                                [{"what": "https://e.com/s", "where": "network",
                                  "content_hash": "ab" * 8}])

        with ThreadPoolExecutor(max_workers=1) as ex:
            ctx = contextvars.copy_context()
            ex.submit(ctx.run, worker).result()

        self.assertEqual(self._trace_events(), [])
        self.assertEqual(self._lines(self.global_sink), [])

    def test_claim_verification_uses_ctx_submit(self):
        # The fix itself: assemble_claim_verification_evidence must propagate
        # context into its workers. Observed end-to-end: a fake
        # web_search_structured (patched at the module ref) records a read
        # via the guard from inside the worker; the event must land in the
        # TURN sink.
        import claim_verification as cv
        te.set_turn_context(trace_dir=self.trace_dir,
                            conversation_id="conv-cv", stealth=False)

        def fake_search(query, max_results=5, **kw):
            te.record_web_reads("web_search",
                                [{"what": f"query:{query}", "where": "network"}])
            return [{"title": "t", "url": "https://e.com/r", "snippet": "s"}]

        claims = [{"claim_num": 1, "claim_type": "statistic",
                   "risk_level": "high", "claim": "GDP rose 3%",
                   "why_flagged": "w", "challenge_query": "gdp q1"}]
        with mock.patch.object(cv, "web_search_structured",
                               side_effect=fake_search):
            with mock.patch.object(cv, "score_external_chunks",
                                   side_effect=lambda ch, **k: ch):
                cv.assemble_claim_verification_evidence(claims)

        evs = self._trace_events()
        self.assertTrue(evs, "claim-verify worker event missed the TURN sink")
        self.assertEqual(evs[0].get("conversation_id"), "conv-cv")


class TestLibraryGuardIntegration(_EventEnvMixin):
    def test_web_search_structured_records_result_urls(self):
        te.set_turn_context(trace_dir=self.trace_dir, conversation_id="c1")
        raw = [{"title": "T", "href": "https://e.com/one?sig=LEAKME", "body": "B"}]
        with mock.patch.object(ws, "_gather_raw", return_value=raw):
            ws.web_search_structured("test query")
        evs = self._trace_events()
        self.assertEqual(len(evs), 1)
        whats = [r["what"] for r in evs[0]["reads"]]
        self.assertEqual(whats[0], "query:test query")
        self.assertTrue(any(w.startswith("https://e.com/one") for w in whats[1:]))
        self.assertFalse(any("LEAKME" in w for w in whats))

    def test_web_fetch_records_content_only_hash(self):
        import hashlib
        te.set_turn_context(trace_dir=self.trace_dir, conversation_id="c2")
        result = {"url": "https://e.com/p", "markdown": "hello world",
                  "title": "t", "channel": "httpx", "fetched_at": "2026-07-05"}
        with mock.patch.object(wf, "_fetch_httpx", return_value=result):
            with mock.patch.object(wf, "_is_acceptable", return_value=True):
                wf.web_fetch("https://e.com/p")
        evs = self._trace_events()
        self.assertEqual(len(evs), 1)
        r = evs[0]["reads"][0]
        expect = hashlib.sha256(b"hello world").hexdigest()[:16]
        self.assertEqual(r["content_hash"], expect)
        self.assertEqual(r["chars"], len("hello world"))

    def test_guard_suppressed_under_dispatcher_context(self):
        te.set_turn_context(trace_dir=self.trace_dir, conversation_id="c3")
        raw = [{"title": "T", "href": "https://e.com/x", "body": "B"}]
        with te.suppress_library_recording():
            with mock.patch.object(ws, "_gather_raw", return_value=raw):
                ws.web_search_structured("q")
        self.assertEqual(self._trace_events(), [])


def _mk_ctx(**over):
    ctx = {
        "web_source_chunks": [
            {"url": "https://web.com/a", "title": "A", "document": "alpha body",
             "retrieved_at": "2026-07-05T00:00:00Z", "injected": True},
            {"url": "https://web.com/b", "title": "B", "document": "beta body"},
        ],
        "claim_evidence": [
            {"claim": {"claim_num": 1, "claim": "X grew 5%",
                       "challenge_query": "x growth"},
             "query": "x growth",
             "chunks": [{"url": "https://ev.com/1", "title": "E",
                         "document": "evidence body",
                         "retrieved_at": "2026-07-05T00:00:01Z"}]},
        ],
        "concept_rag": ("[type: engram | weight: 1.00 | source: My Note]\n"
                        "note body text\n\n"),
        "tool_results": "FRED CPI: 3.2%",
    }
    ctx.update(over)
    return ctx


class TestRegistryAndLevel1(_EventEnvMixin):
    def test_registry_kinds_injected_and_timestamps(self):
        reg, stats = eprov.build_registry(_mk_ctx(), None)
        kinds = {s["kind"] for s in reg}
        self.assertEqual(kinds, {"web", "vault", "tool"})
        a = next(s for s in reg if s.get("ref") == "https://web.com/a")
        b = next(s for s in reg if s.get("ref") == "https://web.com/b")
        self.assertTrue(a["injected"])
        self.assertFalse(b["injected"])          # formatter never reached it
        self.assertEqual(stats["missing_timestamps"], 1)   # chunk b
        vault = next(s for s in reg if s["kind"] == "vault")
        self.assertEqual(vault["ref"], "My Note")
        self.assertTrue(vault["injected"])
        self.assertIn("note body text", vault["excerpt"])

    def test_file_sources_secret_sensitive_and_hash_verified_reread(self):
        # Real file for the hash-verified re-read; Windows-shaped secret path
        # (P7 fixture pattern) for existence-only; a sensitive path for the
        # descriptor rule.
        good = os.path.join(self.tmp.name, "doc.txt")
        with open(good, "w", encoding="utf-8") as f:
            f.write("stable content")
        import hashlib
        good_hash = hashlib.sha256(b"stable content").hexdigest()[:16]
        changed = os.path.join(self.tmp.name, "changed.txt")
        with open(changed, "w", encoding="utf-8") as f:
            f.write("post-hoc different")
        events = [
            {"event": "tool", "action": "file_read", "ts": "T1",
             "reads": [{"what": good, "content_hash": good_hash}]},
            {"event": "tool", "action": "file_read", "ts": "T2",
             "reads": [{"what": changed, "content_hash": "0" * 16}]},
            {"event": "tool", "action": "file_read", "ts": "T3",
             "reads": [{"what": r"C:\Users\x\.ssh\id_rsa"}]},
            {"event": "tool", "action": "file_read", "ts": "T4",
             "reads": [{"what": "/prod/records.db"}]},
            {"event": "mcp", "action": "mcp_docs_read", "mutability": "read",
             "ts": "T5"},
        ]
        with open(os.path.join(self.trace_dir, "tool-events.jsonl"), "w",
                  encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")

        sens_map = {good: "private", changed: "private",
                    r"C:\Users\x\.ssh\id_rsa": "secret",
                    "/prod/records.db": "sensitive"}
        with mock.patch.object(te, "resolve_path_sensitivity",
                               side_effect=lambda p: sens_map.get(p, "private")):
            reg, stats = eprov.build_registry({"claim_evidence": []},
                                              self.trace_dir)

        by_ref = {s.get("ref"): s for s in reg}
        self.assertIn("stable content", by_ref[good]["excerpt"])
        self.assertIsNone(by_ref[changed].get("excerpt"))
        self.assertTrue(by_ref[changed].get("content_changed"))
        secrets = [s for s in reg if s.get("sensitivity") == "secret"]
        self.assertEqual(len(secrets), 1)
        self.assertNotIn("ref", secrets[0])       # existence-only: no path
        self.assertNotIn("excerpt", secrets[0])
        sens = by_ref.get("[sensitive PATH withheld]")
        self.assertIsNotNone(sens)
        self.assertNotIn("records.db", json.dumps(reg))
        mcp = [s for s in reg if s["kind"] == "mcp"]
        self.assertEqual(len(mcp), 1)
        self.assertTrue(mcp[0]["opaque"])
        self.assertNotIn("excerpt", mcp[0])
        self.assertEqual(stats["opaque_channels"], 1)

    def test_level1_rows_are_unassessed_and_total_is_none(self):
        ctx = _mk_ctx()
        reg, stats = eprov.build_registry(ctx, None)
        rows = eprov.build_level1_map(ctx, reg)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["support_status"], "unassessed")
        self.assertTrue(rows[0]["source_ids"])
        cov = eprov.compute_coverage(rows, reg, stats, level2_ran=False)
        self.assertIsNone(cov["claims_total"])
        self.assertEqual(cov["claims_examined"], 1)

    def test_sufficiency_truth_table(self):
        reg = [{"source_id": "s1", "kind": "web", "ref": "r",
                "injected": True}]
        sup = [{"claim_id": "c1", "source_ids": ["s1"],
                "support_status": "supported"}]
        una = [{"claim_id": "c1", "source_ids": ["s1"],
                "support_status": "unassessed"}]
        # Level 1 alone can NEVER be sufficient — even fully "supported" rows.
        cov = eprov.compute_coverage(sup, reg, {"opaque_channels": 0},
                                     level2_ran=False)
        self.assertFalse(eprov.decide_sufficiency(cov, sup))
        # Level 2 + all supported + no opaque → sufficient.
        cov = eprov.compute_coverage(sup, reg, {"opaque_channels": 0},
                                     level2_ran=True)
        self.assertTrue(eprov.decide_sufficiency(cov, sup))
        # Any unassessed/unsupported row blocks.
        cov = eprov.compute_coverage(una, reg, {"opaque_channels": 0},
                                     level2_ran=True)
        self.assertFalse(eprov.decide_sufficiency(cov, una))
        # An opaque channel blocks even a fully-supported Level-2 map (§17).
        cov = eprov.compute_coverage(sup, reg, {"opaque_channels": 1},
                                     level2_ran=True)
        self.assertFalse(eprov.decide_sufficiency(cov, sup))
        # Zero claims is never sufficient.
        cov = eprov.compute_coverage([], reg, {"opaque_channels": 0},
                                     level2_ran=True)
        self.assertFalse(eprov.decide_sufficiency(cov, []))

    def test_level2_parser_and_source_validation(self):
        reg = [{"source_id": "s1", "kind": "web", "ref": "r1",
                "injected": True, "excerpt": "e1"},
               {"source_id": "s9", "kind": "mcp", "injected": True,
                "opaque": True}]
        raw = ("CLAIM 1: X grew | SOURCES: s1 | SUPPORT: supported\n"
               "CLAIM 2: Y fell | SOURCES: s9 | SUPPORT: supported\n"
               "CLAIM 3: Z flat | SOURCES:  | SUPPORT: unsupported\n"
               "garbage line\n")
        out = eprov.run_level2("deliverable", reg, lambda s, u: raw)
        self.assertTrue(out["ran"])
        rows = {r["claim_id"]: r for r in out["rows"]}
        self.assertEqual(rows["L2-1"]["support_status"], "supported")
        # s9 is opaque → not a valid support source → verdict demoted.
        self.assertEqual(rows["L2-2"]["support_status"], "unassessed")
        self.assertEqual(rows["L2-2"]["source_ids"], [])
        self.assertEqual(rows["L2-3"]["support_status"], "unsupported")
        # Unparseable output → ran False (Level-1-only, honest).
        out = eprov.run_level2("d", reg, lambda s, u: "no rows here")
        self.assertFalse(out["ran"])


class TestFillAndRender(_EventEnvMixin):
    def _packet(self, signals=None):
        return ep.build_execution_packet(
            signals=signals or {"source_read_suspected": True,
                                "any_mutation": False,
                                "source_candidate_reads": [
                                    {"action": "web_fetch", "where": "network",
                                     "what": "https://ev.com/1"},
                                    {"action": "rag_read", "where": "local",
                                     "chars": 10}]},
            context_pkg={}, output_text="deliverable text",
            risk_tier="standard", trace_ref=self.trace_dir)

    def test_fill_writes_map_stamps_confirmation_and_lane(self):
        pkt = self._packet()
        out = eprov.fill_provenance_lane(
            pkt, context_pkg=_mk_ctx(), response="deliverable",
            trace_dir=self.trace_dir, stealth=False, mixed_turn=False)
        self.assertIsNotNone(out)
        lane = next(l for l in pkt.evidence_lanes
                    if l.lane == "collect_provenance")
        self.assertFalse(lane.sufficient)          # Level 1 → never True
        self.assertEqual(lane.generated_by, ["provenance:level1"])
        map_path = os.path.join(self.trace_dir, "provenance-map.json")
        self.assertTrue(os.path.exists(map_path))
        # Post-hoc §7 confirmation: the used web candidate is confirmed; the
        # unused rag candidate is stamped used: False.
        cands = pkt.execution["source_reads"]
        web = next(c for c in cands if c["action"] == "web_fetch")
        rag = next(c for c in cands if c["action"] == "rag_read")
        self.assertTrue(web.get("confirmed"))
        self.assertNotIn("confirmed", rag)
        self.assertFalse(rag.get("used", True))

    def test_stealth_no_fill_no_artifact(self):
        pkt = self._packet()
        out = eprov.fill_provenance_lane(
            pkt, context_pkg=_mk_ctx(), response="d",
            trace_dir=self.trace_dir, stealth=True)
        self.assertIsNone(out)
        self.assertFalse(os.path.exists(
            os.path.join(self.trace_dir, "provenance-map.json")))
        lane = next(l for l in pkt.evidence_lanes
                    if l.lane == "collect_provenance")
        self.assertIsNone(lane.sufficient)

    def test_render_mixed_turn_is_informational_never_insufficient(self):
        pkt = self._packet(signals={"source_read_suspected": True,
                                    "any_mutation": True})
        eprov.fill_provenance_lane(pkt, context_pkg=_mk_ctx(), response="d",
                                   trace_dir=self.trace_dir, mixed_turn=True)
        text = ep.render_for_review(pkt)
        self.assertIn("informational — not a convergence input", text)
        self.assertNotIn("INSUFFICIENT", text)

    def test_render_source_read_only_shows_verdict_and_rows(self):
        pkt = self._packet()
        eprov.fill_provenance_lane(pkt, context_pkg=_mk_ctx(), response="d",
                                   trace_dir=self.trace_dir, mixed_turn=False)
        text = ep.render_for_review(pkt)
        self.assertIn("PROVENANCE [not sufficient]", text)
        self.assertIn("unassessed", text)
        self.assertIn("https://ev.com/1", text)

    def test_durable_summary_render_suppresses_rows_and_excerpts(self):
        pkt = self._packet()
        eprov.fill_provenance_lane(pkt, context_pkg=_mk_ctx(), response="d",
                                   trace_dir=self.trace_dir, mixed_turn=False)
        text = ep.render_for_review(pkt, durable_summary=True)
        self.assertIn("PROVENANCE", text)
        self.assertNotIn("excerpt:", text)
        self.assertNotIn("evidence body", text)
        self.assertNotIn("claim c1", text)


class TestPrecheckFolds(_EventEnvMixin):
    """Coverage for the adversarial pre-check folds."""

    def test_relationship_lane_parses_its_own_format(self):
        # The relationship formatter emits ### title + *Via: …* blocks, not
        # marker lines — the marker regex was a structural no-op for it.
        rel = ("### Compounding Effects\n"
               "*Via: engram->note (confidence: 0.8)*\n\n"
               "relationship body text here\n\n"
               "### Second Note\n"
               "*Via: note->note (confidence: 0.6)*\n\n"
               "second body\n")
        reg, _ = eprov.build_registry({"relationship_rag": rel}, None)
        graph = [s for s in reg if s["kind"] == "graph"]
        self.assertEqual(len(graph), 2)
        self.assertEqual(graph[0]["ref"], "Compounding Effects")
        self.assertTrue(graph[0]["injected"])
        self.assertIn("relationship body text", graph[0]["excerpt"])

    def test_level2_rejects_sources_not_shown_to_mapper(self):
        # s2 is injected+non-opaque but has NO excerpt → never offered; a
        # "supported" citation of it is fabricated provenance → demoted.
        reg = [{"source_id": "s1", "kind": "web", "ref": "r1",
                "injected": True, "excerpt": "e1"},
               {"source_id": "s2", "kind": "web", "ref": "r2",
                "injected": True}]
        raw = "CLAIM 1: X | SOURCES: s2 | SUPPORT: supported"
        out = eprov.run_level2("d", reg, lambda s, u: raw)
        self.assertTrue(out["ran"])
        self.assertEqual(out["rows"][0]["support_status"], "unassessed")
        self.assertEqual(out["rows"][0]["source_ids"], [])

    def test_level2_unparsed_lines_counted_and_block_sufficiency(self):
        reg = [{"source_id": "s1", "kind": "web", "ref": "r1",
                "injected": True, "excerpt": "e1"}]
        raw = ("CLAIM 1: X | SOURCES: s1 | SUPPORT: supported\n"
               "CLAIM 2: a wrapped row that lost\n"
               "its trailing half | SUPPORT: unsupported\n")
        out = eprov.run_level2("d", reg, lambda s, u: raw)
        self.assertTrue(out["ran"])
        self.assertGreater(out["unparsed_lines"], 0)
        cov = eprov.compute_coverage(out["rows"], reg,
                                     {"opaque_channels": 0}, level2_ran=True)
        cov["level2_unparsed"] = out["unparsed_lines"]
        self.assertFalse(eprov.decide_sufficiency(cov, out["rows"]),
                         "lost mapper lines must block sufficiency")

    def test_origin_unflagged_honored_when_stamped(self):
        ctx = {"claim_evidence": [
            {"claim": {"claim": "c"}, "origin": "unflagged",
             "chunks": [{"url": "https://e.com/1", "document": "d"}]}]}
        reg, _ = eprov.build_registry(ctx, None)
        rows = eprov.build_level1_map(ctx, reg)
        self.assertEqual(rows[0]["origin"], "unflagged")

    def test_failed_fetch_records_exit_not_ok(self):
        te.set_turn_context(trace_dir=self.trace_dir, conversation_id="cf")
        err = {"url": "https://e.com/down", "markdown": "", "title": None,
               "channel": "auto", "error": "all tiers failed",
               "fetched_at": "t"}
        with mock.patch.object(wf, "_fetch_httpx", return_value=err):
            with mock.patch.object(wf, "_fetch_playwright", return_value=err):
                with mock.patch.object(wf, "_fetch_jina", return_value=err):
                    wf.web_fetch("https://e.com/down")
        evs = self._trace_events()
        self.assertEqual(len(evs), 1)
        self.assertFalse(evs[0]["exit"]["ok"])
        # A failed read never fires the source-read signal (risk_gate
        # requires exit.ok) but the egress is OBSERVED (§16-3).

    def test_confirm_matches_capped_candidate_what(self):
        long_url = "https://e.com/" + "p" * 900
        pkt = ep.build_execution_packet(
            signals={"source_read_suspected": True, "any_mutation": False,
                     "source_candidate_reads": [
                         {"action": "web_fetch", "where": "network",
                          "what": te._capped_what(long_url)}]},
            context_pkg={}, output_text="d", risk_tier="standard",
            trace_ref=self.trace_dir)
        registry = [{"source_id": "s1", "kind": "web", "ref": long_url,
                     "injected": True}]
        rows = [{"claim_id": "c1", "source_ids": ["s1"],
                 "support_status": "unassessed"}]
        eprov.confirm_source_reads(pkt, rows, registry)
        cand = pkt.execution["source_reads"][0]
        self.assertTrue(cand.get("confirmed"),
                        "capped candidate failed to match uncapped ref")

    def test_oversize_file_never_slurped(self):
        big = os.path.join(self.tmp.name, "big.txt")
        with open(big, "w", encoding="utf-8") as f:
            f.write("x" * 10)
        with mock.patch.object(eprov.os.path, "getsize",
                               return_value=eprov._REREAD_MAX_BYTES + 1):
            content, changed, oversize = eprov._reread_file_excerpt(big, "ab")
        self.assertIsNone(content)
        self.assertTrue(oversize)

    def test_opaque_channels_deduped_across_events(self):
        events = [{"event": "mcp", "action": "mcp_docs_read",
                   "mutability": "read", "ts": f"T{i}"} for i in range(5)]
        with open(os.path.join(self.trace_dir, "tool-events.jsonl"), "w",
                  encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")
        reg, stats = eprov.build_registry({}, self.trace_dir)
        self.assertEqual(stats["opaque_channels"], 1,
                         "five calls to one MCP reader are ONE channel")

    def test_durable_scrub_keeps_web_refs_withholds_paths(self):
        res = {"provenance": {"rows": [
            {"claim_id": "c1", "support_status": "unassessed",
             "sources": [{"source_id": "s1",
                          "ref": "https://fred.stlouisfed.org/series/GDP"}]}],
            "map_ref": "/some/private/trace/provenance-map.json"}}
        out = epersist._scrub_lane_result(res, "private")
        ref = out["provenance"]["rows"][0]["sources"][0]["ref"]
        self.assertIn("fred.stlouisfed.org", ref,
                      "web refs must survive the durable scrub at private")
        self.assertIn("withheld", out["provenance"]["map_ref"])

    def test_mapper_family_rendered_when_present(self):
        pkt = ep.build_execution_packet(
            signals={"source_read_suspected": True, "any_mutation": False},
            context_pkg={}, output_text="d", risk_tier="standard",
            trace_ref=self.trace_dir)
        lane = next(l for l in pkt.evidence_lanes
                    if l.lane == "collect_provenance")
        lane.result = {"provenance": {
            "coverage": {"claims_total": 1, "claims_examined": 1,
                         "claims_mapped": 1, "claims_supported": 1,
                         "claims_unsupported": 0, "sources_total": 1,
                         "sources_used": 1, "sources_unused": 0,
                         "opaque_channels": 0, "missing_timestamps": 0,
                         "level2_ran": True},
            "rows": [], "rows_truncated": False, "map_ref": None,
            "mixed_turn": False,
            "mapper_family": "same_family (lowered assurance)"}}
        lane.sufficient = True
        text = ep.render_for_review(pkt)
        self.assertIn("mapper family: same_family (lowered assurance)", text)


try:
    import dispatcher as _dispatcher
    _DISPATCHER_OK = bool(getattr(_dispatcher, "_TOOLS_LOADED", False))
except Exception:                                     # pragma: no cover
    _dispatcher = None
    _DISPATCHER_OK = False


@unittest.skipUnless(_DISPATCHER_OK, "dispatcher tools not loaded")
class TestDispatcherWebSanitize(_EventEnvMixin):
    """Pre-check fold: the dispatcher's OWN web recording (which suppresses
    the library guard) must sanitize URLs too — reads[].what AND args."""

    def setUp(self):
        super().setUp()
        self._orig_sink = te.GLOBAL_SINK_DEFAULT
        te.GLOBAL_SINK_DEFAULT = self.global_sink
        te.reset_telemetry_health()
        _dispatcher.reset_consecutive()
        _dispatcher.set_permission_mode("auto-approve")
        te.set_turn_context(trace_dir=self.trace_dir, conversation_id="cd")

    def tearDown(self):
        te.GLOBAL_SINK_DEFAULT = self._orig_sink
        _dispatcher.set_permission_mode("approve-each")
        super().tearDown()

    def test_web_fetch_event_sanitized_and_guard_suppressed(self):
        signed = "https://acct.blob.core.windows.net/r.pdf?sig=SECRETSAS123"

        def fake_handler(params):
            # The real handler calls the guarded library function — prove the
            # suppression kills the inner record (exactly ONE event total).
            te.record_web_reads("web_fetch", [{"what": params.get("url"),
                                               "where": "network"}])
            return {"url": params.get("url"), "markdown": "body",
                    "title": "t", "channel": "httpx", "fetched_at": "now"}

        entry = _dispatcher.TOOL_REGISTRY["web_fetch"]
        with mock.patch.dict(entry, {"handler": fake_handler}):
            _dispatcher.dispatch("web_fetch", {"url": signed})

        evs = [e for e in self._trace_events()
               if e.get("action") == "web_fetch"]
        self.assertEqual(len(evs), 1, "library guard was not suppressed")
        blob = json.dumps(evs[0])
        self.assertNotIn("SECRETSAS123", blob,
                         "signed-URL credential rode the dispatcher event")
        import hashlib as _h
        self.assertEqual(evs[0]["reads"][0]["content_hash"],
                         _h.sha256(b"body").hexdigest()[:16],
                         "content_hash must cover the markdown body only")


class TestPersistenceExtensions(_EventEnvMixin):
    def _filled_packet(self, unsupported=0):
        pkt = ep.build_execution_packet(
            signals={"source_read_suspected": True, "any_mutation": False},
            context_pkg={}, output_text="d", risk_tier="standard",
            trace_ref=self.trace_dir)
        lane = next(l for l in pkt.evidence_lanes
                    if l.lane == "collect_provenance")
        rows = [{"claim_id": "c1", "claim_text": "PII: alice@example.com",
                 "support_status": ("unsupported" if unsupported else
                                    "unassessed"),
                 "sources": [{"source_id": "s1", "ref": "https://e.com/x"}],
                 "excerpt": "raw excerpt text"}]
        lane.result = {"provenance": {
            "coverage": {"claims_total": None, "claims_examined": 1,
                         "claims_mapped": 1, "claims_supported": 0,
                         "claims_unsupported": unsupported,
                         "sources_total": 1, "sources_used": 1,
                         "sources_unused": 0, "opaque_channels": 0,
                         "missing_timestamps": 0, "level2_ran": False},
            "rows": rows, "rows_truncated": False,
            "map_ref": os.path.join(self.trace_dir, "provenance-map.json"),
            "mixed_turn": False}}
        lane.sufficient = False
        lane.generated_by = ["provenance:level1"]
        return pkt

    def test_lane_scrub_sensitive_descriptors_preserve_structural_keys(self):
        pkt = self._filled_packet()
        red = epersist.redact_for_durable(pkt, max_sensitivity="sensitive")
        self.assertIsNotNone(red)
        lane = next(l for l in red.evidence_lanes
                    if l.lane == "collect_provenance")
        row = lane.result["provenance"]["rows"][0]
        self.assertNotIn("alice@example.com", json.dumps(lane.result))
        self.assertIn("SENSITIVE", str(row["claim_text"]))
        self.assertEqual(row["support_status"], "unassessed")  # structural kept
        # The LIVE packet is untouched.
        live = next(l for l in pkt.evidence_lanes
                    if l.lane == "collect_provenance")
        self.assertIn("alice@example.com",
                      live.result["provenance"]["rows"][0]["claim_text"])

    def test_lane_scrub_failure_fails_closed(self):
        pkt = self._filled_packet()
        with mock.patch.object(epersist, "_scrub_lane_result",
                               side_effect=RuntimeError("boom")):
            red = epersist.redact_for_durable(pkt, max_sensitivity="private")
        self.assertIsNone(red)   # caller withholds every durable write

    def test_decide_tier_unsupported_promotes_to_ledger(self):
        pkt = self._filled_packet(unsupported=1)
        self.assertEqual(epersist.decide_tier(pkt), epersist.TIER_LEDGER_LINE)

    def test_decide_tier_unassessed_stays_git_only(self):
        pkt = self._filled_packet(unsupported=0)
        self.assertEqual(epersist.decide_tier(pkt), epersist.TIER_GIT_ONLY)


if __name__ == "__main__":
    unittest.main()
