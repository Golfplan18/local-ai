"""Batch CLI + manifest tracking (Phase 1.12).

Walks a directory of raw chat files, applies an optional date filter,
and processes each file via the per-file orchestrator (Phase 1.11).

A manifest at `~/ora/data/cleanup-manifest.json` tracks completed and
errored files so resumes skip already-processed chats. The manifest is
JSON keyed by raw-chat absolute path; each entry records pairs counts,
cost, output paths, and timestamps.

CLI invocation:

    /opt/homebrew/bin/python3 -m orchestrator.historical.cli \\
        --input-dir ~/Documents/conversations/raw \\
        --output-dir "~/Documents/Commercial AI archives" \\
        --from-date 2026-02-01 \\
        --max-workers 8 \\
        --limit 50

For the pilot batch:

    /opt/homebrew/bin/python3 -m orchestrator.historical.cli \\
        --from-date 2026-02-01 \\
        --max-workers 8

`--rebuild` ignores the manifest. `--resume` (default) skips files
listed as completed in the manifest. Errored files are NOT skipped on
resume — they retry on the next run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from orchestrator.historical.api_client import AnthropicClient
from orchestrator.historical.file_orchestrator import (
    FileProcessingResult,
    ProgressEvent,
    process_chat_file,
)
from orchestrator.historical.parser import parse_raw_chat_file
from orchestrator.historical.writer import DEFAULT_OUTPUT_DIR
from orchestrator.tools.vault_indexer import load_index, INDEX_DEFAULT


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_INPUT_DIR    = os.path.expanduser("~/Documents/conversations/raw")
DEFAULT_MANIFEST_PATH = os.path.expanduser("~/ora/data/cleanup-manifest.json")


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def load_manifest(path: str) -> dict:
    """Load existing manifest or return a fresh empty one."""
    p = Path(path).expanduser()
    if not p.exists():
        return _empty_manifest()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_manifest()


def _empty_manifest() -> dict:
    return {
        "version":            1,
        "created_at":         datetime.now().isoformat(timespec="seconds"),
        "last_updated":       datetime.now().isoformat(timespec="seconds"),
        "completed_files":    {},   # raw_path → completed entry
        "errored_files":      {},   # raw_path → errored entry
        "totals": {
            "pairs_total":    0,
            "pairs_succeeded": 0,
            "pairs_errored":   0,
            "cost_usd":        0.0,
        },
    }


def save_manifest(path: str, manifest: dict) -> None:
    """Atomically write the manifest."""
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    manifest["last_updated"] = datetime.now().isoformat(timespec="seconds")
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    tmp.replace(p)


def manifest_completed(manifest: dict, raw_path: str) -> bool:
    return raw_path in manifest.get("completed_files", {})


def manifest_record_completed(manifest: dict, raw_path: str,
                                result: FileProcessingResult) -> None:
    manifest.setdefault("completed_files", {})[raw_path] = {
        "completed_at":      datetime.now().isoformat(timespec="seconds"),
        "chat_title":        result.chat_title,
        "chat_platform":     result.chat_platform,
        "pairs_total":       result.pairs_total,
        "pairs_succeeded":   result.pairs_succeeded,
        "pairs_with_errors": result.pairs_with_errors,
        "pairs_skipped":     result.pairs_skipped,
        "output_paths":      result.output_paths,
        "input_tokens":      result.total_input_tokens,
        "output_tokens":     result.total_output_tokens,
        "cost_usd":          result.total_cost_usd,
        "duration_secs":     result.duration_secs,
        "errors":            result.errors,
    }
    # Move out of errored_files if it was there.
    manifest.get("errored_files", {}).pop(raw_path, None)
    totals = manifest.setdefault("totals", {})
    totals["pairs_total"]    = totals.get("pairs_total", 0) + result.pairs_total
    totals["pairs_succeeded"] = totals.get("pairs_succeeded", 0) + result.pairs_succeeded
    totals["pairs_errored"]  = totals.get("pairs_errored", 0) + result.pairs_with_errors
    totals["cost_usd"]       = totals.get("cost_usd", 0.0) + result.total_cost_usd


def manifest_record_errored(manifest: dict, raw_path: str,
                              result: FileProcessingResult) -> None:
    manifest.setdefault("errored_files", {})[raw_path] = {
        "errored_at":   datetime.now().isoformat(timespec="seconds"),
        "abort_reason": result.abort_reason,
        "errors":       result.errors[:20],
        "pairs_total":  result.pairs_total,
    }


# ---------------------------------------------------------------------------
# File enumeration + date filter
# ---------------------------------------------------------------------------


def enumerate_input_files(input_dir: str) -> list[str]:
    """List all .md files under input_dir recursively, sorted."""
    root = Path(input_dir).expanduser()
    if not root.is_dir():
        return []
    return sorted(str(p) for p in root.rglob("*.md") if p.is_file())


def chat_creation_date(raw_path: str) -> Optional[date]:
    """Return the chat's created_at as a date, or None if unparseable."""
    try:
        chat = parse_raw_chat_file(raw_path)
    except Exception:
        return None
    if chat.metadata.created_at is None:
        return None
    return chat.metadata.created_at.date()


def passes_date_filter(raw_path: str,
                         from_date: Optional[date],
                         to_date:   Optional[date]) -> bool:
    """Return True if the raw chat is within [from_date, to_date]."""
    if from_date is None and to_date is None:
        return True
    chat_date = chat_creation_date(raw_path)
    if chat_date is None:
        # Unparseable date — include by default (safer than excluding).
        return True
    if from_date and chat_date < from_date:
        return False
    if to_date and chat_date > to_date:
        return False
    return True


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------


def run_batch(
    input_dir:        str = DEFAULT_INPUT_DIR,
    output_dir:       str = DEFAULT_OUTPUT_DIR,
    manifest_path:    str = DEFAULT_MANIFEST_PATH,
    vault_index_path: str = INDEX_DEFAULT,
    from_date:        Optional[date] = None,
    to_date:          Optional[date] = None,
    max_workers:      int = 8,
    file_workers:     int = 1,
    limit:            Optional[int] = None,
    resume:           bool = True,
    rebuild:          bool = False,
    config:           Optional[dict] = None,
    progress_to_stderr: bool = True,
) -> dict:
    """Run cleanup batch. Returns aggregate stats.

    `file_workers` controls how many files are processed in parallel
    through the shared AnthropicClient. Default 1 (sequential). Set to
    e.g. 4 to spawn 4 file-level workers; total in-flight API calls
    becomes file_workers × max_workers.
    """

    start = time.monotonic()

    # Load manifest + vault index once.
    manifest = load_manifest(manifest_path) if not rebuild else _empty_manifest()
    try:
        vault_index = load_index(vault_index_path)
    except Exception as e:
        print(f"warning: failed to load vault index ({e}); proceeding without",
              file=sys.stderr)
        vault_index = {"entries": []}

    client = AnthropicClient()

    # Enumerate + filter
    all_files = enumerate_input_files(input_dir)
    pre_filter = len(all_files)
    target_files: list[str] = []
    skipped_filter = 0
    skipped_resume = 0
    for f in all_files:
        if not passes_date_filter(f, from_date, to_date):
            skipped_filter += 1
            continue
        if resume and not rebuild and manifest_completed(manifest, f):
            skipped_resume += 1
            continue
        target_files.append(f)
        if limit and len(target_files) >= limit:
            break

    if progress_to_stderr:
        print(f"[batch] {pre_filter} files in input dir, "
              f"{skipped_filter} filtered out by date, "
              f"{skipped_resume} skipped by resume, "
              f"{len(target_files)} to process "
              f"(file_workers={file_workers}, pair_workers={max_workers}, "
              f"total in-flight ≤ {file_workers * max_workers})",
              file=sys.stderr)

    aggregate = {
        "input_dir":           input_dir,
        "output_dir":          output_dir,
        "manifest_path":       manifest_path,
        "files_in_input_dir":  pre_filter,
        "files_skipped_filter": skipped_filter,
        "files_skipped_resume": skipped_resume,
        "files_to_process":    len(target_files),
        "files_succeeded":     0,
        "files_aborted":       0,
        "pairs_total":         0,
        "pairs_succeeded":     0,
        "pairs_with_errors":   0,
        "total_cost_usd":      0.0,
        "duration_secs":       0.0,
    }

    def _progress(ev: ProgressEvent) -> None:
        if not progress_to_stderr:
            return
        if ev.stage == "complete":
            return  # final summary printed below
        if ev.stage in ("parse", "cleanup-start"):
            return  # quiet
        # Cleanup-done / write — too verbose for full archive runs;
        # only print at INFO level if a small batch.

    # Lock guarding manifest + aggregate updates when running file_workers > 1.
    state_lock = threading.Lock()
    counter = {"done": 0}

    def _process_one(raw_path: str) -> tuple[str, "FileProcessingResult"]:
        """Run process_chat_file safely, returning result + path."""
        try:
            result = process_chat_file(
                raw_path,
                vault_index=vault_index,
                anthropic_client=client,
                config=config,
                output_dir=output_dir,
                max_workers=max_workers,
                progress_cb=_progress,
            )
            return raw_path, result
        except Exception as e:
            err_result = FileProcessingResult(
                raw_path=raw_path,
                aborted=True,
                abort_reason=f"unexpected exception: {e}",
                errors=[str(e)],
            )
            return raw_path, err_result

    def _record_completion(raw_path: str, result) -> None:
        """Update manifest + aggregate stats under lock, persist atomically."""
        with state_lock:
            counter["done"] += 1
            i = counter["done"]
            elapsed = time.monotonic() - start
            if progress_to_stderr:
                print(f"[batch] {i}/{len(target_files)} ({elapsed:.0f}s) "
                      f"done: {os.path.basename(raw_path)}",
                      file=sys.stderr)
            if result.aborted:
                manifest_record_errored(manifest, raw_path, result)
                aggregate["files_aborted"] += 1
                if progress_to_stderr:
                    print(f"  → ABORTED: {result.abort_reason}", file=sys.stderr)
            else:
                manifest_record_completed(manifest, raw_path, result)
                aggregate["files_succeeded"] += 1
                aggregate["pairs_total"]      += result.pairs_total
                aggregate["pairs_succeeded"]  += result.pairs_succeeded
                aggregate["pairs_with_errors"] += result.pairs_with_errors
                aggregate["total_cost_usd"]   += result.total_cost_usd
                if progress_to_stderr:
                    print(f"  → {result.pairs_succeeded}/{result.pairs_total} "
                          f"pairs, {result.engagement_strips_logged} strips, "
                          f"${result.total_cost_usd:.4f}",
                          file=sys.stderr)
            save_manifest(manifest_path, manifest)

    if file_workers <= 1:
        # Sequential path — simpler, lower contention for small batches.
        for raw_path in target_files:
            path, result = _process_one(raw_path)
            _record_completion(path, result)
    else:
        # Parallel file workers via shared AnthropicClient (thread-safe).
        with ThreadPoolExecutor(max_workers=file_workers) as pool:
            futures = [pool.submit(_process_one, p) for p in target_files]
            for fut in as_completed(futures):
                path, result = fut.result()
                _record_completion(path, result)

    aggregate["duration_secs"] = time.monotonic() - start

    if progress_to_stderr:
        s = client.stats()
        print(file=sys.stderr)
        print(f"[batch] Complete in {aggregate['duration_secs']:.1f}s",
              file=sys.stderr)
        print(f"  files: {aggregate['files_succeeded']} succeeded, "
              f"{aggregate['files_aborted']} aborted",
              file=sys.stderr)
        print(f"  pairs: {aggregate['pairs_succeeded']}/{aggregate['pairs_total']} "
              f"succeeded ({aggregate['pairs_with_errors']} errors)",
              file=sys.stderr)
        print(f"  API: {s.calls} calls, {s.failures} failures, "
              f"{s.input_tokens}+{s.output_tokens} tokens, "
              f"${s.cost_usd:.4f}",
              file=sys.stderr)

    return aggregate


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


def _parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Batch cleanup of raw chat archive (Phase 1).",
    )
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--vault-index", default=INDEX_DEFAULT)
    parser.add_argument("--from-date", type=_parse_iso_date,
                          help="Filter: chat created_at >= this date (YYYY-MM-DD)")
    parser.add_argument("--to-date", type=_parse_iso_date,
                          help="Filter: chat created_at <= this date (YYYY-MM-DD)")
    parser.add_argument("--max-workers", type=int, default=8,
                          help="Parallel cleanup workers per file (default 8)")
    parser.add_argument("--file-workers", type=int, default=1,
                          help="Files processed in parallel (default 1). "
                               "Total in-flight = file-workers × max-workers.")
    parser.add_argument("--limit", type=int,
                          help="Max files to process this run")
    parser.add_argument("--rebuild", action="store_true",
                          help="Ignore manifest, reprocess everything")
    parser.add_argument("--no-resume", action="store_true",
                          help="Don't skip files in manifest (still record results)")
    parser.add_argument("--quiet", action="store_true",
                          help="Suppress per-file progress to stderr")
    args = parser.parse_args(argv)

    aggregate = run_batch(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        manifest_path=args.manifest,
        vault_index_path=args.vault_index,
        from_date=args.from_date,
        to_date=args.to_date,
        max_workers=args.max_workers,
        file_workers=args.file_workers,
        limit=args.limit,
        resume=not args.no_resume,
        rebuild=args.rebuild,
        progress_to_stderr=not args.quiet,
    )
    print(json.dumps(aggregate, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "DEFAULT_INPUT_DIR",
    "DEFAULT_MANIFEST_PATH",
    "load_manifest",
    "save_manifest",
    "manifest_completed",
    "manifest_record_completed",
    "manifest_record_errored",
    "enumerate_input_files",
    "chat_creation_date",
    "passes_date_filter",
    "run_batch",
    "main",
]
