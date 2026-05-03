"""Path 2 orchestrator — emit conversation chunks from cleaned-pair files.

Phase 2 takes the persistent cleaned-pair archive (Phase 1 output) and
re-emits each cleaned pair as a Schema §12 conversation chunk plus a
Conversational RAG §2 ChromaDB record. The output lands in the same
folders the live pipeline writes to so historical and live chunks are
queryable side-by-side.

Per-pair flow:

    cleaned-pair file
        │
        ├─→ chunk markdown (~/Documents/conversations/)
        │     YAML §12 frontmatter + Context paragraphs + Exchange body
        │
        └─→ ChromaDB record (`conversations` collection)
              ~22-field metadata dict + embedded context-prefixed text

Per-session finalize: after all chunks for one source-chat group are
emitted, walk back through them and update `total_turns` /
`is_last_turn` on the last pair.

Chain assignment: each chunk's metadata carries `chain_id` and
`chain_label` lookup-derived from `chain-index.json` so RAG queries
can walk the complete arc a session belongs to.

Concurrency: file I/O + ChromaDB writes are serial within one session
(finalize order matters), but sessions run in a thread pool. The
ChromaDB embedding function (nomic via Ollama) is the throughput floor.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from orchestrator.conversation_chunk import (
    _extract_keywords,
    build_chroma_metadata,
    build_chunk_filename,
    build_chunk_markdown,
)
from orchestrator.historical.chain_detector import (
    derive_session_id,
)
from orchestrator.historical.cleaned_pair_reader import (
    CleanedPairFile,
    load_cleaned_pair,
)
from orchestrator.historical.paste_detection import process_user_input


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_CLEANED_PAIR_DIR  = "/Users/oracle/Documents/Commercial AI archives"
DEFAULT_CONVERSATIONS_DIR = "/Users/oracle/Documents/conversations"
# Live pipeline writes to ~/ora/chromadb/ — Phase 2 must match so
# historical chunks land in the same `conversations` collection that
# RAG queries hit.
DEFAULT_CHROMADB_PATH     = "/Users/oracle/ora/chromadb"

# nomic-embed-text-v1.5 has an 8192-token context. Conservative cap on
# embedded text so we don't blow it on long pairs (Bible quotes, book
# outlines, etc.). 10K chars handles dense content (code, non-ASCII,
# repeated tokens) that hits ~2 chars/token in the tokenizer. The chunk
# MARKDOWN file still carries the full text; only the EMBEDDED text
# used for RAG retrieval is truncated.
MAX_EMBED_CHARS = 10_000


# ---------------------------------------------------------------------------
# Result records
# ---------------------------------------------------------------------------


@dataclass
class SessionEmissionResult:
    """Outcome of emitting one session's chunks."""
    source_chat:       str
    session_id:        str
    chain_id:          str = ""
    chain_label:       str = ""
    pairs_total:       int = 0
    chunks_written:    int = 0
    chunks_indexed:    int = 0
    chunks_skipped:    int = 0
    output_paths:      list[str] = field(default_factory=list)
    chunk_ids:         list[str] = field(default_factory=list)
    errors:            list[str] = field(default_factory=list)
    duration_secs:     float = 0.0


# ---------------------------------------------------------------------------
# Context header composition
# ---------------------------------------------------------------------------


def _compose_context_header(cp: CleanedPairFile) -> str:
    """Build the embedded context paragraph for one chunk.

    Combines the cleaned-pair file's session_context + pair_context into
    a single block, falling back to a mechanical header if both are
    missing. Phase 1's cleanup wrote richer context paragraphs than the
    live pipeline's `_generate_chunk_metadata` does, so we use them
    verbatim — RAG embeddings benefit from the extra topical signal.
    """
    parts: list[str] = []
    if cp.session_context:
        parts.append(cp.session_context.strip())
    if cp.pair_context:
        parts.append(cp.pair_context.strip())
    if parts:
        return "\n\n".join(parts)
    # Fallback for pre-Phase-1 files (shouldn't happen in practice).
    return (
        f"Historical conversation chunk dated "
        f"{cp.source_timestamp.strftime('%Y-%m-%d') if cp.source_timestamp else 'unknown'} "
        f"from {cp.source_platform}."
    )


def _topics_from_pair(cp: CleanedPairFile, max_n: int = 5) -> list[str]:
    """Extract topic keywords from cleaned text for the chunk metadata."""
    text = cp.cleaned_user_input + "\n" + cp.cleaned_ai_response
    return _extract_keywords(text, max_n=max_n)


def _user_voice_only(cp: CleanedPairFile) -> str:
    """Extract just the user's personal-voice text from cleaned_user_input,
    excluding pasted content (news, opinion, resource, earlier-draft, other).

    Phase 1's paste detector segregates pasted from personal segments,
    but the cleaned-pair file's `cleaned_user_input` field interleaves
    both. To get a paste-free representation for RAG embedding, we
    re-run paste detection on the cleaned text and concatenate just
    the personal segments.

    The chunk file's body still contains the full text; this affects
    only the EMBEDDED representation that ChromaDB indexes for retrieval.
    Returns empty string when the entire user input is paste content
    (e.g. the user just pasted an article and asked for a take).
    """
    if not cp.cleaned_user_input:
        return ""
    segments = process_user_input(
        cp.cleaned_user_input,
        vault_index=None,                 # vault lookup not needed here
        source_platform=cp.source_platform,
    )
    personal_parts = [s.content for s in segments if s.kind == "personal"]
    return "\n\n".join(personal_parts).strip()


# ---------------------------------------------------------------------------
# Per-session emission
# ---------------------------------------------------------------------------


def _historical_model_id(platform: str) -> str:
    """Map source_platform → chunk model_id. We don't know the exact
    model that produced a 2025 ChatGPT response, so we use the platform
    name as a coarse-grained identifier."""
    return f"historical-{platform}" if platform else "historical-import"


def emit_chunks_for_session(
    cleaned_pair_paths: list[str],
    *,
    conversations_dir: str = DEFAULT_CONVERSATIONS_DIR,
    chromadb_path:     str = DEFAULT_CHROMADB_PATH,
    chain_id:          str = "",
    chain_label:       str = "",
    skip_if_chunk_exists: bool = True,
    chromadb_collection = None,
) -> SessionEmissionResult:
    """Emit chunk files + ChromaDB records for one source-chat session.

    `cleaned_pair_paths` MUST already be sorted by `source_pair_num`.
    The first cleaned-pair file in the list is loaded eagerly to
    establish session-wide identifiers (session_id, conversation_id,
    first_user_input).

    Pass `chromadb_collection` to share a pre-opened collection across
    sessions (avoids re-opening the persistent client for every session).
    Otherwise the function opens its own.
    """
    start = time.monotonic()
    if not cleaned_pair_paths:
        return SessionEmissionResult(
            source_chat="", session_id="",
            errors=["no cleaned-pair files in session"],
        )

    # Pre-load the first pair so we can derive session-wide identifiers
    # before processing the rest in order.
    try:
        first = load_cleaned_pair(cleaned_pair_paths[0])
    except Exception as e:
        return SessionEmissionResult(
            source_chat="", session_id="",
            errors=[f"failed to load first pair: {e}"],
        )

    source_chat       = first.source_chat
    conversation_id   = source_chat   # one chat = one conversation
    session_id        = derive_session_id(source_chat)
    source_platform   = first.source_platform
    first_user_input  = first.cleaned_user_input or first.cleaned_ai_response

    result = SessionEmissionResult(
        source_chat   = source_chat,
        session_id    = session_id,
        chain_id      = chain_id,
        chain_label   = chain_label,
        pairs_total   = len(cleaned_pair_paths),
    )

    # Open ChromaDB collection if not provided.
    owns_collection = False
    if chromadb_collection is None:
        try:
            import chromadb
            from orchestrator.embedding import get_or_create_collection
            client = chromadb.PersistentClient(path=str(chromadb_path))
            chromadb_collection = get_or_create_collection(client, "conversations")
            owns_collection = True
        except Exception as e:
            result.errors.append(f"open chromadb: {e}")
            result.duration_secs = time.monotonic() - start
            return result

    # Iterate pairs in order — finalize update at the end requires order.
    chroma_records: list[dict[str, Any]] = []
    last_when: Optional[datetime] = None

    os.makedirs(conversations_dir, exist_ok=True)
    seen_filenames: set[str] = set()

    for path in cleaned_pair_paths:
        try:
            cp = load_cleaned_pair(path)
        except Exception as e:
            result.errors.append(f"load {os.path.basename(path)}: {e}")
            continue

        when = cp.source_timestamp or datetime.now()
        last_when = when

        # Compose chunk filename. We need to distinguish two collision
        # cases:
        #   (a) intra-session collision — two pairs in THIS run share
        #       the same timestamp + slug. Disambiguate with `-pairNNN`.
        #   (b) re-run skip — a chunk file already exists from a PRIOR
        #       run. Skip if `skip_if_chunk_exists`, else upsert.
        # `seen_filenames` distinguishes them: a path in `seen_filenames`
        # was written in THIS run; a path not in it but on disk is from
        # a prior run.
        base_name = build_chunk_filename(
            when, cp.cleaned_user_input, cp.cleaned_ai_response,
        )
        chunk_path = os.path.join(conversations_dir, base_name)

        if chunk_path in seen_filenames:
            # Intra-session collision — suffix with pair number.
            stem, ext = os.path.splitext(base_name)
            chunk_path = os.path.join(
                conversations_dir,
                f"{stem}-pair{cp.source_pair_num:03d}{ext}",
            )

        # Skip-if-exists ONLY skips the file write (not the indexing).
        # ChromaDB upsert is idempotent — re-indexing an existing chunk
        # is safe, and this lets re-runs catch any pairs whose index
        # failed on a prior run (e.g. embedding-model errors).
        skip_write = (
            skip_if_chunk_exists
            and os.path.exists(chunk_path)
            and chunk_path not in seen_filenames
        )
        seen_filenames.add(chunk_path)

        # Build chunk content + metadata via the shared helpers.
        context_header = _compose_context_header(cp)
        topics         = _topics_from_pair(cp)
        topic_primary  = topics[0] if topics else ""

        if skip_write:
            # File already exists — don't rewrite, but still build
            # metadata + queue for indexing below.
            result.chunks_skipped += 1
            result.output_paths.append(chunk_path)
        else:
            try:
                chunk_md = build_chunk_markdown(
                    user_input    = cp.cleaned_user_input,
                    ai_response   = cp.cleaned_ai_response,
                    context_header= context_header,
                    when          = when,
                    tag           = "",
                )
            except Exception as e:
                result.errors.append(
                    f"build chunk md pair {cp.source_pair_num}: {e}"
                )
                continue

            try:
                with open(chunk_path, "w", encoding="utf-8") as f:
                    f.write(chunk_md)
                result.chunks_written += 1
                result.output_paths.append(chunk_path)
            except Exception as e:
                result.errors.append(
                    f"write {os.path.basename(chunk_path)}: {e}"
                )
                continue

        # Build ChromaDB metadata.
        try:
            meta = build_chroma_metadata(
                user_input        = cp.cleaned_user_input,
                ai_response       = cp.cleaned_ai_response,
                conversation_id   = conversation_id,
                session_id        = session_id,
                pair_num          = cp.source_pair_num,
                model_id          = _historical_model_id(source_platform),
                raw_path          = source_chat,
                chunk_path        = chunk_path,
                when              = when,
                first_user_input  = first_user_input,
                topic_primary     = topic_primary,
                topics            = topics,
                turn_summary      = cp.pair_context or context_header[:200],
                thread_id         = cp.thread_id,
                tag               = "",
                source_platform   = f"historical-{source_platform}",
                chain_id          = chain_id,
                chain_label       = chain_label,
            )
        except Exception as e:
            result.errors.append(
                f"build chroma meta pair {cp.source_pair_num}: {e}"
            )
            continue

        chunk_id = (
            f"session-{session_id}-pair-{cp.source_pair_num:03d}"
        )
        result.chunk_ids.append(chunk_id)

        # Embedded document text — paste-free user voice + context header.
        # We exclude pasted segments from the embedding so RAG queries
        # find the user's actual thinking, not pasted articles. The chunk
        # markdown file body still carries the full text including pastes
        # for visibility; only the embedded representation is paste-free.
        # If the user input was 100% paste (e.g. "[long article]"), we
        # fall back to context_header alone — at minimum the embedding
        # captures the conversation's session-level context.
        user_voice = _user_voice_only(cp)
        if user_voice:
            embedded_text = (
                f"{context_header}\n\n{user_voice}"
            )[:MAX_EMBED_CHARS]
        else:
            embedded_text = context_header[:MAX_EMBED_CHARS]
        chroma_records.append({
            "id":       chunk_id,
            "document": embedded_text,
            "metadata": meta,
        })

    # Bulk add to ChromaDB. ChromaDB upsert idempotency: ids are
    # deterministic, so re-running this orchestrator overwrites existing
    # records rather than duplicating them.
    if chroma_records:
        try:
            chromadb_collection.upsert(
                ids       = [r["id"]       for r in chroma_records],
                documents = [r["document"] for r in chroma_records],
                metadatas = [r["metadata"] for r in chroma_records],
            )
            result.chunks_indexed = len(chroma_records)
        except Exception:
            # One bad record (e.g. embedding-model context overflow)
            # would otherwise sink the whole batch. Fall back to per-
            # record upsert; on context-length overflow, halve the text
            # and retry until the record fits or is too short to mean
            # anything (last resort: just the context_header).
            indexed = 0
            for r in chroma_records:
                doc = r["document"]
                # Progressive truncation on context-length errors.
                attempt_chars = [len(doc), 6000, 4000, 2500, 1500, 800]
                last_err: Optional[Exception] = None
                for cap in attempt_chars:
                    try:
                        chromadb_collection.upsert(
                            ids=[r["id"]],
                            documents=[doc[:cap]],
                            metadatas=[r["metadata"]],
                        )
                        indexed += 1
                        last_err = None
                        break
                    except Exception as ee:
                        msg = str(ee).lower()
                        last_err = ee
                        if "context length" not in msg and "exceeds" not in msg:
                            break  # non-truncation error; don't retry
                if last_err is not None:
                    result.errors.append(
                        f"chromadb upsert {r['id']}: {str(last_err)[:200]}"
                    )
            result.chunks_indexed = indexed

    # Finalize: set total_turns + is_last_turn on the chunks for this
    # session. The shared closeout helper does the heavy lifting; we
    # only call it if at least one chunk was indexed in this run OR
    # this is the first run.
    if (result.chunks_indexed > 0 or result.chunks_skipped == result.pairs_total):
        try:
            from orchestrator.conversation_closeout import (
                _finalize_conversation_chunks,
            )
            _finalize_conversation_chunks(
                conversation_id, chromadb_path=Path(chromadb_path),
            )
        except Exception as e:
            # Closeout failures are non-fatal — chunk content + metadata
            # are still written; total_turns / is_last_turn just stay
            # at their initial values.
            result.errors.append(f"finalize: {e}")

    result.duration_secs = time.monotonic() - start
    return result


# ---------------------------------------------------------------------------
# Multi-session orchestration
# ---------------------------------------------------------------------------


def group_cleaned_pairs_by_session(
    cleaned_pair_files: list[str],
) -> dict[str, list[str]]:
    """Read each cleaned-pair file's frontmatter and group paths by
    `source_chat`. Returns a dict mapping source_chat → ordered list of
    cleaned-pair paths (sorted by source_pair_num)."""
    by_source: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for path in cleaned_pair_files:
        try:
            cp = load_cleaned_pair(path)
        except Exception:
            continue
        by_source[cp.source_chat].append((cp.source_pair_num, path))
    return {
        source: [p for _, p in sorted(items)]
        for source, items in by_source.items()
    }


def emit_chunks_for_all_sessions(
    sessions_to_paths: dict[str, list[str]],
    *,
    conversations_dir: str = DEFAULT_CONVERSATIONS_DIR,
    chromadb_path:     str = DEFAULT_CHROMADB_PATH,
    session_to_chain:  Optional[dict[str, str]] = None,
    chain_labels:      Optional[dict[str, str]] = None,
    max_workers:       int = 4,
    progress_cb:       Optional[Callable[[str, SessionEmissionResult], None]] = None,
) -> dict[str, SessionEmissionResult]:
    """Emit chunks for many sessions in parallel.

    `session_to_chain[session_id] → chain_id` and
    `chain_labels[chain_id] → human-readable label` come from
    `chain_detector.save_chain_index`. If absent, chunks emit with
    empty chain assignments (still useful but no chain navigation).

    Returns a dict mapping source_chat → SessionEmissionResult.
    """
    session_to_chain = session_to_chain or {}
    chain_labels     = chain_labels or {}
    results: dict[str, SessionEmissionResult] = {}

    # Open one ChromaDB collection and share it across workers (the
    # underlying client is thread-safe).
    try:
        import chromadb
        from orchestrator.embedding import get_or_create_collection
        client = chromadb.PersistentClient(path=str(chromadb_path))
        collection = get_or_create_collection(client, "conversations")
    except Exception as e:
        for source in sessions_to_paths:
            results[source] = SessionEmissionResult(
                source_chat=source,
                session_id=derive_session_id(source),
                errors=[f"open chromadb: {e}"],
            )
        return results

    def _process(source: str, paths: list[str]) -> tuple[str, SessionEmissionResult]:
        sid = derive_session_id(source)
        chain_id = session_to_chain.get(sid, "")
        chain_label = chain_labels.get(chain_id, "") if chain_id else ""
        r = emit_chunks_for_session(
            paths,
            conversations_dir   = conversations_dir,
            chromadb_path       = chromadb_path,
            chain_id            = chain_id,
            chain_label         = chain_label,
            chromadb_collection = collection,
        )
        return source, r

    if max_workers <= 1:
        for source, paths in sessions_to_paths.items():
            source, r = _process(source, paths)
            results[source] = r
            if progress_cb:
                progress_cb(source, r)
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [
                pool.submit(_process, src, paths)
                for src, paths in sessions_to_paths.items()
            ]
            for fut in as_completed(futures):
                source, r = fut.result()
                results[source] = r
                if progress_cb:
                    progress_cb(source, r)

    return results


__all__ = [
    "DEFAULT_CLEANED_PAIR_DIR",
    "DEFAULT_CONVERSATIONS_DIR",
    "DEFAULT_CHROMADB_PATH",
    "SessionEmissionResult",
    "emit_chunks_for_session",
    "emit_chunks_for_all_sessions",
    "group_cleaned_pairs_by_session",
]
