#!/usr/bin/env python3
"""
Ora Conversation File Format — Pydantic schema for the V3 chunk file YAML
and the conversation.json envelope, per V3 Backlog 2C (resolved 2026-04-28,
schema documented 2026-04-30).

This module is documentation-as-code. The actual save / load logic lives in:

  * ``orchestrator/conversation_memory.py`` — load and save the
    ``conversation.json`` envelope; turn append; tag retrieval; sidebar
    enumeration; mark read / errored; rename / pin; fork; ensure WELCOME.
  * ``server/server.py::_save_conversation`` — write per-turn chunk files
    (markdown body + YAML frontmatter) and index them into the ChromaDB
    ``conversations`` collection.
  * ``server/server.py`` endpoints — read both surfaces for the sidebar
    list, output pane, retry, dismiss, etc.

The models below are the canonical shape for each storage surface. They are
**not** wired into the existing runtime code — the existing code is
permissive by design (see backwards-compat notes below). The models are the
authoritative record of "what fields exist and what they mean," and they
provide a foundation for future runtime validation, JSON Schema generation
(via ``.model_json_schema()``), or test harnesses.

Three storage surfaces, in order of authority:

  1. **Per-conversation envelope** (source of truth) —
     ``~/ora/sessions/{conversation_id}/conversation.json``.
     JSON. See :class:`ConversationEnvelope` and :class:`Turn`.

  2. **Per-turn chunk file** (denormalized cache for retrieval + audit) —
     ``~/Documents/conversations/{date}_{time}_{slug}.md``.
     YAML frontmatter + markdown body. See :class:`ChunkYAML`,
     :class:`ChunkBodyOk`, :class:`ChunkBodyErrored`.

  3. **ChromaDB ``conversations`` collection** (denormalized cache for
     embedding-based RAG). See :class:`ChromaDBChunkMetadata`.

The conversation envelope is the source of truth. Both the chunk file and
the ChromaDB row can be rebuilt from the envelope plus the raw session log
fragment under ``~/Documents/conversations/raw/``.

Round-trip example::

    from orchestrator.conversation_file_format import (
        ChunkYAML, ConversationEnvelope, Turn, ChromaDBChunkMetadata,
    )

    yaml_doc = ChunkYAML(
        chunk_id="session-abcdef-pair-001",
        session_id="abcdef",
        turn_range="1",
        source_file="2026-04-30_15-15_first-prompt.md",
        source_platform="local",
        model_used="local-mlx-gpt-oss-120b",
        timestamp="2026-04-30T15:15:00",
        topics=["greeting", "first"],
        status="ok",
        tag="",
    )
    print(yaml_doc.model_dump_json(indent=2))
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# ── Constants ──────────────────────────────────────────────────────────────

# Conversation-level mode (V3 Phase 1.1). Set at conversation creation,
# immutable for the life of the conversation. Stealth conversations purge
# on close. Private conversations retain-and-flag. Standard ("") is the
# default and behaves like classic Ora.
ConversationTag = Literal["", "stealth", "private"]
VALID_CONVERSATION_TAGS: tuple[str, ...] = ("", "stealth", "private")

# Per-chunk pipeline outcome (V3 Backlog 2C / 2D). "ok" is the default
# when the field is absent in legacy chunks. "errored" indicates the
# pipeline could not complete after exhausting its self-correction
# (verifier PASS/FAIL, Gear 3 correction cycles, MAX_ITERATIONS).
ChunkStatus = Literal["ok", "errored"]
VALID_CHUNK_STATUSES: tuple[str, ...] = ("ok", "errored")

# The three optional turn fields WP-5.3 persists. Always present (never
# absent) on writes from save_turn_spatial_state, but legacy turns may
# omit them — readers default to None. Mirrors
# conversation_memory.TURN_SPATIAL_FIELDS.
TURN_SPATIAL_FIELDS: tuple[str, ...] = (
    "spatial_representation",
    "annotations",
    "vision_extraction_result",
)


# ── Per-turn chunk file (markdown + YAML frontmatter) ──────────────────────


class ChunkYAML(BaseModel):
    """YAML frontmatter shape for a per-turn chunk file.

    Files live at ``~/Documents/conversations/{date}_{time}_{slug}.md``.
    The YAML frontmatter sits above a markdown body. Body shape depends
    on ``status``:

      * ``status: ok`` → ``## Context`` then ``## Exchange``
        (with **User:** / **Assistant:** subsections). See
        :class:`ChunkBodyOk`.
      * ``status: errored`` → adds ``## Failure`` and
        ``## Recommendation`` sections. See :class:`ChunkBodyErrored`.

    The chunk file is a denormalized cache. The conversation.json
    envelope is the source of truth for everything except topics +
    contextual header (those are produced once at chunk-write time
    by the sidebar model).
    """

    # ── Core identity ──────────────────────────────────────────────────────

    chunk_id: str = Field(
        description=(
            "Globally unique chunk identifier. "
            "Format: ``session-{6-char-session-id}-pair-{NNN}``. "
            "Used as the ChromaDB row id and as the unambiguous "
            "fork-ancestry pointer in the envelope's "
            "``fork_point_chunk_id``."
        )
    )
    session_id: str = Field(
        description=(
            "Per-pipeline-session unique ID, server-generated as a 6-char "
            "hex string. NOT the same as ``conversation_id`` — "
            "``session_id`` covers a single ``_save_conversation`` "
            "session (resets when ``is_new_session=True``); "
            "``conversation_id`` covers the whole conversation directory."
        )
    )
    turn_range: str = Field(
        description=(
            "Pair number within this session, written as a string for "
            'YAML compat (e.g., "1", "23"). Resets across sessions, so '
            "use ``chunk_id`` for unambiguous global ordering."
        )
    )

    # ── Provenance ─────────────────────────────────────────────────────────

    source_file: str = Field(
        description=(
            "Filename (not full path) of the raw session log this chunk "
            "was sliced from. Always lives in "
            "``~/Documents/conversations/raw/``."
        )
    )
    source_platform: Literal["local"] = Field(
        description=(
            "Platform tag. Currently always ``local`` since chunks come "
            "from the local pipeline."
        )
    )
    model_used: str = Field(
        description=(
            "The model identifier from ``config/endpoints.json`` that "
            "produced the assistant response."
        )
    )
    timestamp: str = Field(
        description="ISO 8601 timestamp with second precision."
    )
    topics: list[str] = Field(
        default_factory=list,
        description=(
            "Auto-extracted topic tags from the user prompt + AI response. "
            "Generated by the sidebar model with mechanical fallback. "
            "Used for browse + light-weight retrieval. Stored as a YAML "
            "list in the chunk file; written to ChromaDB metadata as a "
            "comma-joined string (Chroma does not allow list values)."
        )
    )

    # ── V3 Backlog 2C additions ────────────────────────────────────────────

    status: ChunkStatus = Field(
        default="ok",
        description=(
            "Pipeline outcome. Defaults to ``ok`` when absent (legacy "
            "chunks). ``errored`` indicates the pipeline could not "
            "complete after exhausting its self-correction (verifier "
            "PASS/FAIL protocol, Gear 3 correction cycles capped at 2, "
            "MAX_ITERATIONS=10 on tool loops). Errored chunks carry the "
            "two extra body sections from :class:`ChunkBodyErrored`."
        )
    )
    tag: ConversationTag = Field(
        default="",
        description=(
            "Conversation-level mode (V3 Phase 1.2). Denormalized from "
            "the envelope's ``tag``, which is the source of truth. "
            "RAG queries filter on this without joining against "
            "conversation.json. Values: empty (standard), ``stealth``, "
            "``private``."
        )
    )


class ChunkBodyOk(BaseModel):
    """Body sections for an ``ok``-status chunk.

    Two markdown sections under H2 headings::

        ## Context

        <context>

        ## Exchange

        **User:**

        <user_input>

        **Assistant:**

        <ai_response>
    """

    context: str = Field(
        description=(
            "Sentence-form summary of the turn, generated by the sidebar "
            "model with mechanical fallback. Used as the embedding text "
            "for ChromaDB indexing alongside the user prompt."
        )
    )
    user_input: str = Field(
        description="The user's prompt verbatim."
    )
    ai_response: str = Field(
        description="The assistant's response verbatim."
    )


class ChunkBodyErrored(ChunkBodyOk):
    """Body sections for an ``errored``-status chunk.

    All :class:`ChunkBodyOk` sections plus two additional sections for
    failure diagnosis. The errored body shape is designed but the
    write path is not yet implemented in ``_save_conversation`` —
    today the envelope's ``last_status`` field is the only signal. See
    Backlog 2D for the implementation handoff.
    """

    failure: str = Field(
        description=(
            "The failure trace from the pipeline. Stored verbatim so the "
            "user can see what went wrong. Rendered under ``## Failure``."
        )
    )
    recommendation: str = Field(
        description=(
            "AI-generated diagnosis of the failure plus a suggested next "
            "step. Generated by the local-fast model so the user does "
            'not have to ask "what now?". Rendered under '
            "``## Recommendation``."
        )
    )


# ── Per-conversation envelope (conversation.json) ──────────────────────────


class Turn(BaseModel):
    """A single message in the envelope's ``messages[]`` list.

    User turns may carry the three optional spatial fields. Assistant
    turns currently always have them set to ``None`` (reserved — future
    assistants may emit spatial state too). Keys are always present
    (never absent) on writes from ``save_turn_spatial_state`` so
    downstream code can rely on the shape; legacy turns may omit them
    and readers default to ``None``.
    """

    role: Literal["user", "assistant", "system"] = Field(
        description="Speaker. ``system`` is reserved for future use."
    )
    content: str = Field(
        description="The verbatim text of the turn."
    )
    timestamp: Optional[str] = Field(
        default=None,
        description=(
            "ISO 8601 timestamp; may be ``None`` for legacy turns "
            "(written before timestamping was added)."
        )
    )
    spatial_representation: Optional[dict] = Field(
        default=None,
        description=(
            "Konva canvas state captured per-turn (WP-5.3). Schema lives "
            "at ``~/ora/config/schemas/canvas-state.schema.json``. "
            "Persisted so the next turn's prompt can include the "
            "PRIOR-STATE fence with layout-preservation guidance."
        )
    )
    annotations: Optional[list] = Field(
        default=None,
        description=(
            "User-drawn annotations on the canvas (WP-5.3). List of "
            "callout / highlight / strikethrough / sticky / pen "
            "objects produced by ``annotation-parser.js``."
        )
    )
    vision_extraction_result: Optional[dict] = Field(
        default=None,
        description=(
            "Vision-model extraction output for image-bearing turns "
            "(WP-5.3). Populated when a vision-capable model processes "
            "an uploaded image."
        )
    )


class ConversationEnvelope(BaseModel):
    """Shape of ``~/ora/sessions/{conversation_id}/conversation.json``.

    Source of truth for everything the V3 sidebar / output pane needs to
    know about a conversation. Chunk files and ChromaDB metadata are
    denormalized caches that can be rebuilt from this envelope plus the
    raw session log fragment.
    """

    # ── Identity ───────────────────────────────────────────────────────────

    conversation_id: str = Field(
        description=(
            "The directory name under ``~/ora/sessions/``. Stable across "
            "the conversation's lifetime. Also written explicitly into "
            "the envelope so the file is self-describing if relocated."
        )
    )
    display_name: str = Field(
        default="",
        description=(
            "User-editable surface name shown in the sidebar and output "
            "pane header. Auto-generated from the first prompt "
            "(60 char trim) on first save; user-editable via "
            "``POST /api/conversation/<id>/rename``. Empty string falls "
            "back to a derived title at render time."
        )
    )

    # ── V3 Phase 1.1 — mode tag ────────────────────────────────────────────

    tag: ConversationTag = Field(
        default="",
        description=(
            "Conversation-level mode. Set at creation, immutable for the "
            "life of the conversation. Drives close-out dispatch "
            "(empty → retain, ``stealth`` → full purge, ``private`` → "
            "retain-and-flag) and default RAG filtering "
            '(``tag != "private"`` is added to cross-conversation '
            "queries)."
        )
    )

    # ── Lifecycle ──────────────────────────────────────────────────────────

    created: Optional[str] = Field(
        default=None,
        description=(
            "ISO 8601 timestamp when this envelope was created. May be "
            "``None`` on legacy envelopes; ``conversation_memory`` "
            "backfills on next write but does not overwrite."
        )
    )

    # ── Fork ancestry (V3 Backlog 2C) ──────────────────────────────────────

    parent_conversation_id: Optional[str] = Field(
        default=None,
        description=(
            "For forks: the parent's ``conversation_id``. ``None`` for "
            "root conversations. Pipeline reconstruction walks this "
            "chain recursively. Non-stealth ancestors are always "
            "available; orphan handling for purged stealth ancestors "
            "is intentional (see Backlog item 5)."
        )
    )
    fork_point_chunk_id: Optional[str] = Field(
        default=None,
        description=(
            "For forks: the parent's ``chunk_id`` at the fork point. "
            "Uses ``chunk_id`` rather than turn number because "
            "``pair_num`` resets within a session, so ``chunk_id`` is "
            "the only unambiguous global pointer inside a conversation."
        )
    )
    forked_at: Optional[str] = Field(
        default=None,
        description=(
            "Legacy mirror of ``created`` for fork events. Older "
            "callers may read this; new writes set both ``created`` "
            "and ``forked_at``."
        )
    )

    # ── Reading state (V3 Phase 2) ─────────────────────────────────────────

    last_read_at: Optional[str] = Field(
        default=None,
        description=(
            "Last time the user viewed this conversation's output. "
            "Compared against the latest message timestamp to decide "
            "Unread group membership in the sidebar list."
        )
    )

    # ── Errored state (Backlog 11) ─────────────────────────────────────────

    last_status: Optional[Literal["errored"]] = Field(
        default=None,
        description=(
            "Mirror of the last chunk's status when the pipeline failed. "
            "Drives the Errored sidebar group. Only ``errored`` is "
            "written; the field is removed on dismiss / retry-success."
        )
    )
    last_error_summary: Optional[str] = Field(
        default=None,
        description=(
            "Short summary text shown in the errored row before the "
            "user opens the chunk to see the full failure trace."
        )
    )
    last_errored_at: Optional[str] = Field(
        default=None,
        description="ISO timestamp when ``last_status`` was set to errored."
    )

    # ── WELCOME (V3 spec §6.2) ─────────────────────────────────────────────

    is_welcome: bool = Field(
        default=False,
        description=(
            "True only on the WELCOME thread. Pins it to the top of the "
            "sidebar regardless of recency, exempts it from automatic "
            "cleanup, and substitutes the title with ``Welcome to Ora`` "
            "at render time when ``display_name`` is empty."
        )
    )

    # ── Pin (V3 Backlog 3F) ────────────────────────────────────────────────

    pinned: bool = Field(
        default=False,
        description=(
            "User-pinned conversations surface in the Pinned sidebar "
            "group at the top of the list. Independent of "
            "``is_welcome`` (the two coexist; WELCOME is auto-pinned "
            "while ``pinned`` reflects a user toggle)."
        )
    )

    # ── Messages ───────────────────────────────────────────────────────────

    messages: list[Turn] = Field(
        default_factory=list,
        description=(
            "Ordered list of user / assistant turns. ``save_turn_"
            "spatial_state`` appends a user turn followed by an "
            "assistant turn per call."
        )
    )


# ── ChromaDB denormalized cache ────────────────────────────────────────────


class ChromaDBChunkMetadata(BaseModel):
    """Metadata fields written to the ChromaDB ``conversations`` collection
    for each chunk_id.

    The collection's row id is the chunk_id. The document text is the
    embedding-input string (``context_header + "\\n\\n" + user_input``).
    Metadata fields below are denormalized from the chunk YAML and the
    conversation envelope so RAG queries can filter without joining.

    ChromaDB metadata constraints:

      * Values must be primitive scalars (str / int / float / bool).
      * Lists are not allowed — ``topics`` is a comma-joined string.
      * Field absence is allowed; readers default missing fields.
    """

    source_platform: Literal["local"] = Field(
        description="Mirror of the chunk YAML field."
    )
    model_used: str = Field(
        description="Mirror of the chunk YAML field."
    )
    timestamp: str = Field(
        description="Mirror of the chunk YAML field."
    )
    session_id: str = Field(
        description="Mirror of the chunk YAML field."
    )
    pair_num: int = Field(
        description=(
            "Integer form of the chunk YAML's ``turn_range`` (which is "
            "stringified for YAML)."
        )
    )
    topics: str = Field(
        description=(
            "Comma-joined topics list. Chroma does not allow list "
            "values, so the list is flattened to a string."
        )
    )
    chunk_path: str = Field(
        description="Absolute path to the chunk file on disk."
    )
    agent_id: Literal["user"] = Field(
        description=(
            "Reserved for future multi-agent attribution. Currently "
            "always ``user``."
        )
    )
    tag: ConversationTag = Field(
        description=(
            "Denormalized from the conversation envelope. Default RAG "
            'queries add ``tag != "private"`` to exclude private '
            "content from cross-conversation retrieval."
        )
    )
    conversation_id: str = Field(
        description=(
            "Links the chunk back to the V3 conversation directory. "
            "Used by close-out dispatch to identify everything to "
            "purge for stealth-tagged conversations (chunks, "
            "envelope, raw log fragments, vault artifacts)."
        )
    )
    raw_path: str = Field(
        description=(
            "Absolute path to the raw session log fragment. Used by "
            "close-out dispatch to remove the raw log entry on stealth "
            "purge."
        )
    )


# ── Backwards-compat notes ─────────────────────────────────────────────────

BACKCOMPAT_NOTES = """
Legacy compatibility (informational; no migration script exists or is
needed — all defaults are sound):

* Chunks written before V3 Backlog 2C lack ``status`` and ``tag`` YAML
  keys. Readers default ``status`` to ``ok`` and ``tag`` to ``""``.

* Conversation envelopes written before V3 Phase 1.1 lack ``tag``.
  Readers default to ``""`` (standard mode). ``conversation_memory.py``
  backfills ``tag``, ``created``, ``parent_conversation_id``, and
  ``fork_point_chunk_id`` to defaults on the next write but does NOT
  overwrite existing values.

* Turns written before WP-5.3 lack ``spatial_representation``,
  ``annotations``, and ``vision_extraction_result``. Readers default
  to ``None`` for each.

* The errored-chunk write path described by :class:`ChunkBodyErrored`
  is designed but not yet implemented in ``_save_conversation``. Today
  only the envelope's ``last_status`` field signals an errored run.
"""


__all__ = [
    "ConversationTag",
    "ChunkStatus",
    "VALID_CONVERSATION_TAGS",
    "VALID_CHUNK_STATUSES",
    "TURN_SPATIAL_FIELDS",
    "ChunkYAML",
    "ChunkBodyOk",
    "ChunkBodyErrored",
    "Turn",
    "ConversationEnvelope",
    "ChromaDBChunkMetadata",
    "BACKCOMPAT_NOTES",
]
