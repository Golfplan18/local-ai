"""Unified conversation ingest — one command from raw exports to engrams.

Chains the four batch stages of the Conversation Processing Pipeline
into a single resumable run:

  Stage 1 — Cleanup (Layers 1–2.5):   `cli.run_batch`
      Raw exports in the input directory → cleaned-pair archive.
      Resume: cleanup manifest skips completed files.

  Stage 2 — Extraction (Phase 3):     `phase3_extraction.run_phase3`
      Pasted news/opinion/resource segments in the cleaned pairs →
      structured source notes in the flat vault `Resources/` folder +
      ChromaDB `knowledge` records. Chain detection runs first so the
      notes carry chain_id/chain_label enrichment.
      Resume: phase3 manifest skips completed segments.

  Stage 3 — Chunks (Layers 3–4):      `path2_cli.run_chain_detection`
      + `path2_cli.run_chunk_emission`
      Cleaned pairs → chain index → chunk files + ChromaDB
      `conversations` records. Chain detection is deterministic and
      re-runs over the whole archive each time (no model calls);
      emission skips sessions already in the path2 manifest.

  Stage 4 — Engrams (downstream):     `phase5_atomic_extraction.run_phase5`
      Cleaned pairs → atomic engram notes in the vault + dedup index.
      Resume: phase5 manifest skips completed pairs.

Every stage is manifest-guarded, so re-running the command after an
interruption (rate-window exhaustion, reboot, Ctrl-C) continues where
it left off. Every stage's model calls flow through the selected
backend (`api` / `claude-cli` / `ora-slots`); this module never names
models.

CLI:

    python -m orchestrator.historical.ingest \
        --backend claude-cli
    python -m orchestrator.historical.ingest \
        --input-dir ~/Documents/conversations/raw --no-engrams

This is the runnable entry point for the Conversation Processing
Pipeline framework's batch mode. Ora invokes the same `run_ingest`
function programmatically (backend `ora-slots`).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime
from typing import Optional

from orchestrator.historical.cleanup_backends import (
    BACKEND_API,
    BACKEND_CHOICES,
    BACKEND_CLAUDE_CLI,
    CLI_RECOMMENDED_MAX_WORKERS,
)
from orchestrator.historical.cli import (
    DEFAULT_INPUT_DIR,
    run_batch,
)
from orchestrator.historical.path2_cli import (
    run_chain_detection,
    run_chunk_emission,
)
from orchestrator.historical.phase3_extraction import run_phase3
from orchestrator.historical.phase5_atomic_extraction import run_phase5
from orchestrator.historical.writer import DEFAULT_OUTPUT_DIR


def run_ingest(
    input_dir:     str = DEFAULT_INPUT_DIR,
    *,
    output_dir:    str = DEFAULT_OUTPUT_DIR,
    backend:       str = BACKEND_API,
    from_date:     Optional[date] = None,
    to_date:       Optional[date] = None,
    max_workers:   int = 8,
    file_workers:  int = 1,
    limit:         Optional[int] = None,
    extraction:    bool = True,
    chunks:        bool = True,
    engrams:       bool = True,
    progress:      bool = True,
) -> dict:
    """Run the full ingest chain. Returns a per-stage summary dict.

    Stage boundaries are hard: extraction and chunks only start after
    cleanup completes, engrams only after chunks. Chain detection runs
    once ahead of extraction (its persisted chain-index.json enriches
    the source notes) and its session map feeds chunk emission. A stage
    that processes nothing is still recorded in the summary.
    """
    started = time.monotonic()
    summary: dict = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "input_dir":  input_dir,
        "backend":    backend,
    }

    # ---- Stage 1: cleanup -------------------------------------------------
    if progress:
        print("[ingest] stage 1/4 — cleanup (raw exports → cleaned pairs)",
              file=sys.stderr, flush=True)
    summary["cleanup"] = run_batch(
        input_dir=input_dir,
        output_dir=output_dir,
        from_date=from_date,
        to_date=to_date,
        max_workers=max_workers,
        file_workers=file_workers,
        limit=limit,
        backend=backend,
        progress_to_stderr=progress,
    )

    # ---- Chain detection (feeds stage 2 enrichment + stage 3 emission) ----
    detection: Optional[dict] = None
    if extraction or chunks:
        detection = run_chain_detection(
            cleaned_pair_dir=output_dir,
            progress_to_stderr=progress,
        )
        summary["chains"] = {
            "sessions": detection.get("sessions", 0),
            "chains":   detection.get("chains", 0),
        }

    # ---- Stage 2: phase-3 extraction (pasted sources → vault notes) -------
    if extraction:
        if progress:
            print("[ingest] stage 2/4 — extraction (pasted news/opinion/"
                  "resource → vault Resources/ + knowledge index)",
                  file=sys.stderr, flush=True)
        extraction_workers = max_workers
        if backend == BACKEND_CLAUDE_CLI:
            extraction_workers = min(extraction_workers,
                                     CLI_RECOMMENDED_MAX_WORKERS)
        summary["extraction"] = run_phase3(
            archive_dir=output_dir,
            max_workers=extraction_workers,
            progress_to_stderr=progress,
            backend=backend,
        )
    else:
        summary["extraction"] = {"skipped": True}

    # ---- Stage 3: chunk emission -------------------------------------------
    if chunks:
        if progress:
            print("[ingest] stage 3/4 — chunks (cleaned pairs → chunk files "
                  "+ ChromaDB)", file=sys.stderr, flush=True)
        summary["chunks"] = run_chunk_emission(
            detection["sessions_to_paths"],
            max_workers=4,
            progress_to_stderr=progress,
        )
    else:
        summary["chunks"] = {"skipped": True}

    # ---- Stage 4: engram extraction ---------------------------------------
    if engrams:
        if progress:
            print("[ingest] stage 4/4 — engrams (cleaned pairs → atomic "
                  "notes)", file=sys.stderr, flush=True)
        phase5_workers = max_workers
        if backend == BACKEND_CLAUDE_CLI:
            phase5_workers = min(phase5_workers, CLI_RECOMMENDED_MAX_WORKERS)
        summary["engrams"] = run_phase5(
            archive_dir=output_dir,
            max_workers=phase5_workers,
            progress_to_stderr=progress,
            backend=backend,
        )
    else:
        summary["engrams"] = {"skipped": True}

    summary["duration_secs"] = time.monotonic() - started
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Unified conversation ingest: cleanup → extraction "
                    "→ chunks → engrams.",
    )
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--backend", choices=list(BACKEND_CHOICES),
                        default=BACKEND_API,
                        help="Model-call path for every stage: 'api' "
                             "(metered Anthropic key), 'claude-cli' "
                             "(subscription), 'ora-slots' (Ora slot "
                             "routing), 'openrouter' (explicit "
                             "OpenRouter-only route via openrouter.ai)")
    parser.add_argument("--from-date", type=_parse_iso_date)
    parser.add_argument("--to-date", type=_parse_iso_date)
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--file-workers", type=int, default=1)
    parser.add_argument("--limit", type=int,
                        help="Max raw files to clean this run")
    parser.add_argument("--no-extraction", action="store_true",
                        help="Skip phase-3 source-note extraction")
    parser.add_argument("--no-chunks", action="store_true",
                        help="Skip chunk emission + ChromaDB indexing")
    parser.add_argument("--no-engrams", action="store_true",
                        help="Skip engram extraction (no heavy-tier calls)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    summary = run_ingest(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        backend=args.backend,
        from_date=args.from_date,
        to_date=args.to_date,
        max_workers=args.max_workers,
        file_workers=args.file_workers,
        limit=args.limit,
        extraction=not args.no_extraction,
        chunks=not args.no_chunks,
        engrams=not args.no_engrams,
        progress=not args.quiet,
    )
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["run_ingest", "main"]
