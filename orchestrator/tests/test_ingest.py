"""Tests for the unified ingest pipeline (orchestrator.historical.ingest).

All three stage functions are mocked — these tests verify orchestration:
stage order, flag routing, backend propagation, worker capping, and
summary shape.
"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date
from unittest.mock import patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.historical import ingest  # noqa: E402
from orchestrator import runtime_paths as _rp  # noqa: E402
from orchestrator.historical import path2_cli, path2_orchestrator  # noqa: E402
from orchestrator.historical import phase3_extraction, phase5_atomic_extraction  # noqa: E402
from orchestrator.historical import privacy_tagging  # noqa: E402
from orchestrator.historical import phase_b_vault_extraction  # noqa: E402
from orchestrator.historical import phase_c_relationship_extraction  # noqa: E402
from orchestrator.historical import rebuild_atomic_dedup, repair_refusal_pairs  # noqa: E402
from orchestrator.historical import writer  # noqa: E402


def _mocks():
    return (
        patch.object(ingest, "run_batch",
                     return_value={"files_succeeded": 2}),
        patch.object(ingest, "run_chain_detection",
                     return_value={"sessions": 5, "chains": 1,
                                   "sessions_to_paths": {"s1": ["a.md"]}}),
        patch.object(ingest, "run_phase3",
                     return_value={"targets_written": 4}),
        patch.object(ingest, "run_chunk_emission",
                     return_value={"sessions_processed": 1}),
        patch.object(ingest, "run_phase5",
                     return_value={"pairs_processed": 3}),
    )


class TestRunIngest(unittest.TestCase):

    def test_historical_defaults_share_runtime_roots(self):
        self.assertEqual(path2_cli.DEFAULT_MANIFEST_PATH,
                         str(_rp.DATA_DIR / "path2-manifest.json"))
        self.assertEqual(path2_orchestrator.DEFAULT_CLEANED_PAIR_DIR,
                         str(_rp.historical_archive_dir()))
        self.assertEqual(path2_orchestrator.DEFAULT_CONVERSATIONS_DIR,
                         str(_rp.conversations_dir()))
        self.assertEqual(path2_orchestrator.DEFAULT_CHROMADB_PATH,
                         str(_rp.chromadb_dir()))
        self.assertEqual(phase3_extraction.DEFAULT_ARCHIVE_DIR,
                         str(_rp.historical_archive_dir()))
        self.assertEqual(phase3_extraction.DEFAULT_RESOURCES_ROOT,
                         str(_rp.vault_dir() / "Resources"))
        self.assertEqual(phase3_extraction.DEFAULT_MANIFEST_PATH,
                         str(_rp.DATA_DIR / "phase3-manifest.json"))
        self.assertEqual(phase5_atomic_extraction.DEFAULT_VAULT_ROOT,
                         str(_rp.vault_dir() / "Engrams" / "Historical Atomics"))
        self.assertEqual(rebuild_atomic_dedup.VAULT_ROOT,
                         str(_rp.vault_dir() / "Engrams"))
        self.assertEqual(rebuild_atomic_dedup.CHROMA_PATH,
                         str(_rp.chromadb_dir()))
        self.assertEqual(rebuild_atomic_dedup.COLLECTION, "atomics")
        self.assertEqual(
            phase5_atomic_extraction.DEFAULT_DEDUP_COLLECTION, "atomics",
        )
        self.assertEqual(repair_refusal_pairs.DEFAULT_REPORT_PATH,
                         str(_rp.DATA_DIR / "refusal-repair-report.json"))
        self.assertEqual(writer.DEFAULT_OUTPUT_DIR,
                         str(_rp.historical_archive_dir()))
        self.assertEqual(privacy_tagging.DEFAULT_VAULT_ROOT,
                         str(_rp.vault_dir()))
        self.assertEqual(privacy_tagging.DEFAULT_ARCHIVE_DIR,
                         str(_rp.historical_archive_dir()))
        self.assertEqual(phase_b_vault_extraction.DEFAULT_VAULT_ROOT_FLAT,
                         str(_rp.vault_dir() / "Engrams"))
        self.assertEqual(phase_c_relationship_extraction.DEFAULT_VAULT_ROOT,
                         str(_rp.vault_dir() / "Engrams"))
        self.assertEqual(phase_c_relationship_extraction.DEFAULT_CHROMADB_PATH,
                         str(_rp.chromadb_dir()))
        self.assertEqual(
            phase_c_relationship_extraction.DEFAULT_DEDUP_COLLECTION,
            "atomics",
        )

    def test_all_stages_run_in_order(self):
        m_batch, m_detect, m_p3, m_emit, m_p5 = _mocks()
        order = []
        with m_batch as b, m_detect as d, m_p3 as p3, m_emit as e, m_p5 as p:
            b.side_effect = lambda **kw: order.append("cleanup") or {"ok": 1}
            d.side_effect = lambda **kw: order.append("detect") or {
                "sessions": 1, "chains": 0, "sessions_to_paths": {}}
            p3.side_effect = lambda **kw: order.append("phase3") or {}
            e.side_effect = lambda *a, **kw: order.append("emit") or {}
            p.side_effect = lambda **kw: order.append("phase5") or {}
            summary = ingest.run_ingest(progress=False)
        # Chain detection precedes phase3 so source notes get chain
        # enrichment; extraction precedes chunks per the original
        # historical phase ordering.
        self.assertEqual(order, ["cleanup", "detect", "phase3", "emit",
                                 "phase5"])
        self.assertIn("cleanup", summary)
        self.assertIn("extraction", summary)
        self.assertIn("chunks", summary)
        self.assertIn("engrams", summary)
        self.assertIn("duration_secs", summary)

    def test_no_extraction_skips_phase3(self):
        m_batch, m_detect, m_p3, m_emit, m_p5 = _mocks()
        with m_batch, m_detect as d, m_p3 as p3, m_emit as e, m_p5:
            summary = ingest.run_ingest(extraction=False, progress=False)
        p3.assert_not_called()
        # Chunks still need chain detection + emission.
        d.assert_called_once()
        e.assert_called_once()
        self.assertEqual(summary["extraction"], {"skipped": True})

    def test_extraction_reads_cleaned_archive(self):
        m_batch, m_detect, m_p3, m_emit, m_p5 = _mocks()
        with m_batch, m_detect, m_p3 as p3, m_emit, m_p5:
            ingest.run_ingest(output_dir="/tmp/archive", progress=False)
        self.assertEqual(p3.call_args[1]["archive_dir"], "/tmp/archive")

    def test_extraction_only_still_runs_chain_detection(self):
        # Chain enrichment on source notes needs a fresh chain index
        # even when chunk emission is disabled.
        m_batch, m_detect, m_p3, m_emit, m_p5 = _mocks()
        with m_batch, m_detect as d, m_p3 as p3, m_emit as e, m_p5:
            summary = ingest.run_ingest(chunks=False, engrams=False,
                                        progress=False)
        d.assert_called_once()
        p3.assert_called_once()
        e.assert_not_called()
        self.assertEqual(summary["chunks"], {"skipped": True})

    def test_no_chunks_no_extraction_skips_detection(self):
        m_batch, m_detect, m_p3, m_emit, m_p5 = _mocks()
        with m_batch, m_detect as d, m_p3, m_emit as e, m_p5:
            summary = ingest.run_ingest(extraction=False, chunks=False,
                                        progress=False)
        d.assert_not_called()
        e.assert_not_called()
        self.assertEqual(summary["chunks"], {"skipped": True})

    def test_no_engrams_skips_final_stage(self):
        m_batch, m_detect, m_p3, m_emit, m_p5 = _mocks()
        with m_batch, m_detect, m_p3, m_emit, m_p5 as p:
            summary = ingest.run_ingest(engrams=False, progress=False)
        p.assert_not_called()
        self.assertEqual(summary["engrams"], {"skipped": True})

    def test_backend_propagates_to_backend_aware_stages(self):
        m_batch, m_detect, m_p3, m_emit, m_p5 = _mocks()
        with m_batch as b, m_detect, m_p3 as p3, m_emit, m_p5 as p:
            ingest.run_ingest(backend="claude-cli", progress=False)
        self.assertEqual(b.call_args[1]["backend"], "claude-cli")
        self.assertEqual(p3.call_args[1]["backend"], "claude-cli")
        self.assertEqual(p.call_args[1]["backend"], "claude-cli")

    def test_api_backend_is_default_for_extraction(self):
        m_batch, m_detect, m_p3, m_emit, m_p5 = _mocks()
        with m_batch, m_detect, m_p3 as p3, m_emit, m_p5:
            ingest.run_ingest(progress=False)
        self.assertEqual(p3.call_args[1]["backend"], "api")

    def test_cli_backend_caps_phase5_workers(self):
        m_batch, m_detect, m_p3, m_emit, m_p5 = _mocks()
        with m_batch, m_detect, m_p3, m_emit, m_p5 as p:
            ingest.run_ingest(backend="claude-cli", max_workers=8,
                              progress=False)
        self.assertLessEqual(p.call_args[1]["max_workers"], 3)

    def test_cli_backend_caps_extraction_workers(self):
        m_batch, m_detect, m_p3, m_emit, m_p5 = _mocks()
        with m_batch, m_detect, m_p3 as p3, m_emit, m_p5:
            ingest.run_ingest(backend="claude-cli", max_workers=8,
                              progress=False)
        self.assertLessEqual(p3.call_args[1]["max_workers"], 3)

    def test_api_backend_does_not_cap_extraction_workers(self):
        m_batch, m_detect, m_p3, m_emit, m_p5 = _mocks()
        with m_batch, m_detect, m_p3 as p3, m_emit, m_p5:
            ingest.run_ingest(backend="api", max_workers=8, progress=False)
        self.assertEqual(p3.call_args[1]["max_workers"], 8)

    def test_date_filters_reach_cleanup(self):
        m_batch, m_detect, m_p3, m_emit, m_p5 = _mocks()
        with m_batch as b, m_detect, m_p3, m_emit, m_p5:
            ingest.run_ingest(from_date=date(2026, 5, 1), progress=False)
        self.assertEqual(b.call_args[1]["from_date"], date(2026, 5, 1))


class TestIngestCLI(unittest.TestCase):

    def test_cli_flags_route(self):
        m_batch, m_detect, m_p3, m_emit, m_p5 = _mocks()
        with m_batch as b, m_detect, m_p3, m_emit, m_p5 as p, \
             patch("builtins.print"):
            ingest.main(["--backend", "claude-cli", "--no-engrams",
                         "--quiet", "--limit", "10"])
        self.assertEqual(b.call_args[1]["backend"], "claude-cli")
        self.assertEqual(b.call_args[1]["limit"], 10)
        p.assert_not_called()

    def test_cli_no_extraction_flag(self):
        m_batch, m_detect, m_p3, m_emit, m_p5 = _mocks()
        with m_batch, m_detect, m_p3 as p3, m_emit, m_p5, \
             patch("builtins.print"):
            ingest.main(["--no-extraction", "--quiet"])
        p3.assert_not_called()


if __name__ == "__main__":
    unittest.main()
