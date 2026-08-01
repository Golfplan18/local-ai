"""Tests for the automated supersession/cleaning system (2026-07-12).

Covers:
- News detector collection wiring: detection must open the knowledge
  collection through orchestrator.embedding.get_collection (logical →
  physical name resolution), not chromadb's raw get_collection — the raw
  path opens the empty pre-migration collection and silently reports 0.
- The date-gap one-directional strategy in engram cleaning detection.
- Model-judgment parsing + fail-open contract (supersession_judge).
- The judged sweep end-to-end with a mocked judge (mutations, logging,
  idempotent drain, per-sweep bound, Phase-C fold).
- tags-metadata backfill idempotency.
- Maintenance-scheduler gating for the two new tasks.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.expanduser("~/ora"))

from orchestrator.historical import run_engram_cleaning_detection as eng_det
from orchestrator.historical import run_engram_cleaning_resolver as eng_res
from orchestrator.historical import run_news_supersession_detection as news_det
from orchestrator.historical import run_news_supersession_resolver as news_res
from orchestrator.historical import supersession_judge as judge_mod
from orchestrator.tools import supersession_sweep as sweep_mod
from orchestrator.tools import backfill_tags_metadata as backfill_mod
from orchestrator import maintenance_scheduler as sched
from orchestrator import runtime_hygiene as hygiene


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _meta(slug: str, h1: str, date_created: str, tags=None, path: str = "") -> dict:
    """An engram-index entry shaped like build_engram_index's output."""
    return {
        "slug": slug,
        "h1": h1,
        "filename": f"{slug}.md",
        "path": path or f"/nonexistent/{slug}.md",
        "frontmatter": {"date created": date_created, "tags": tags or []},
    }


def _make_graph_db(path: str, edges: list[tuple[str, str, str, str]]):
    """edges: (source, target, type, confidence)."""
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE relationships ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " source TEXT NOT NULL, target TEXT NOT NULL,"
        " type TEXT NOT NULL,"
        " confidence TEXT NOT NULL DEFAULT 'medium',"
        " UNIQUE(source, target, type))"
    )
    cur.executemany(
        "INSERT OR IGNORE INTO relationships (source, target, type, confidence) "
        "VALUES (?, ?, ?, ?)", edges)
    conn.commit()
    conn.close()


def _write_engram(dirpath: str, slug: str, h1: str, date_created: str,
                  tags=("atomic", "fact")) -> str:
    tag_lines = "".join(f"  - {t}\n" for t in tags)
    path = os.path.join(dirpath, f"{slug}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "---\n"
            "nexus:\n"
            "type: engram\n"
            "tags:\n"
            f"{tag_lines}"
            f"date created: {date_created}\n"
            f"date modified: {date_created}\n"
            "---\n"
            f"\n# {h1}\n\nBody of {slug}.\n"
        )
    return path


# ---------------------------------------------------------------------------
# News detector collection wiring
# ---------------------------------------------------------------------------


class TestDurableLogLocations(unittest.TestCase):
    def test_defaults_follow_project_ownership(self):
        news_suffix = os.path.join(
            "Projects", "MSI", "Working — News Supersession Log.md")
        news_queue_suffix = os.path.join(
            "Projects", "MSI", "Working — News Supersession Queue.md")
        engram_suffix = os.path.join(
            "Projects", "Ora", "Working — Engram Cleaning Log.md")
        engram_queue_suffix = os.path.join(
            "Projects", "Ora", "Working — Engram Cleaning Queue.md")
        hypocrisy_suffix = os.path.join(
            "Projects", "Ora", "Working — Engram Cleaning Hypocrisy Review.md")

        self.assertTrue(news_det.LOG_FILE.endswith(news_suffix))
        self.assertTrue(news_res.LOG_FILE.endswith(news_suffix))
        self.assertTrue(news_det.QUEUE_FILE.endswith(news_queue_suffix))
        self.assertTrue(news_res.QUEUE_FILE.endswith(news_queue_suffix))
        self.assertTrue(eng_det.LOG_FILE.endswith(engram_suffix))
        self.assertTrue(eng_res.LOG_FILE.endswith(engram_suffix))
        self.assertTrue(eng_det.QUEUE_FILE.endswith(engram_queue_suffix))
        self.assertTrue(eng_res.QUEUE_FILE.endswith(engram_queue_suffix))
        self.assertTrue(eng_res.HYPOCRISY_FILE.endswith(hypocrisy_suffix))
        self.assertIn(
            "nexus:\n  - main-street-independent\n",
            sweep_mod._news_log_header(),
        )


class TestNewsDetectorCollectionWiring(unittest.TestCase):
    def test_detect_opens_collection_via_embedding_helper(self):
        """detect_topic_cluster must resolve the logical collection name
        through orchestrator.embedding.get_collection."""
        sentinel_client = object()
        fake_chromadb = types.SimpleNamespace(
            PersistentClient=lambda path: sentinel_client)

        calls = []

        def fake_get_collection(client, name):
            calls.append((client, name))
            return object()

        import orchestrator.embedding as embedding
        with mock.patch.dict(sys.modules, {"chromadb": fake_chromadb}), \
                mock.patch.object(embedding, "get_collection",
                                  fake_get_collection):
            out = news_det.detect_topic_cluster(
                {}, similarity_threshold=0.8, limit=5)

        self.assertEqual(out, [])
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0][0], sentinel_client)
        self.assertEqual(calls[0][1], "knowledge")

    def test_chromadb_import_error_raises_not_sys_exit(self):
        """A missing chromadb dependency must raise a catchable exception,
        not call sys.exit — SystemExit is a BaseException that would
        escape task_news_supersession's `except Exception` and abort the
        entire maintenance_scheduler.sweep() pass, not just this task.
        (Adversarial review finding, 2026-07-12.)"""
        with mock.patch.dict(sys.modules, {"chromadb": None}):
            with self.assertRaises(RuntimeError):
                news_det.detect_topic_cluster({}, similarity_threshold=0.8, limit=5)

    def test_scan_bounded_by_oversample_factor(self):
        """detect_topic_cluster must stop scanning once it has collected
        limit * CANDIDATE_OVERSAMPLE_FACTOR candidates, not walk the full
        Resources/ corpus every run. (Adversarial review finding: the
        collection-wiring fix reactivates a previously-dormant unbounded
        per-resource ChromaDB scan.)"""
        by_path = {}
        for i in range(20):
            slug = f"2026-01-{i+1:02d}_example-topic-{i}"
            by_path[f"/vault/Resources/{slug}.md"] = {
                "path": f"/vault/Resources/{slug}.md",
                "slug": slug,
                "filename": f"{slug}.md",
                "h1": f"Example Topic {i}",
                "tag_type": "news",
                "tags": ["news"],
                "date_created": f"2026-01-{i+1:02d}",
            }
        paths_in_order = list(by_path.keys())

        get_calls = []

        class FakeCol:
            def get(self, ids=None, where=None, include=None):
                # get_document_embedding first resolves physical records by
                # logical path metadata, then fetches those records' vectors.
                if where is not None:
                    path = where["path"]
                    get_calls.append(path)
                    return {"ids": [path]}
                return {
                    "ids": list(ids or []),
                    "embeddings": [[0.1, 0.2] for _ in (ids or [])],
                }

            def query(self, query_embeddings, n_results, include=None):
                if include != ["distances", "metadatas"]:
                    raise AssertionError(f"unexpected query include: {include}")
                # Each resource's sole neighbor is the NEXT resource in
                # iteration order — same tag_type, different date, distinct
                # entities ("Example"/"Topic" overlap) — every resource
                # yields exactly one real candidate.
                idx = paths_in_order.index(get_calls[-1])
                if idx + 1 >= len(paths_in_order):
                    return {"distances": [[]], "ids": [[]]}
                neighbor = paths_in_order[idx + 1]
                return {
                    "distances": [[0.1]],
                    "ids": [[neighbor]],
                }

        sentinel_client = object()
        fake_chromadb = types.SimpleNamespace(
            PersistentClient=lambda path: sentinel_client)

        import orchestrator.embedding as embedding
        with mock.patch.dict(sys.modules, {"chromadb": fake_chromadb}), \
                mock.patch.object(embedding, "get_collection",
                                  lambda client, name: FakeCol()), \
                mock.patch.object(news_det, "CANDIDATE_OVERSAMPLE_FACTOR", 2):
            out = news_det.detect_topic_cluster(
                by_path, similarity_threshold=0.05, limit=3)

        # threshold = limit(3) * factor(2) = 6 candidates before stopping;
        # one candidate per scanned resource → exactly 6 resources scanned.
        self.assertEqual(len(get_calls), 6)
        self.assertLessEqual(len(out), 3)


# ---------------------------------------------------------------------------
# Date-gap strategy
# ---------------------------------------------------------------------------


class TestDateGapStrategy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "graph.db")
        self._orig_db = eng_det.GRAPH_DB
        eng_det.GRAPH_DB = self.db

    def tearDown(self):
        eng_det.GRAPH_DB = self._orig_db
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_one_directional_medium_edge_with_gap_surfaces(self):
        a = _meta("2024-12-23_searle-chinese-room", "Searle's Chinese Room holds",
                  "2024-12-23")
        b = _meta("2025-09-19_llms-disprove-searle", "LLMs disprove the claim",
                  "2025-09-19")
        by_slug = {m["slug"]: m for m in (a, b)}
        by_h1 = {m["h1"]: m for m in (a, b)}
        _make_graph_db(self.db, [
            (a["slug"], b["slug"], "contradicts", "medium"),
        ])
        pairs = eng_det.detect_date_gap(by_slug, by_h1, limit=10)
        self.assertEqual(len(pairs), 1)
        newer, older = pairs[0]
        self.assertEqual(newer["slug"], b["slug"])   # newer first
        self.assertEqual(older["slug"], a["slug"])

    def test_small_gap_filtered(self):
        a = _meta("2026-01-01_x", "X is true", "2026-01-01")
        b = _meta("2026-01-15_not-x", "X is not true", "2026-01-15")
        by_slug = {m["slug"]: m for m in (a, b)}
        by_h1 = {m["h1"]: m for m in (a, b)}
        _make_graph_db(self.db, [
            (a["slug"], b["slug"], "contradicts", "high"),
        ])
        pairs = eng_det.detect_date_gap(by_slug, by_h1, limit=10,
                                        min_gap_days=90)
        self.assertEqual(pairs, [])

    def test_archived_side_filtered(self):
        a = _meta("2024-01-01_a", "A", "2024-01-01", tags=["archived"])
        b = _meta("2025-01-01_b", "B", "2025-01-01")
        by_slug = {m["slug"]: m for m in (a, b)}
        by_h1 = {m["h1"]: m for m in (a, b)}
        _make_graph_db(self.db, [
            (a["slug"], b["slug"], "contradicts", "high"),
        ])
        self.assertEqual(
            eng_det.detect_date_gap(by_slug, by_h1, limit=10), [])

    def test_resolved_set_filtered(self):
        a = _meta("2024-01-01_a", "A", "2024-01-01")
        b = _meta("2025-01-01_b", "B", "2025-01-01")
        by_slug = {m["slug"]: m for m in (a, b)}
        by_h1 = {m["h1"]: m for m in (a, b)}
        _make_graph_db(self.db, [
            (a["slug"], b["slug"], "contradicts", "high"),
        ])
        resolved = {tuple(sorted([a["slug"], b["slug"]]))}
        self.assertEqual(
            eng_det.detect_date_gap(by_slug, by_h1, limit=10,
                                    resolved_set=resolved), [])

    def test_claim_keyed_target_resolves_via_h1(self):
        """Unresolved claim targets stay verbatim in the DB; the strategy
        must fall back to H1 lookup for those."""
        a = _meta("2024-01-01_a", "Claim A", "2024-01-01")
        b = _meta("2025-06-01_b", "Claim B stays verbatim", "2025-06-01")
        by_slug = {m["slug"]: m for m in (a, b)}
        by_h1 = {m["h1"]: m for m in (a, b)}
        _make_graph_db(self.db, [
            (a["slug"], b["h1"], "contradicts", "high"),
        ])
        pairs = eng_det.detect_date_gap(by_slug, by_h1, limit=10)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0][0]["slug"], b["slug"])

    def test_sorted_by_gap_desc_and_limit(self):
        a1 = _meta("2020-01-01_old", "Old", "2020-01-01")
        b1 = _meta("2025-01-01_new", "New", "2025-01-01")
        a2 = _meta("2024-06-01_older", "Older", "2024-06-01")
        b2 = _meta("2025-01-02_newer", "Newer", "2025-01-02")
        metas = (a1, b1, a2, b2)
        by_slug = {m["slug"]: m for m in metas}
        by_h1 = {m["h1"]: m for m in metas}
        _make_graph_db(self.db, [
            (a1["slug"], b1["slug"], "contradicts", "high"),
            (a2["slug"], b2["slug"], "contradicts", "high"),
        ])
        pairs = eng_det.detect_date_gap(by_slug, by_h1, limit=10)
        self.assertEqual(len(pairs), 2)
        # 5-year gap sorts ahead of ~7-month gap
        self.assertEqual(pairs[0][0]["slug"], b1["slug"])
        pairs = eng_det.detect_date_gap(by_slug, by_h1, limit=1)
        self.assertEqual(len(pairs), 1)

    def test_engram_date_fallback_to_slug_prefix(self):
        m = _meta("2024-03-05_thing", "Thing", None)
        m["frontmatter"] = {}
        self.assertEqual(eng_det.engram_date(m), "2024-03-05")


# ---------------------------------------------------------------------------
# Judge parsing + fail-open
# ---------------------------------------------------------------------------


class TestJudgeParsing(unittest.TestCase):
    def test_clean_supersede(self):
        d, r = judge_mod.parse_verdict(
            "VERDICT: SUPERSEDE\nREASON: newer note reverses the older claim")
        self.assertEqual(d, "supersede")
        self.assertEqual(r, "newer note reverses the older claim")

    def test_clean_skip_lowercase(self):
        d, r = judge_mod.parse_verdict("verdict: skip\nreason: contrastive pair")
        self.assertEqual(d, "skip")
        self.assertEqual(r, "contrastive pair")

    def test_verdict_embedded_in_prose(self):
        d, _ = judge_mod.parse_verdict(
            "Looking at both notes...\nVERDICT: SKIP\n"
            "REASON: different aspects\nHope that helps!")
        self.assertEqual(d, "skip")

    def test_missing_verdict_is_error(self):
        d, r = judge_mod.parse_verdict("The newer note supersedes the older.")
        self.assertEqual(d, "error")
        self.assertIn("no VERDICT", r)

    def test_empty_is_error(self):
        d, _ = judge_mod.parse_verdict("")
        self.assertEqual(d, "error")


class TestJudgeFailOpen(unittest.TestCase):
    def _judge(self):
        return judge_mod.judge_pair(
            "New", "2025-09-19", "new text",
            "Old", "2024-12-23", "old text", kind="engram")

    def test_model_error_returns_error_decision(self):
        from orchestrator.model_dispatch import ModelDispatchError

        def boom(*a, **k):
            raise ModelDispatchError("model_error", "model exploded")

        import orchestrator.model_dispatch as md
        with mock.patch.object(md, "invoke_chat", boom):
            res = self._judge()
        self.assertEqual(res.decision, "error")
        self.assertIn("model error", res.reason)

    def test_slot_ladder_falls_back_to_sidebar(self):
        from orchestrator.model_dispatch import ModelDispatchError
        seen_slots = []

        def picky(system, user, *, slot, context):
            seen_slots.append(slot)
            if slot == "evaluator":
                raise ModelDispatchError("no_slot_endpoint", "none", slot=slot)
            return "VERDICT: SKIP\nREASON: fallback worked"

        import orchestrator.model_dispatch as md
        with mock.patch.object(md, "invoke_chat", picky):
            res = self._judge()
        self.assertEqual(seen_slots, ["evaluator", "sidebar"])
        self.assertEqual(res.decision, "skip")
        self.assertEqual(res.slot, "sidebar")

    def test_unparseable_response_is_error(self):
        import orchestrator.model_dispatch as md
        with mock.patch.object(md, "invoke_chat",
                               lambda *a, **k: "I think probably yes?"):
            res = self._judge()
        self.assertEqual(res.decision, "error")

    def test_good_response(self):
        import orchestrator.model_dispatch as md
        with mock.patch.object(
                md, "invoke_chat",
                lambda *a, **k: "VERDICT: SUPERSEDE\nREASON: clear reversal"):
            res = self._judge()
        self.assertEqual(res.decision, "supersede")
        self.assertEqual(res.reason, "clear reversal")
        self.assertEqual(res.slot, "evaluator")


# ---------------------------------------------------------------------------
# Engram sweep end-to-end (mocked judge)
# ---------------------------------------------------------------------------


class TestNewsSweepApplyFailure(unittest.TestCase):
    """Mirrors TestEngramSweep's apply-failure coverage for the news task's
    own separate code path (task_news_supersession uses a different
    resolver — news_res.apply_supersession — and a different log)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.log = os.path.join(self.tmp, "Working — News Supersession Log.md")
        self._saved_log = news_res.LOG_FILE
        news_res.LOG_FILE = self.log
        self.data = os.path.join(self.tmp, "data")
        os.makedirs(self.data)
        self.data_patch = mock.patch.object(
            hygiene._rp, "DATA_DIR_STR", self.data,
        )
        self.data_patch.start()
        self._campaign = 0

        self.cand = {
            "newer": {"slug": "2026-02-01_newer", "h1": "Newer story",
                      "date_created": "2026-02-01", "path": "/x/newer.md",
                      "tag_type": "news"},
            "older": {"slug": "2026-01-01_older", "h1": "Older story",
                      "date_created": "2026-01-01", "path": "/x/older.md",
                      "tag_type": "news"},
            "similarity": 0.9, "entity_overlap": 2, "date_gap_days": 31,
        }

    def tearDown(self):
        self.data_patch.stop()
        news_res.LOG_FILE = self._saved_log
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, apply_result, judge_decision="supersede"):
        jr = judge_mod.JudgeResult(judge_decision, "reason", slot="evaluator")
        with mock.patch.object(news_det, "build_resources_index",
                               lambda: {}), \
                mock.patch.object(news_det, "_load_resolved_pair_set",
                                  lambda: set()), \
                mock.patch.object(news_det, "detect_topic_cluster",
                                  lambda *a, **k: [self.cand]), \
                mock.patch.object(judge_mod, "judge_pair", lambda *a, **k: jr), \
                mock.patch.object(news_res, "apply_supersession",
                                  lambda **k: dict(apply_result)), \
                mock.patch.object(news_res, "refresh_chromadb",
                                  lambda slugs: None):
            self._campaign += 1
            return sweep_mod.task_news_supersession(
                campaign_id=f"test-news-{self._campaign}",
            )

    def test_apply_failure_fails_open_not_logged_as_resolved(self):
        result = self._run({"mutated_files": [], "errors": ["survivor not found"]})
        self.assertEqual(result.stats["superseded"], 0)
        self.assertEqual(result.stats["errors"], 1)
        self.assertFalse(os.path.exists(self.log))

    def test_apply_success_logs_and_counts_superseded(self):
        result = self._run({"mutated_files": ["a.md", "b.md"], "errors": []})
        self.assertEqual(result.stats["superseded"], 1)
        self.assertEqual(result.stats["errors"], 0)
        with open(self.log, encoding="utf-8") as f:
            self.assertIn("changed-mind:source-supersedes-target (auto)",
                          f.read())


class TestEngramSweep(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.engrams = os.path.join(self.tmp, "Engrams")
        os.makedirs(self.engrams)
        self.db = os.path.join(self.tmp, "graph.db")
        self.log = os.path.join(self.tmp, "Working — Engram Cleaning Log.md")
        self.data = os.path.join(self.tmp, "data")
        os.makedirs(self.data)
        self.data_patch = mock.patch.object(
            hygiene._rp, "DATA_DIR_STR", self.data,
        )
        self.data_patch.start()
        self._campaign = 0

        self._saved = {
            "det_dir": eng_det.ENGRAMS_DIR, "det_db": eng_det.GRAPH_DB,
            "det_log": eng_det.LOG_FILE,
            "res_dir": eng_res.ENGRAMS_DIR, "res_log": eng_res.LOG_FILE,
            "refresh": eng_res.refresh_chromadb,
            "max_pairs": sweep_mod.MAX_ENGRAM_PAIRS,
        }
        eng_det.ENGRAMS_DIR = self.engrams
        eng_det.GRAPH_DB = self.db
        eng_det.LOG_FILE = self.log
        eng_res.ENGRAMS_DIR = self.engrams
        eng_res.LOG_FILE = self.log
        self.refreshed: list[set] = []
        eng_res.refresh_chromadb = lambda slugs: self.refreshed.append(set(slugs))

        self.a_path = _write_engram(
            self.engrams, "2024-12-23_searle-holds",
            "Searle's Chinese Room argument holds", "2024-12-23")
        self.b_path = _write_engram(
            self.engrams, "2025-09-19_searle-reversed",
            "LLMs empirically disprove the Chinese Room claim", "2025-09-19")
        _make_graph_db(self.db, [
            ("2024-12-23_searle-holds", "2025-09-19_searle-reversed",
             "contradicts", "medium"),
        ])

    def tearDown(self):
        self.data_patch.stop()
        eng_det.ENGRAMS_DIR = self._saved["det_dir"]
        eng_det.GRAPH_DB = self._saved["det_db"]
        eng_det.LOG_FILE = self._saved["det_log"]
        eng_res.ENGRAMS_DIR = self._saved["res_dir"]
        eng_res.LOG_FILE = self._saved["res_log"]
        eng_res.refresh_chromadb = self._saved["refresh"]
        sweep_mod.MAX_ENGRAM_PAIRS = self._saved["max_pairs"]
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_with_judge(self, decision, reason="test reason"):
        jr = judge_mod.JudgeResult(decision, reason, slot="evaluator")
        with mock.patch.object(judge_mod, "judge_pair",
                               lambda *a, **k: jr):
            self._campaign += 1
            return sweep_mod.task_engram_cleaning(
                campaign_id=f"test-engram-{self._campaign}",
            )

    def test_supersede_applies_mutations_and_logs(self):
        result = self._run_with_judge("supersede")
        self.assertTrue(result.success)
        self.assertEqual(result.stats["superseded"], 1)

        with open(self.b_path, encoding="utf-8") as f:
            survivor = f.read()
        self.assertIn("type: supersedes", survivor)
        self.assertIn("Chinese Room argument holds", survivor)

        with open(self.a_path, encoding="utf-8") as f:
            archived = f.read()
        self.assertIn("- archived", archived)

        with open(self.log, encoding="utf-8") as f:
            log = f.read()
        self.assertIn("changed-mind:source-supersedes-target (auto)", log)
        self.assertIn("**Judge:** model (evaluator) — test reason", log)
        self.assertIn("[[2025-09-19_searle-reversed]]", log)

        self.assertEqual(self.refreshed,
                         [{"2024-12-23_searle-holds",
                           "2025-09-19_searle-reversed"}])

    def test_judged_pairs_do_not_resurface(self):
        self._run_with_judge("supersede")
        result2 = self._run_with_judge("supersede")
        self.assertEqual(result2.stats["judged"], 0)
        self.assertEqual(result2.stats["date_gap_candidates"], 0)

    def test_skip_logs_without_mutation(self):
        result = self._run_with_judge("skip")
        self.assertEqual(result.stats["skipped"], 1)
        with open(self.a_path, encoding="utf-8") as f:
            self.assertNotIn("- archived", f.read())
        with open(self.log, encoding="utf-8") as f:
            self.assertIn("skip (auto)", f.read())
        # and the skip is durable — pair does not resurface
        result2 = self._run_with_judge("skip")
        self.assertEqual(result2.stats["judged"], 0)

    def test_error_fails_open_and_resurfaces(self):
        result = self._run_with_judge("error", "model down")
        self.assertEqual(result.stats["errors"], 1)
        self.assertEqual(result.stats["superseded"], 0)
        self.assertFalse(result.success)
        self.assertTrue(any("model down" in a for a in result.alerts))
        self.assertFalse(os.path.exists(self.log))  # NOT logged as resolved
        # pair resurfaces next sweep
        result2 = self._run_with_judge("skip")
        self.assertEqual(result2.stats["judged"], 1)

    def test_per_sweep_bound(self):
        _write_engram(self.engrams, "2020-01-01_c", "Claim C", "2020-01-01")
        _write_engram(self.engrams, "2025-01-01_d", "Claim D", "2025-01-01")
        _make_graph_db(self.db + ".ignore", [])  # no-op; keep helper honest
        conn = sqlite3.connect(self.db)
        conn.execute(
            "INSERT INTO relationships (source, target, type, confidence) "
            "VALUES ('2020-01-01_c', '2025-01-01_d', 'contradicts', 'high')")
        conn.commit()
        conn.close()

        sweep_mod.MAX_ENGRAM_PAIRS = 1
        result = self._run_with_judge("skip")
        self.assertEqual(result.stats["judged"], 1)
        self.assertEqual(result.stats["remaining"], 1)

    def test_phase_c_fold_tops_up(self):
        conn = sqlite3.connect(self.db)
        conn.execute("DELETE FROM relationships")
        conn.execute(
            "INSERT INTO relationships (source, target, type, confidence) "
            "VALUES ('2025-09-19_searle-reversed', '2024-12-23_searle-holds', "
            "'supersedes', 'high')")
        conn.commit()
        conn.close()

        result = self._run_with_judge("supersede")
        self.assertEqual(result.stats["phase_c_candidates"], 1)
        self.assertEqual(result.stats["superseded"], 1)
        with open(self.a_path, encoding="utf-8") as f:
            self.assertIn("- archived", f.read())
        # consumed: next sweep sees the target archived → no candidates
        result2 = self._run_with_judge("supersede")
        self.assertEqual(result2.stats["phase_c_candidates"], 0)

    def test_apply_failure_fails_open_not_logged_as_resolved(self):
        """A judge SUPERSEDE verdict whose apply step can't find the
        survivor/older file (returns errors without raising — e.g. the
        file vanished between index-build and judgment) must NOT be
        logged as resolved. Logging it would permanently hide a pair
        that was never actually mutated and discard the real verdict.
        (Adversarial review finding, 2026-07-12 — reproduced against the
        exact {mutated_files: [], errors: [...]} shape apply_changed_mind
        returns on a missing file.)"""
        jr = judge_mod.JudgeResult("supersede", "clear reversal", slot="evaluator")
        broken_apply = {"mutated_files": [], "errors": ["survivor not found: x"]}
        with mock.patch.object(judge_mod, "judge_pair", lambda *a, **k: jr), \
                mock.patch.object(eng_res, "apply_changed_mind",
                                  lambda **k: dict(broken_apply)):
            self._campaign += 1
            result = sweep_mod.task_engram_cleaning(
                campaign_id=f"test-engram-{self._campaign}",
            )

        self.assertEqual(result.stats["superseded"], 0)
        self.assertEqual(result.stats["errors"], 1)
        self.assertFalse(os.path.exists(self.log),
                         "apply failure must not write a resolved log entry")
        with open(self.a_path, encoding="utf-8") as f:
            self.assertNotIn("- archived", f.read())

        # The pair must resurface next sweep (nothing was durably resolved).
        with mock.patch.object(judge_mod, "judge_pair", lambda *a, **k: jr), \
                mock.patch.object(eng_res, "apply_changed_mind",
                                  lambda **k: dict(broken_apply)):
            self._campaign += 1
            result2 = sweep_mod.task_engram_cleaning(
                campaign_id=f"test-engram-{self._campaign}",
            )
        self.assertEqual(result2.stats["date_gap_candidates"], 1)

    def test_log_write_failure_rolls_back_subject_mutation(self):
        """An audit-write failure restores the campaign transaction."""
        jr = judge_mod.JudgeResult("supersede", "clear reversal", slot="evaluator")
        with mock.patch.object(judge_mod, "judge_pair", lambda *a, **k: jr), \
                mock.patch.object(sweep_mod, "_append_judged_log",
                                  side_effect=OSError("disk full")):
            self._campaign += 1
            result = sweep_mod.task_engram_cleaning(
                campaign_id=f"test-engram-{self._campaign}",
            )

        self.assertFalse(result.success)
        self.assertEqual(result.stats["errors"], 1)
        with open(self.b_path, encoding="utf-8") as f:
            self.assertNotIn("type: supersedes", f.read())


# ---------------------------------------------------------------------------
# Backfill idempotency
# ---------------------------------------------------------------------------


class FakeCollection:
    def __init__(self, records: dict[str, dict], *, fail_batch_index=None):
        # records: id -> metadata
        self.records = dict(records)
        self.update_calls = 0
        self._fail_batch_index = fail_batch_index

    def count(self):
        return len(self.records)

    def get(self, ids=None, limit=None, offset=None, include=None):
        if ids is not None:
            sel = [(i, self.records[i]) for i in ids if i in self.records]
        else:
            items = sorted(self.records.items())
            offset = offset or 0
            sel = items[offset:offset + (limit or len(items))]
        out = {"ids": [i for i, _ in sel]}
        if include and "metadatas" in include:
            out["metadatas"] = [dict(m) for _, m in sel]
        return out

    def update(self, ids, metadatas):
        if self._fail_batch_index is not None and \
                self.update_calls == self._fail_batch_index:
            self.update_calls += 1
            raise RuntimeError("simulated chromadb update failure")
        self.update_calls += 1
        for i, m in zip(ids, metadatas):
            self.records[i] = dict(m)


class TestBackfillIdempotency(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p1 = _write_engram(self.tmp, "2024-01-01_a", "Claim A",
                                "2024-01-01", tags=("atomic", "superseded"))
        self.p2 = _write_engram(self.tmp, "2024-01-02_b", "Claim B",
                                "2024-01-02", tags=("atomic",))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fresh_col(self):
        # Live-collection shape: tag_* booleans present, no `tags` key.
        return FakeCollection({
            self.p1: {"path": self.p1, "type": "engram",
                      "tag_archived": False},
            self.p2: {"path": self.p2, "type": "engram",
                      "tag_archived": False},
            "/gone/file.md": {"path": "/gone/file.md", "type": "engram"},
        })

    def test_backfill_adds_tags_and_is_idempotent(self):
        col = self._fresh_col()
        stats = backfill_mod.backfill_collection(col, batch_size=2,
                                                 log=lambda *a, **k: None)
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["updated"], 2)
        self.assertEqual(stats["missing_file"], 1)
        self.assertEqual(col.records[self.p1]["tags"],
                         ["atomic", "superseded"])
        self.assertEqual(col.records[self.p2]["tags"], ["atomic"])
        # pre-existing keys survive the merge
        self.assertIn("tag_archived", col.records[self.p1])

        stats2 = backfill_mod.backfill_collection(col, batch_size=2,
                                                  log=lambda *a, **k: None)
        self.assertEqual(stats2["updated"], 0)
        self.assertEqual(stats2["unchanged"], 2)

    def test_dry_run_writes_nothing(self):
        col = self._fresh_col()
        stats = backfill_mod.backfill_collection(col, batch_size=2,
                                                 dry_run=True,
                                                 log=lambda *a, **k: None)
        self.assertEqual(stats["updated"], 2)
        self.assertEqual(col.update_calls, 0)
        self.assertNotIn("tags", col.records[self.p1])

    def test_indexer_still_composes_tags_going_forward(self):
        """Regression guard: new indexing must write the `tags` list."""
        from orchestrator.tools.knowledge_index import (
            _parse_frontmatter, _compose_chroma_metadata)
        with open(self.p1, encoding="utf-8") as f:
            meta, _ = _parse_frontmatter(f.read())
        composed = _compose_chroma_metadata(self.p1, meta)
        self.assertEqual(composed["tags"], ["atomic", "superseded"])

    def test_batch_update_failure_does_not_abort_whole_run(self):
        """One bad batch's col.update() must not kill the entire 150k-record
        run with no summary — matches the existing resolvers' refresh_
        chromadb pattern of wrapping collection.update in try/except.
        (Adversarial review finding, minor.)"""
        p3 = _write_engram(self.tmp, "2024-01-03_c", "Claim C", "2024-01-03",
                           tags=("atomic",))
        col = FakeCollection({
            self.p1: {"path": self.p1, "type": "engram"},
            self.p2: {"path": self.p2, "type": "engram"},
            p3: {"path": p3, "type": "engram"},
        }, fail_batch_index=0)  # first batch's update() call raises

        stats = backfill_mod.backfill_collection(
            col, batch_size=1, log=lambda *a, **k: None)

        self.assertEqual(stats["batch_errors"], 1)
        # batch 1 (p1, alphabetically first) failed and was not updated;
        # the run continued and updated the rest.
        self.assertNotIn("tags", col.records[self.p1])
        self.assertIn("tags", col.records[self.p2])
        self.assertIn("tags", col.records[p3])


class TestBackfillMSIOverridePreservation(unittest.TestCase):
    """Adversarial review finding (CRITICAL, reproduced against the live
    MSI News mirror): project tools index into the shared knowledge
    collection via meta_overrides (type/nexus/tags injected at index time,
    not present in the source file's own frontmatter). Recomposing full
    metadata from bare frontmatter for such a record wipes type/nexus and
    flips every tag_<name> boolean to False, breaking RAG exclude_tags
    scoping and provenance-weight lookup for that project's records,
    permanently (those records are never re-touched after initial index).
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # An MSI-style source file: real content, but NO Ora-schema tags/
        # type/nexus fields in its own frontmatter (those come from
        # meta_overrides at index time only).
        self.msi_path = os.path.join(self.tmp, "msi-article.md")
        with open(self.msi_path, "w", encoding="utf-8") as f:
            f.write(
                "---\n"
                "headline: Some MSI Article\n"
                "publish_date: 2026-06-01\n"
                "---\n\n# Some MSI Article\n\nBody.\n"
            )
        # A genuine vault engram WITH real tags in its own frontmatter.
        self.vault_path = _write_engram(
            self.tmp, "2024-01-01_a", "Claim A", "2024-01-01",
            tags=("atomic", "superseded"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_override_indexed_record_is_skipped_not_corrupted(self):
        col = FakeCollection({
            self.msi_path: {
                "path": self.msi_path, "type": "resource",
                "nexus": "main-street-independent",
                "tag_msi-news": True, "tag_archived": False,
            },
        })
        stats = backfill_mod.backfill_collection(
            col, batch_size=10, log=lambda *a, **k: None)

        self.assertEqual(stats["skipped_override_indexed"], 1)
        self.assertEqual(stats["updated"], 0)
        # Nothing about the existing record changed — type/nexus/tag_msi-news
        # survive untouched.
        rec = col.records[self.msi_path]
        self.assertEqual(rec["type"], "resource")
        self.assertEqual(rec["nexus"], "main-street-independent")
        self.assertTrue(rec["tag_msi-news"])
        self.assertNotIn("tags", rec)

    def test_normal_record_updates_tags_only_not_type_or_nexus(self):
        """Even for a record whose tags DO recompute, only tags/tag_* keys
        may change — type/nexus/other fields must never be touched by
        this backfill (its job is narrowly tags, not a full recompose)."""
        col = FakeCollection({
            self.vault_path: {
                "path": self.vault_path, "type": "engram",
                "nexus": "some-custom-value-not-in-file",
                "tag_archived": False,
            },
        })
        stats = backfill_mod.backfill_collection(
            col, batch_size=10, log=lambda *a, **k: None)

        self.assertEqual(stats["updated"], 1)
        rec = col.records[self.vault_path]
        self.assertEqual(rec["tags"], ["atomic", "superseded"])
        # untouched, even though _compose_chroma_metadata would recompute
        # nexus to "" for this bare frontmatter (no nexus: field written)
        self.assertEqual(rec["nexus"], "some-custom-value-not-in-file")
        self.assertEqual(rec["type"], "engram")


# ---------------------------------------------------------------------------
# Scheduler gating
# ---------------------------------------------------------------------------


class TestSchedulerGating(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._env = os.environ.get("ORA_VAULT_PATH")
        os.environ["ORA_VAULT_PATH"] = self.tmp

    def tearDown(self):
        if self._env is None:
            os.environ.pop("ORA_VAULT_PATH", None)
        else:
            os.environ["ORA_VAULT_PATH"] = self._env
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_control_doc(self, block: str):
        with open(os.path.join(self.tmp, sched.CONTROL_DOC_NAME), "w",
                  encoding="utf-8") as f:
            f.write(f"---\nmaintenance:\n{block}---\n\n# Control\n")

    def test_event_tasks_are_exposed_and_default_off(self):
        config = sched.load_config()  # no control doc → defaults
        self.assertEqual(config["news_supersession"], "off")
        self.assertEqual(config["engram_cleaning"], "off")

    def test_off_is_the_escape_hatch(self):
        self._write_control_doc(
            "  news_supersession: off\n  engram_cleaning: off\n")
        config = sched.load_config()
        self.assertEqual(config["news_supersession"], "off")
        self.assertEqual(config["engram_cleaning"], "off")
        due = sched.due_tasks(config, state={})
        self.assertNotIn("news_supersession", due)
        self.assertNotIn("engram_cleaning", due)

    def test_clock_cadence_cannot_reenable_event_tasks(self):
        self._write_control_doc(
            "  news_supersession: daily\n  engram_cleaning: monthly\n")
        config = sched.load_config()
        due = sched.due_tasks(config, state={})
        self.assertEqual(config["news_supersession"], "off")
        self.assertEqual(config["engram_cleaning"], "off")
        self.assertNotIn("news_supersession", due)
        self.assertNotIn("engram_cleaning", due)

    def test_event_tasks_absent_from_clock_dispatch(self):
        self.assertNotIn("news_supersession", sched.TASK_FUNCTIONS)
        self.assertNotIn("engram_cleaning", sched.TASK_FUNCTIONS)


if __name__ == "__main__":
    unittest.main()
