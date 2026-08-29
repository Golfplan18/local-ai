"""Shared helpers for building conversation chunks (live + historical).

Phase 5.8 introduced the canonical conversation-chunk shape:
  - vault YAML follows Schema §12 chunk template
  - ChromaDB metadata covers Conv RAG §2 fields (~22)

This module is the single source of truth. Both the live writer
(`server.py::_save_conversation`) and the historical Path 2 emitter
(`tools/path2_emitter.py`) call into the same helpers so chunks land
indistinguishable regardless of source.

Helpers exposed:
    _extract_entities, _extract_keywords, _compute_pair_hash
    _v3_tag_to_schema_tags
    build_chroma_metadata(...) → ~22-field dict
    build_chunk_markdown(...) → frontmatter + body string
    build_chunk_filename(...) → on-disk filename for the chunk
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Heuristic extractors (paragraph-level proper-noun regex + stop-word filter).
# Phase 5.8 ships these as fallbacks; the historical-pipeline framework
# redesign will replace them with model-based extraction.
# ---------------------------------------------------------------------------


_ENTITY_RE = re.compile(r"\b[A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*\b")

_STOP_WORDS = frozenset(
    "a an the this that these those is am are was were be been being have has "
    "had do does did will would shall should may might can could of in to for "
    "with on at by from as into through during before after above below between "
    "out off over under again further then once here there when where why how "
    "all each every both few more most other some such no nor not only own same "
    "so than too very just also still already even much many well really quite "
    "and but or if while because until although since what which who whom whose "
    "i me my we our you your he him his she her it its they them their using "
    "make sure going like get know think please help want need".split()
)


def _extract_entities(text: str, max_n: int = 10) -> list[str]:
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in _ENTITY_RE.finditer(text):
        ent = m.group(0).strip()
        if len(ent) < 2:
            continue
        key = ent.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(ent)
        if len(out) >= max_n:
            break
    return out


def _extract_keywords(text: str, max_n: int = 10) -> list[str]:
    if not text:
        return []
    words = re.findall(r"\b[a-zA-Z][a-zA-Z\-]{2,}\b", text.lower())
    seen: set[str] = set()
    out: list[str] = []
    for w in words:
        if w in _STOP_WORDS or w in seen:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= max_n:
            break
    return out


def _compute_pair_hash(user_input: str, ai_response: str) -> str:
    h = hashlib.sha256()
    h.update((user_input or "").encode("utf-8"))
    h.update(b"\n---\n")
    h.update((ai_response or "").encode("utf-8"))
    return h.hexdigest()[:16]


def _v3_tag_to_schema_tags(v3_tag: str) -> tuple[list[str], dict[str, bool]]:
    """V3 conversation-mode tag → Schema §3 controlled-vocabulary tags +
    Phase 5.3 boolean filter extracts.

    Mapping:
        "private" → tags=["private"], tag_private=True
        "stealth" → tags=[]            (mode flag, not a content tag)
        ""        → tags=[]
    """
    safe = v3_tag if v3_tag in ("", "stealth", "private") else ""
    tags: list[str] = []
    booleans = {
        "tag_archived":   False,
        "tag_incubating": False,
        "tag_private":    False,
    }
    if safe == "private":
        tags = ["private"]
        booleans["tag_private"] = True
    return tags, booleans


# ---------------------------------------------------------------------------
# Canonical chunk filename
# ---------------------------------------------------------------------------


_FILENAME_STOP_RE = re.compile(r"[^\w\s]+")


def _topic_slug_for_filename(user_input: str, ai_response: str = "",
                              max_words: int = 4) -> str:
    """Cheap topic-slug extraction for filenames. Mirrors the live
    server.py _topic_slug heuristic."""
    text = (user_input or "")[:500] + " " + (ai_response or "")[:500]
    text = _FILENAME_STOP_RE.sub(" ", text.lower())
    words = [w for w in text.split() if len(w) > 2 and w not in _STOP_WORDS]
    if not words:
        return "conversation"
    return "-".join(words[:max_words])


def build_chunk_filename(when: datetime, user_input: str,
                          ai_response: str = "") -> str:
    """Live conversations use ``YYYY-MM-DD_HH-MM_<topic-slug>.md`` —
    same shape used here so historical chunks live in the same dir
    without colliding."""
    date_str = when.strftime("%Y-%m-%d")
    time_str = when.strftime("%H-%M")
    slug = _topic_slug_for_filename(user_input, ai_response)
    return f"{date_str}_{time_str}_{slug}.md"


# ---------------------------------------------------------------------------
# Canonical chunk YAML + body
# ---------------------------------------------------------------------------


def build_chunk_markdown(
    user_input: str,
    ai_response: str,
    context_header: str,
    *,
    when: datetime,
    tag: str = "",
    turn_privacy: str | None = None,
) -> str:
    """Compose the full chunk markdown file — Schema §12 YAML frontmatter
    followed by the Context + Exchange body."""
    schema_tags, _ = _v3_tag_to_schema_tags(tag)
    try:
        from orchestrator.vault_export import _build_canonical_frontmatter
        frontmatter = _build_canonical_frontmatter(
            nexus=[],
            type_="chat",
            tags=schema_tags,
            created_at=when.strftime("%Y-%m-%d %H:%M:%S"),
            modified_at=when,
        )
    except Exception:
        # Fallback: emit canonical YAML inline without the helper.
        date_str = when.strftime("%Y-%m-%d")
        tags_yaml = "tags:\n" + "".join(f"  - {t}\n" for t in schema_tags) if schema_tags else "tags:\n"
        frontmatter = (
            f"---\n"
            f"nexus:\n"
            f"type: chat\n"
            f"{tags_yaml}"
            f"date created: {date_str}\n"
            f"date modified: {date_str}\n"
            f"---\n"
        )
    if turn_privacy is not None and turn_privacy not in {
        "standard", "private", "stealth",
    }:
        raise ValueError("turn_privacy must be standard, private, or stealth")
    authority_marker = (
        "<!-- ora-turn-privacy: "
        + json.dumps(turn_privacy, ensure_ascii=False)
        + " -->\n\n"
        if turn_privacy is not None else ""
    )
    return (
        f"{frontmatter}\n"
        f"{authority_marker}"
        f"## Context\n\n"
        f"{context_header}\n\n"
        f"## Exchange\n\n"
        f"**User:**\n\n"
        f"{user_input}\n\n"
        f"**Assistant:**\n\n"
        f"{ai_response}\n"
    )


def build_retrieval_document(
    context_header: str,
    user_input: str,
    ai_response: str,
) -> str:
    """Complete per-turn Chroma document; both speakers are retrievable."""
    return (
        f"## Context\n\n{context_header}\n\n"
        f"## Exchange\n\n"
        f"**User:**\n\n{user_input}\n\n"
        f"**Assistant:**\n\n{ai_response}"
    )


def build_embedding_orientation(context_header: str, user_input: str) -> str:
    """Query-facing orientation kept separate from the complete document."""
    return f"{context_header}\n\n{user_input}"


def attach_chunk_ownership(
    markdown: str, *, conversation_id: str, chunk_id: str,
) -> str:
    """Insert redundant exact ownership markers immediately after YAML."""
    if not isinstance(conversation_id, str) or not conversation_id:
        raise ValueError("conversation_id must be a non-empty string")
    if not isinstance(chunk_id, str) or not chunk_id:
        raise ValueError("chunk_id must be a non-empty string")
    frontmatter = re.match(r"\A---\s*\n.*?\n---\s*\n", markdown, re.DOTALL)
    if frontmatter is None:
        raise ValueError("conversation chunk has no YAML frontmatter")
    markers = (
        "<!-- ora-conversation-id: "
        + json.dumps(conversation_id, ensure_ascii=False)
        + " -->\n<!-- ora-chunk-id: "
        + json.dumps(chunk_id, ensure_ascii=False)
        + " -->\n\n"
    )
    return markdown[:frontmatter.end()] + markers + markdown[frontmatter.end():]


def append_chunk_manifest(
    *,
    conversation_id: str,
    chunk_id: str,
    chunk_path: str | Path,
    tag: str = "",
    turn_privacy: str | None = None,
    turn_index: int | None = None,
    raw_path: str = "",
    source_path: str = "",
    manifest_path: str | Path | None = None,
) -> Path:
    """Append the standard typed chunk ownership record under a shared lock."""
    try:
        from orchestrator import runtime_paths as rp
    except ImportError:  # pragma: no cover - legacy top-level import context
        import runtime_paths as rp  # type: ignore

    destination = (
        Path(manifest_path) if manifest_path is not None
        else Path(rp.DATA_DIR_STR) / "conversation-manifest.jsonl"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    absolute_chunk = Path(chunk_path).expanduser().absolute()
    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "conversation_id": conversation_id,
        "chunk_id": chunk_id,
        "chunk_path": str(absolute_chunk),
        "chunk_root": str(absolute_chunk.parent),
        "artifact_kind": "conversation_chunk",
        "managed_by": "ora",
        "raw_path": raw_path,
        # Imported source archives are user-owned inputs. Keep their path as
        # provenance, never in raw_path (which lifecycle treats as an
        # Ora-managed raw-log deletion pointer).
        "source_path": source_path,
        "tag": tag,
    }
    if turn_privacy is not None:
        if turn_privacy not in {"standard", "private", "stealth"}:
            raise ValueError("invalid turn_privacy")
        record["turn_privacy"] = turn_privacy
    if turn_index is not None:
        if isinstance(turn_index, bool) or not isinstance(turn_index, int) or turn_index < 1:
            raise ValueError("turn_index must be a positive integer")
        record["turn_index"] = turn_index
    with rp.locked_file(destination):
        rp.append_text_no_follow(
            destination,
            json.dumps(record, ensure_ascii=False) + "\n",
        )
    return destination


# ---------------------------------------------------------------------------
# Canonical ChromaDB metadata (~22 Conv RAG §2 fields + V3 compat)
# ---------------------------------------------------------------------------


def build_chroma_metadata(
    user_input: str,
    ai_response: str,
    *,
    conversation_id: str,
    session_id: str,
    pair_num: int,
    model_id: str,
    raw_path: str,
    chunk_path: str,
    when: datetime,
    first_user_input: str,
    topic_primary: str,
    topics: list[str],
    turn_summary: str,
    thread_id: str,
    tag: str = "",
    turn_privacy: str | None = None,
    source_platform: str = "local",
    chain_id: str = "",
    chain_label: str = "",
) -> dict[str, Any]:
    """Compose the ~22-field ChromaDB metadata dict for one chunk.

    `total_turns` initializes to `pair_num` (current count). The
    close-out finalizer updates it later. `is_last_turn` is False at
    save; close-out sets True on the final pair.

    `chain_id` / `chain_label` carry the Phase 2B chain assignment so
    RAG queries can walk the entire arc a session belongs to. Default
    empty (live conversations don't yet carry chain assignments).
    """
    schema_tags, tag_booleans = _v3_tag_to_schema_tags(tag)
    if turn_privacy is not None and turn_privacy not in {
        "standard", "private", "stealth",
    }:
        raise ValueError("invalid turn_privacy")

    try:
        ts_local = when.strftime("%Y-%m-%dT%H:%M:%S")
        ts_utc = when.astimezone(timezone.utc).isoformat(timespec="seconds")
    except Exception:
        ts_local = when.isoformat(timespec="seconds")
        ts_utc = ts_local

    # This metadata rides one exact exchange. A Dialogue-wide first turn may
    # be Private even when the current row is Standard, so only the owned user
    # text may supply its searchable title.
    conversation_title = (user_input or "")[:80].strip()
    if not conversation_title:
        conversation_title = f"Session {session_id}"

    combined_text = f"{user_input}\n{ai_response}"
    entities = _extract_entities(combined_text)
    keywords = _extract_keywords(combined_text)
    references_turns = [pair_num - 1] if pair_num > 1 else []

    meta: dict[str, Any] = {
        # Temporal
        "timestamp_utc":      ts_utc,
        "date":               when.strftime("%Y-%m-%d"),
        "year":               int(when.year),
        "month":              int(when.month),

        # Identity
        "conversation_id":    conversation_id,
        "conversation_title": conversation_title,
        "session_id":         session_id,

        # Structure
        "turn_index":         pair_num,
        "total_turns":        pair_num,    # finalized at close-out
        "chunk_type":         "turn_pair",
        "is_first_turn":      pair_num == 1,
        "is_last_turn":       False,        # finalized at close-out

        # Content
        "topic_primary":      topic_primary,
        "turn_summary":       turn_summary,

        # Source / origin
        "source_platform":    source_platform,
        "model_id":           model_id,

        # Thread continuity
        "thread_id":          thread_id,

        # Pipeline
        "obsidian_path":      chunk_path,
        "file_hash":          _compute_pair_hash(user_input, ai_response),

        # Type + Phase 5.3 filter booleans + V3 close-out compatibility
        "type":               "chat",
        "tag":                tag,
        "agent_id":           "user",
        "chunk_path":         chunk_path,
        "raw_path":           raw_path,
        "model_used":         model_id,
        "timestamp":          ts_local,
        "pair_num":           pair_num,
        "source":             os.path.basename(chunk_path),
    }
    if turn_privacy is not None:
        meta["turn_privacy"] = turn_privacy
    meta.update(tag_booleans)

    # ChromaDB rejects empty list metadata; only emit non-empty lists.
    if topics:
        meta["topic_tags"] = topics
        meta["topics"]     = ", ".join(topics)
    if entities:
        meta["entities"]   = entities
    if keywords:
        meta["keywords"]   = keywords
    if references_turns:
        meta["references_turns"] = references_turns
    # Chain (Phase 2B). Only emit when assigned — live conversations
    # default to no chain.
    if chain_id:
        meta["chain_id"]    = chain_id
        meta["chain_label"] = chain_label

    return meta


# ---------------------------------------------------------------------------
# Mechanical metadata fallback (no model)
# ---------------------------------------------------------------------------


def mechanical_chunk_metadata(
    user_input: str,
    ai_response: str,
    *,
    conversation_id: str,
    model_id: str,
    pair_num: int,
    when: datetime,
) -> tuple[str, list[str]]:
    """Produce a (context_header, topics) pair without invoking a model.

    Used when the historical-import pipeline runs without the framework
    redesign's model-based cleanup. Returns a one-paragraph header
    derived from the user input plus a small list of topic words.
    """
    preview = (user_input or "")[:140].rstrip()
    if user_input and len(user_input) > 140:
        preview += "..."
    date_str = when.strftime("%Y-%m-%d")
    header = (
        f"Historical conversation chunk dated {date_str} from conversation "
        f"'{conversation_id[:32]}' under model {model_id}. "
        f"Turn {pair_num} of an archived exchange. "
        f"The user asked: {preview}"
    )
    topics = _extract_keywords(user_input or "", max_n=3)
    return header, topics


__all__ = [
    "_extract_entities",
    "_extract_keywords",
    "_compute_pair_hash",
    "_v3_tag_to_schema_tags",
    "build_chunk_filename",
    "build_chunk_markdown",
    "attach_chunk_ownership",
    "append_chunk_manifest",
    "build_chroma_metadata",
    "mechanical_chunk_metadata",
    "build_retrieval_document",
    "build_embedding_orientation",
]
