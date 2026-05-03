"""Path 2 — historical conversation re-emission.

The Document Processing framework defines Path 1 (atomic note
extraction) and Path 2 (conversation re-emission as chunks). This
module implements Path 2: take a parsed historical chat, walk its
prompt+response pairs, and emit one chunk file plus one ChromaDB
record per pair using the canonical Schema §12 + Conv RAG §2 shapes
that live `_save_conversation` produces.

Goal: chunks land **indistinguishable** from the live pipeline —
historical timestamps preserved, full metadata schema populated,
finalize step sets total_turns / is_last_turn at the end of each
conversation.

The emitter exposes pluggable pre-process stages (paste detection,
transcription cleanup, Phase A cleanup). Today they're no-ops; the
historical-import framework redesign will plug in real implementations.
The wiring stays the same — only the stage bodies change.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from orchestrator.conversation_chunk import (
    build_chroma_metadata,
    build_chunk_filename,
    build_chunk_markdown,
    mechanical_chunk_metadata,
)


# ---------------------------------------------------------------------------
# Pluggable pre-process stages — no-ops today; framework work later.
# ---------------------------------------------------------------------------


@dataclass
class Pair:
    """A normalized prompt+response pair flowing through the emitter."""
    user_input:    str
    ai_response:   str
    when:          datetime
    pair_num:      int = 0
    skip_reason:   str = ""             # set by stages to skip this pair
    annotations:   dict = field(default_factory=dict)  # stage outputs


# A stage takes a Pair and returns a (possibly modified) Pair.
# Stages may set pair.skip_reason to drop the pair from emission.
PreProcessStage = Callable[[Pair], Pair]


def _noop_stage(pair: Pair) -> Pair:
    """Default stage — pass-through."""
    return pair


def default_pre_process_stages() -> list[PreProcessStage]:
    """No-op stages today. The historical-import framework redesign
    replaces these with paste-detection, transcription-cleanup, and
    Phase A cleanup implementations."""
    return [_noop_stage]


# ---------------------------------------------------------------------------
# Pair extraction
# ---------------------------------------------------------------------------


def _parse_timestamp(value: Any, default: datetime) -> datetime:
    """Best-effort timestamp parse. Accepts datetime, ISO string, or
    'YYYY-MM-DD HH:MM:SS' string. Falls back to `default` on any error."""
    if isinstance(value, datetime):
        return value
    if not value:
        return default
    if not isinstance(value, str):
        return default
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(value[:len(fmt) + 4], fmt)
        except (ValueError, TypeError):
            continue
    return default


def pairs_from_messages(messages: list[dict],
                         default_when: Optional[datetime] = None
                         ) -> Iterable[Pair]:
    """Iterate User/Assistant pairs from a parsed message list.

    Each `messages[i]` is expected to be a dict with at least
    `role` ('user' or 'assistant') and `content`. `timestamp` is
    optional; falls back to `default_when` (default: now()).

    Skips orphan user messages (no following assistant) and orphan
    assistants. Pairs are numbered 1, 2, 3... in order.
    """
    default_when = default_when or datetime.now()
    pair_num = 0
    pending_user: Optional[dict] = None
    for msg in messages:
        role = (msg.get("role") or "").lower()
        if role == "user":
            pending_user = msg
        elif role == "assistant" and pending_user is not None:
            pair_num += 1
            ts = _parse_timestamp(msg.get("timestamp")
                                  or pending_user.get("timestamp"),
                                  default_when)
            yield Pair(
                user_input=str(pending_user.get("content") or ""),
                ai_response=str(msg.get("content") or ""),
                when=ts,
                pair_num=pair_num,
            )
            pending_user = None
        # Other roles (system, tool) ignored.


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------


def _derive_session_id(conversation_id: str, raw_path: str) -> str:
    """Stable session_id for a historical conversation. Hashes the
    conversation_id + raw_path so re-running the emitter produces the
    same session_id (and thus the same ChromaDB ids) — supports
    resumable processing."""
    h = hashlib.sha256()
    h.update((conversation_id or "").encode("utf-8"))
    h.update(b"|")
    h.update((raw_path or "").encode("utf-8"))
    return h.hexdigest()[:6]


def _thread_id(conversation_id: str, counter: int) -> str:
    return f"thread_{(conversation_id or '')[:8]}_{counter:03d}"


def emit_path2_chunks(
    messages: list[dict],
    *,
    conversation_id: str,
    raw_path: str,
    conversations_dir: str,
    chromadb_path: str,
    model_id: str = "historical-import",
    source_platform: str = "historical-import",
    tag: str = "",
    pre_process_stages: Optional[list[PreProcessStage]] = None,
    finalize: bool = True,
    default_when: Optional[datetime] = None,
) -> dict[str, Any]:
    """Re-emit a historical chat as conversation chunks (Path 2).

    Args:
        messages: parsed message list (from vault_export._parse_raw_session_log
            or any equivalent format conversion).
        conversation_id: identifier for this historical conversation. Used
            as the panel_id-equivalent in the chunks' metadata so close-out
            and RAG queries can group chunks together.
        raw_path: path to the source markdown (recorded on each chunk for
            close-out + audit).
        conversations_dir: directory where chunk markdown files land.
        chromadb_path: chromadb persistent client path.
        model_id: producer model name (default 'historical-import').
        source_platform: provenance label (default 'historical-import').
        tag: V3 conversation-mode flag ('', 'stealth', 'private').
        pre_process_stages: optional list of pre-process callables. Defaults
            to no-ops; framework redesign plugs in real stages.
        finalize: if True, walk the emitted chunks at the end and update
            total_turns + is_last_turn. (Set False for tests that want
            to inspect the pre-finalize state.)
        default_when: timestamp to use for pairs lacking one (default: now()).

    Returns a stats dict.
    """
    stages = pre_process_stages or default_pre_process_stages()
    os.makedirs(conversations_dir, exist_ok=True)
    session_id = _derive_session_id(conversation_id, raw_path)

    stats = {
        "chunks_written":         0,
        "chunks_indexed":         0,
        "skipped_pairs":          0,
        "errors":                 [],
        "first_pair_timestamp":   None,
        "last_pair_timestamp":    None,
        "session_id":             session_id,
        "conversation_id":        conversation_id,
    }

    # Track thread continuity across the conversation.
    prior_topic: Optional[str] = None
    thread_counter: int = 0
    first_user_input: Optional[str] = None
    final_pair_num = 0
    chroma_records: list[dict[str, Any]] = []

    for pair in pairs_from_messages(messages, default_when):
        if first_user_input is None:
            first_user_input = pair.user_input
        if stats["first_pair_timestamp"] is None:
            stats["first_pair_timestamp"] = pair.when.isoformat(timespec="seconds")

        # Run pre-process stages. Any stage may set skip_reason.
        for stage in stages:
            try:
                pair = stage(pair)
            except Exception as e:
                stats["errors"].append(f"stage {stage.__name__} pair {pair.pair_num}: {e}")
            if pair.skip_reason:
                break

        if pair.skip_reason:
            stats["skipped_pairs"] += 1
            continue

        # Generate metadata. Mechanical fallback today; framework will
        # swap to model-based extraction.
        context_header, topics = mechanical_chunk_metadata(
            pair.user_input,
            pair.ai_response,
            conversation_id=conversation_id,
            model_id=model_id,
            pair_num=pair.pair_num,
            when=pair.when,
        )
        topic_primary = topics[0] if topics else ""

        # Thread continuity — increment when topic_primary changes.
        if topic_primary != prior_topic:
            thread_counter += 1
        prior_topic = topic_primary

        # Compose chunk file content + filename.
        chunk_filename = build_chunk_filename(pair.when, pair.user_input,
                                                pair.ai_response)
        chunk_path = os.path.join(conversations_dir, chunk_filename)
        # Filename collision guard (multiple pairs same minute + slug).
        if os.path.exists(chunk_path):
            stem, ext = os.path.splitext(chunk_filename)
            chunk_filename = f"{stem}-pair{pair.pair_num:03d}{ext}"
            chunk_path = os.path.join(conversations_dir, chunk_filename)

        chunk_markdown = build_chunk_markdown(
            user_input=pair.user_input,
            ai_response=pair.ai_response,
            context_header=context_header,
            when=pair.when,
            tag=tag,
        )

        try:
            with open(chunk_path, "w", encoding="utf-8") as f:
                f.write(chunk_markdown)
            stats["chunks_written"] += 1
        except Exception as e:
            stats["errors"].append(f"write chunk {chunk_path}: {e}")
            continue

        chunk_id = f"session-{session_id}-pair-{pair.pair_num:03d}"
        meta = build_chroma_metadata(
            user_input=pair.user_input,
            ai_response=pair.ai_response,
            conversation_id=conversation_id,
            session_id=session_id,
            pair_num=pair.pair_num,
            model_id=model_id,
            raw_path=raw_path,
            chunk_path=chunk_path,
            when=pair.when,
            first_user_input=first_user_input or pair.user_input,
            topic_primary=topic_primary,
            topics=topics,
            turn_summary=context_header,
            thread_id=_thread_id(conversation_id, thread_counter),
            tag=tag,
            source_platform=source_platform,
        )
        # Attach annotations from any stage that wanted to mark the chunk.
        if pair.annotations:
            for k, v in pair.annotations.items():
                if k not in meta:
                    meta[k] = v

        chroma_records.append({
            "id":       chunk_id,
            "document": f"{context_header}\n\n{pair.user_input}",
            "metadata": meta,
        })
        stats["last_pair_timestamp"] = pair.when.isoformat(timespec="seconds")
        final_pair_num = pair.pair_num

    # Bulk-add to ChromaDB. Failures here don't roll back the file
    # writes — the chunk files are the source of truth; the index can
    # be rebuilt.
    if chroma_records:
        try:
            import chromadb
            from orchestrator.embedding import get_or_create_collection
            client = chromadb.PersistentClient(path=str(chromadb_path))
            # Bind the canonical embedding_function so historical chunks
            # are embedded the same way live ones are.
            col = get_or_create_collection(client, "conversations")
            col.add(
                ids=[r["id"] for r in chroma_records],
                documents=[r["document"] for r in chroma_records],
                metadatas=[r["metadata"] for r in chroma_records],
            )
            stats["chunks_indexed"] = len(chroma_records)
        except Exception as e:
            stats["errors"].append(f"chromadb add: {e}")

    # Finalize: set total_turns + is_last_turn on the chunks we just wrote.
    if finalize and stats["chunks_indexed"] > 0:
        try:
            from orchestrator.conversation_closeout import _finalize_conversation_chunks
            finalize_result = _finalize_conversation_chunks(
                conversation_id, chromadb_path=Path(chromadb_path),
            )
            stats["finalize"] = finalize_result
        except Exception as e:
            stats["errors"].append(f"finalize: {e}")

    stats["final_pair_num"] = final_pair_num
    return stats


__all__ = [
    "Pair",
    "PreProcessStage",
    "default_pre_process_stages",
    "pairs_from_messages",
    "emit_path2_chunks",
]
