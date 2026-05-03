"""Phase 2 batch CLI — chain detection + chunk emission.

Two-stage flow:

  Stage A (chain detection):
    Walk all cleaned-pair files, group into sessions, detect chains
    via methods 1+2 (title-keyword overlap + topic-fingerprint
    overlap), persist `~/ora/data/chain-index.json`.

  Stage B (chunk emission):
    For each session in the chain index, emit one chunk per pair to
    `~/Documents/conversations/` and one record per chunk to ChromaDB
    `conversations` collection. Inject the session's chain_id and
    chain_label into each chunk's metadata so RAG queries can walk
    the entire chain when a chunk hits.

A manifest at `~/ora/data/path2-manifest.json` tracks per-session
emission state. Re-runs skip sessions already complete unless
`--rebuild-manifest` is used. Chain detection always re-runs unless
`--skip-chain-detection` is passed.

CLI:

    /opt/homebrew/bin/python3 -m orchestrator.historical.path2_cli \\
        --max-workers 4
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from orchestrator.historical.chain_detector import (
    CHAIN_INDEX_DEFAULT,
    DEFAULT_MIN_SHARED_PHRASES,
    DEFAULT_MIN_SHARED_TITLE_KEYWORDS,
    DEFAULT_PHRASE_DF_CUTOFF,
    DEFAULT_TITLE_DF_CUTOFF,
    Session,
    derive_session_id,
    detect_chains,
    extract_session_key_phrases,
    extract_title_keywords,
    load_chain_index,
    save_chain_index,
)
from orchestrator.historical.cleaned_pair_reader import load_cleaned_pair
from orchestrator.historical.path2_orchestrator import (
    DEFAULT_CHROMADB_PATH,
    DEFAULT_CLEANED_PAIR_DIR,
    DEFAULT_CONVERSATIONS_DIR,
    SessionEmissionResult,
    emit_chunks_for_all_sessions,
)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_MANIFEST_PATH = "/Users/oracle/ora/data/path2-manifest.json"


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def _empty_manifest() -> dict:
    return {
        "version":      1,
        "created_at":   datetime.now().isoformat(timespec="seconds"),
        "last_updated": datetime.now().isoformat(timespec="seconds"),
        "completed_sessions": {},   # source_chat → entry
        "totals": {
            "sessions_completed":  0,
            "chunks_written":      0,
            "chunks_indexed":      0,
            "chunks_skipped":      0,
        },
    }


def load_manifest(path: str = DEFAULT_MANIFEST_PATH) -> dict:
    p = Path(path).expanduser()
    if not p.exists():
        return _empty_manifest()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_manifest()


def save_manifest(manifest: dict, path: str = DEFAULT_MANIFEST_PATH) -> None:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    manifest["last_updated"] = datetime.now().isoformat(timespec="seconds")
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    tmp.replace(p)


def manifest_record_session(
    manifest: dict,
    source_chat: str,
    result: SessionEmissionResult,
) -> None:
    manifest.setdefault("completed_sessions", {})[source_chat] = {
        "completed_at":   datetime.now().isoformat(timespec="seconds"),
        "session_id":     result.session_id,
        "chain_id":       result.chain_id,
        "chain_label":    result.chain_label,
        "pairs_total":    result.pairs_total,
        "chunks_written": result.chunks_written,
        "chunks_indexed": result.chunks_indexed,
        "chunks_skipped": result.chunks_skipped,
        "duration_secs":  result.duration_secs,
        "errors":         result.errors[:20],
    }
    totals = manifest.setdefault("totals", {})
    totals["sessions_completed"] = totals.get("sessions_completed", 0) + 1
    totals["chunks_written"]     = totals.get("chunks_written", 0) + result.chunks_written
    totals["chunks_indexed"]     = totals.get("chunks_indexed", 0) + result.chunks_indexed
    totals["chunks_skipped"]     = totals.get("chunks_skipped", 0) + result.chunks_skipped


# ---------------------------------------------------------------------------
# Stage A — Chain detection
# ---------------------------------------------------------------------------


def build_sessions_from_archive(
    cleaned_pair_dir: str = DEFAULT_CLEANED_PAIR_DIR,
    *,
    progress_to_stderr: bool = True,
) -> tuple[list[Session], dict[str, list[str]]]:
    """Walk the cleaned-pair archive, parse every file, group by
    `source_chat`, and build one Session record per group.

    Returns:
        (sessions, sessions_to_paths)
        - `sessions`: list of Session records (one per source_chat)
        - `sessions_to_paths`: source_chat → ordered list of cleaned-pair
          file paths (sorted by source_pair_num)
    """
    start = time.monotonic()
    by_source: dict[str, list] = defaultdict(list)
    files = list(Path(cleaned_pair_dir).expanduser().glob("*.md"))
    if progress_to_stderr:
        print(f"[chain] scanning {len(files):,} cleaned-pair files...",
              file=sys.stderr, flush=True)
    parsed = 0
    skipped = 0
    for f in files:
        try:
            cp = load_cleaned_pair(f)
            by_source[cp.source_chat].append(cp)
            parsed += 1
        except Exception:
            skipped += 1
            continue
    if progress_to_stderr:
        print(f"[chain] parsed {parsed:,} ({skipped} skipped) in "
              f"{time.monotonic()-start:.1f}s; "
              f"{len(by_source):,} unique sessions",
              file=sys.stderr, flush=True)

    sessions: list[Session] = []
    sessions_to_paths: dict[str, list[str]] = {}
    t1 = time.monotonic()
    for source_chat, cps in by_source.items():
        cps.sort(key=lambda c: c.source_pair_num)
        # Aggregate cleaned content (capped) for phrase extraction.
        user_agg = "\n".join(
            (cp.cleaned_user_input or "")[:600] for cp in cps[:30]
        )
        ai_agg = "\n".join(
            (cp.cleaned_ai_response or "")[:300] for cp in cps[:30]
        )
        title = Path(source_chat).stem
        title_kw = extract_title_keywords(source_chat)
        phrases = extract_session_key_phrases(title, user_agg, ai_agg)
        timestamps = [c.source_timestamp for c in cps if c.source_timestamp]
        sessions.append(Session(
            session_id         = derive_session_id(source_chat),
            source_chat        = source_chat,
            source_platform    = cps[0].source_platform if cps else "unknown",
            title_keywords     = title_kw,
            key_phrases        = phrases,
            fingerprint        = "|".join(sorted(p.lower() for p in phrases)),
            cleaned_pair_paths = [c.file_path for c in cps],
            first_when         = min(timestamps) if timestamps else None,
            last_when          = max(timestamps) if timestamps else None,
        ))
        sessions_to_paths[source_chat] = [c.file_path for c in cps]

    if progress_to_stderr:
        print(f"[chain] built {len(sessions):,} session records in "
              f"{time.monotonic()-t1:.1f}s",
              file=sys.stderr, flush=True)
    return sessions, sessions_to_paths


def run_chain_detection(
    cleaned_pair_dir: str = DEFAULT_CLEANED_PAIR_DIR,
    chain_index_path: str = CHAIN_INDEX_DEFAULT,
    *,
    min_shared_title_keywords: int = DEFAULT_MIN_SHARED_TITLE_KEYWORDS,
    min_shared_phrases:        int = DEFAULT_MIN_SHARED_PHRASES,
    title_df_cutoff:           float = DEFAULT_TITLE_DF_CUTOFF,
    phrase_df_cutoff:          float = DEFAULT_PHRASE_DF_CUTOFF,
    progress_to_stderr:        bool = True,
) -> dict:
    """Stage A — build sessions, detect chains, persist `chain-index.json`."""
    sessions, sessions_to_paths = build_sessions_from_archive(
        cleaned_pair_dir, progress_to_stderr=progress_to_stderr,
    )
    t1 = time.monotonic()
    chains = detect_chains(
        sessions,
        min_shared_title_keywords=min_shared_title_keywords,
        min_shared_phrases=min_shared_phrases,
        title_df_cutoff=title_df_cutoff,
        phrase_df_cutoff=phrase_df_cutoff,
    )
    if progress_to_stderr:
        print(f"[chain] detected {len(chains):,} chains in "
              f"{time.monotonic()-t1:.1f}s",
              file=sys.stderr, flush=True)
        # Top-N for human inspection.
        for c in chains[:10]:
            print(f"[chain]   {c.session_count:4} sessions  "
                  f"label={c.chain_label!r}",
                  file=sys.stderr, flush=True)

    save_chain_index(chains, sessions, path=chain_index_path)
    return {
        "sessions":          len(sessions),
        "chains":            len(chains),
        "chain_index_path":  chain_index_path,
        "sessions_to_paths": sessions_to_paths,
    }


# ---------------------------------------------------------------------------
# Stage B — Chunk emission
# ---------------------------------------------------------------------------


def run_chunk_emission(
    sessions_to_paths: dict[str, list[str]],
    chain_index_path:  str = CHAIN_INDEX_DEFAULT,
    *,
    conversations_dir: str = DEFAULT_CONVERSATIONS_DIR,
    chromadb_path:     str = DEFAULT_CHROMADB_PATH,
    manifest_path:     str = DEFAULT_MANIFEST_PATH,
    max_workers:       int = 4,
    rebuild_manifest:  bool = False,
    progress_to_stderr: bool = True,
) -> dict:
    """Stage B — emit chunks + ChromaDB records for each session.

    Resumes from `manifest_path` unless `rebuild_manifest`. Each session
    is processed via `emit_chunks_for_all_sessions`.
    """
    chain_index = load_chain_index(chain_index_path)
    session_to_chain: dict[str, str] = chain_index.get("session_to_chain", {})
    chain_labels: dict[str, str] = {
        c["chain_id"]: c["chain_label"]
        for c in chain_index.get("chains", [])
    }

    manifest = load_manifest(manifest_path)
    if rebuild_manifest:
        manifest = _empty_manifest()
    completed = set(manifest.get("completed_sessions", {}).keys())

    targets = {
        source: paths
        for source, paths in sessions_to_paths.items()
        if source not in completed
    }
    if progress_to_stderr:
        print(f"[emit] {len(sessions_to_paths):,} sessions in scope, "
              f"{len(completed):,} already complete, "
              f"{len(targets):,} to process (max_workers={max_workers})",
              file=sys.stderr, flush=True)

    if not targets:
        if progress_to_stderr:
            print("[emit] nothing to do — exiting", file=sys.stderr,
                  flush=True)
        return {"sessions_processed": 0}

    start = time.monotonic()
    aggregate = {
        "sessions_processed":  0,
        "chunks_written":      0,
        "chunks_indexed":      0,
        "chunks_skipped":      0,
        "errors_total":        0,
    }
    counter = {"done": 0}
    total = len(targets)

    def _on_complete(source: str, r: SessionEmissionResult) -> None:
        counter["done"] += 1
        aggregate["sessions_processed"] += 1
        aggregate["chunks_written"]     += r.chunks_written
        aggregate["chunks_indexed"]     += r.chunks_indexed
        aggregate["chunks_skipped"]     += r.chunks_skipped
        aggregate["errors_total"]       += len(r.errors)
        manifest_record_session(manifest, source, r)
        if counter["done"] % 25 == 0:
            save_manifest(manifest, manifest_path)
        if progress_to_stderr and counter["done"] % 50 == 0:
            print(f"[emit] {counter['done']}/{total} "
                  f"({time.monotonic()-start:.0f}s)  "
                  f"chunks_written={aggregate['chunks_written']}  "
                  f"chunks_skipped={aggregate['chunks_skipped']}",
                  file=sys.stderr, flush=True)

    emit_chunks_for_all_sessions(
        targets,
        conversations_dir = conversations_dir,
        chromadb_path     = chromadb_path,
        session_to_chain  = session_to_chain,
        chain_labels      = chain_labels,
        max_workers       = max_workers,
        progress_cb       = _on_complete,
    )

    save_manifest(manifest, manifest_path)
    aggregate["duration_secs"] = time.monotonic() - start
    return aggregate


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 2 — chain detection + chunk emission.",
    )
    parser.add_argument("--cleaned-pair-dir",
                          default=DEFAULT_CLEANED_PAIR_DIR)
    parser.add_argument("--conversations-dir",
                          default=DEFAULT_CONVERSATIONS_DIR)
    parser.add_argument("--chromadb-path",
                          default=DEFAULT_CHROMADB_PATH)
    parser.add_argument("--chain-index-path",
                          default=CHAIN_INDEX_DEFAULT)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--skip-chain-detection", action="store_true",
                          help="Reuse existing chain-index.json without rebuilding")
    parser.add_argument("--rebuild-manifest", action="store_true",
                          help="Ignore the path2 manifest, re-emit everything")
    parser.add_argument("--quiet", action="store_true",
                          help="Suppress progress messages to stderr")
    args = parser.parse_args(argv)

    progress = not args.quiet

    # Stage A: chain detection.
    if args.skip_chain_detection:
        if progress:
            print("[chain] --skip-chain-detection set; reusing existing index",
                  file=sys.stderr, flush=True)
        # Build sessions_to_paths fresh (cheap) so emission has the
        # current cleaned-pair file list. Only chain detection is skipped.
        _, sessions_to_paths = build_sessions_from_archive(
            args.cleaned_pair_dir, progress_to_stderr=progress,
        )
        chain_stats = {
            "sessions_to_paths": sessions_to_paths,
            "skipped": True,
        }
    else:
        chain_stats = run_chain_detection(
            cleaned_pair_dir   = args.cleaned_pair_dir,
            chain_index_path   = args.chain_index_path,
            progress_to_stderr = progress,
        )

    sessions_to_paths = chain_stats.pop("sessions_to_paths")

    # Stage B: chunk emission.
    emit_stats = run_chunk_emission(
        sessions_to_paths,
        chain_index_path   = args.chain_index_path,
        conversations_dir  = args.conversations_dir,
        chromadb_path      = args.chromadb_path,
        manifest_path      = args.manifest,
        max_workers        = args.max_workers,
        rebuild_manifest   = args.rebuild_manifest,
        progress_to_stderr = progress,
    )

    print(json.dumps({
        "chain_stage": chain_stats,
        "emit_stage":  emit_stats,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "DEFAULT_MANIFEST_PATH",
    "load_manifest",
    "save_manifest",
    "build_sessions_from_archive",
    "run_chain_detection",
    "run_chunk_emission",
    "main",
]
