"""Per-file orchestrator with parallel workers (Phase 1.11).

Processes one raw chat file end-to-end:
  1. Parse the file (Phase 1.2) → list of RawPair
  2. Cleanup all pairs in parallel (Phase 1.8) via ThreadPoolExecutor
  3. Build context headers in source order (Phase 1.9) — must be
     sequential because thread-id assignment depends on prior pairs
  4. Write cleaned-pair files (Phase 1.10)
  5. Aggregate stats

The parallel workers share a single AnthropicClient instance (which
is thread-safe). The per-pair cleanup makes 2 model calls (user + AI),
so with 8 workers the API has up to 16 in-flight requests.

Per-file resume / manifest tracking lives in Phase 1.12 (CLI).
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from orchestrator.historical import RawChat
from orchestrator.historical.api_client import AnthropicClient
from orchestrator.historical.context_header import (
    ContextHeader,
    ThreadTracker,
    build_context_header,
)
from orchestrator.historical.engagement import (
    ENGAGEMENT_LOG_DEFAULT,
    log_strips,
)
from orchestrator.historical.pair_cleanup import (
    CleanedPair,
    clean_pair,
)
from orchestrator.historical.parser import parse_raw_chat_file
from orchestrator.historical.writer import (
    DEFAULT_OUTPUT_DIR,
    write_cleaned_pair_file,
)


# ---------------------------------------------------------------------------
# Result + progress event
# ---------------------------------------------------------------------------


@dataclass
class FileProcessingResult:
    """Aggregate outcome of processing one raw chat file."""
    raw_path:           str
    chat_title:         str = ""
    chat_platform:      str = ""
    pairs_total:        int = 0
    pairs_succeeded:    int = 0
    pairs_skipped:      int = 0
    pairs_with_errors:  int = 0
    output_paths:       list[str] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd:     float = 0.0
    engagement_strips_logged: int = 0
    duration_secs:      float = 0.0
    errors:             list[str] = field(default_factory=list)
    aborted:            bool = False
    abort_reason:       str = ""


@dataclass
class ProgressEvent:
    """One progress notification, passed to optional progress callback."""
    raw_path:    str
    stage:       str           # 'parse' | 'cleanup-start' | 'cleanup-done' | 'write' | 'complete'
    pair_num:    int = 0
    total_pairs: int = 0
    detail:      str = ""


# ---------------------------------------------------------------------------
# Error budget
# ---------------------------------------------------------------------------

# If this fraction (or more) of pairs error out, abort the file.
ABORT_ERROR_FRACTION = 0.5
ABORT_MIN_FAILURES = 3   # need at least N failures before abort kicks in


def _should_abort(pairs_total: int, errored: int) -> bool:
    if pairs_total < ABORT_MIN_FAILURES:
        return False
    if errored < ABORT_MIN_FAILURES:
        return False
    return (errored / pairs_total) >= ABORT_ERROR_FRACTION


# ---------------------------------------------------------------------------
# Process one file
# ---------------------------------------------------------------------------


def process_chat_file(
    raw_path:         str,
    *,
    vault_index:      dict,
    anthropic_client: AnthropicClient,
    config:           Optional[dict] = None,
    output_dir:       str = DEFAULT_OUTPUT_DIR,
    max_workers:      int = 8,
    progress_cb:      Optional[Callable[[ProgressEvent], None]] = None,
    engagement_log_path: str = ENGAGEMENT_LOG_DEFAULT,
) -> FileProcessingResult:
    """Process one raw chat file end-to-end.

    Returns a FileProcessingResult with full diagnostics. Does NOT raise
    for cleanup-side errors — those are captured per-pair and aggregated
    onto the result. Only programmer / parse errors raise.
    """
    start = time.monotonic()
    result = FileProcessingResult(raw_path=raw_path)

    def emit(stage: str, **kwargs: Any) -> None:
        if progress_cb:
            progress_cb(ProgressEvent(raw_path=raw_path, stage=stage, **kwargs))

    # 1. Parse
    emit("parse")
    try:
        chat = parse_raw_chat_file(raw_path)
    except Exception as e:
        result.errors.append(f"parse failed: {e}")
        result.aborted = True
        result.abort_reason = "parse failed"
        result.duration_secs = time.monotonic() - start
        return result

    result.chat_title    = chat.metadata.title
    result.chat_platform = (chat.metadata.platform.value
                              if chat.metadata.platform else "unknown")
    pairs = chat.to_pairs()
    result.pairs_total = len(pairs)

    if not pairs:
        result.duration_secs = time.monotonic() - start
        return result

    # 2. Parallel cleanup
    emit("cleanup-start", total_pairs=len(pairs))
    cleaned: list[Optional[CleanedPair]] = [None] * len(pairs)

    chat_platform_str = (
        chat.metadata.platform.value if chat.metadata.platform else "unknown"
    )

    def _worker(i_pair):
        i, pair = i_pair
        return i, clean_pair(
            pair, vault_index=vault_index,
            anthropic_client=anthropic_client, config=config,
            source_path=raw_path,
            source_platform=chat_platform_str,
        )

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_worker, (i, p)) for i, p in enumerate(pairs)]
        for fut in as_completed(futures):
            try:
                i, cp = fut.result()
            except Exception as e:
                # Catastrophic worker failure — record but continue.
                result.errors.append(f"worker raised: {e}")
                continue
            cleaned[i] = cp
            emit("cleanup-done",
                  pair_num=cp.pair_num, total_pairs=len(pairs),
                  detail="errors=" + str(len(cp.errors)) if cp.errors else "ok")

    # 3. Aggregate per-pair stats + abort check
    errored_count = 0
    for cp in cleaned:
        if cp is None:
            errored_count += 1
            continue
        if cp.skipped:
            result.pairs_skipped += 1
            continue
        if cp.errors:
            errored_count += 1
            result.errors.extend(f"pair {cp.pair_num}: {e}" for e in cp.errors)
        else:
            result.pairs_succeeded += 1
        result.total_input_tokens  += cp.total_input_tokens
        result.total_output_tokens += cp.total_output_tokens
        result.total_cost_usd      += cp.total_cost_usd
    result.pairs_with_errors = errored_count

    if _should_abort(result.pairs_total, errored_count):
        result.aborted = True
        result.abort_reason = (
            f"error rate {errored_count}/{result.pairs_total} ≥ "
            f"{int(ABORT_ERROR_FRACTION * 100)}%"
        )
        result.duration_secs = time.monotonic() - start
        return result

    # 4. Sequential context-header build (thread tracker is order-sensitive)
    nonempty = [cp for cp in cleaned if cp is not None and not cp.skipped]
    headers: list[ContextHeader] = []
    tracker = ThreadTracker(conversation_id=chat.metadata.conversation_id
                              or os.path.basename(raw_path))
    for i, cp in enumerate(nonempty):
        h = build_context_header(chat, i, nonempty, tracker)
        headers.append(h)

    # 5. Write files + log engagement strips
    for cp, h in zip(nonempty, headers):
        try:
            path = write_cleaned_pair_file(
                cp, h, chat, output_dir=output_dir,
            )
            result.output_paths.append(path)
        except Exception as e:
            result.errors.append(f"write pair {cp.pair_num}: {e}")
            continue
        emit("write", pair_num=cp.pair_num,
              total_pairs=len(nonempty), detail=os.path.basename(path))
        if cp.engagement_strips:
            written = log_strips(
                cp.engagement_strips,
                context={
                    "source_path":    raw_path,
                    "source_chat":    chat.metadata.title,
                    "platform":       result.chat_platform,
                    "pair_num":       cp.pair_num,
                    "thread_id":      h.thread_id,
                },
                log_path=engagement_log_path,
            )
            result.engagement_strips_logged += written

    result.duration_secs = time.monotonic() - start
    emit("complete", total_pairs=len(pairs))
    return result


__all__ = [
    "ABORT_ERROR_FRACTION",
    "ABORT_MIN_FAILURES",
    "FileProcessingResult",
    "ProgressEvent",
    "process_chat_file",
]
