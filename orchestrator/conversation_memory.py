#!/usr/bin/env python3
"""
WP-5.3 — Spatial continuity across turns.

This module owns the turn-to-turn persistence contract for visual state. Each
turn of a conversation may carry a ``spatial_representation``, an
``annotations`` payload, and/or a ``vision_extraction_result``. When the next
turn fires, the analytical pipeline receives the prior turn's spatial state
alongside the new input so the model sees the evolution of the user's
arrangement — not just the latest snapshot.

Persistence surface
-------------------

``~/ora/sessions/<conversation_id>/conversation.json`` is the native
structured log for a conversation. Each message in ``messages[]`` is a
``{role, content, timestamp, ...}`` dict; WP-5.3 adds three optional fields
per turn:

    {
      "role": "user",
      "content": "<text>",
      "timestamp": "...",
      "spatial_representation": { ... } | null,
      "annotations": [ ... ] | null,
      "vision_extraction_result": { ... } | null
    }

All three fields are optional. Missing fields are stored as ``null`` (not
absent) so forward/backward compatibility is trivial: older records without
these keys are still loadable, and reading code always sees ``None`` for a
missing slot.

Schema-version strategy
-----------------------

No ``schema_version`` field on the conversation.json envelope — the additive-
fields approach + null-default rule means existing files keep working without
migration. If we ever need to bump the shape (e.g. renaming a key), we'll
introduce ``schema_version: "1"`` at that point. Until then, absence of the
field means "v0 / unversioned".

Backwards compat
----------------

* A conversation.json written before WP-5.3 has no spatial_representation
  keys on its turns. :func:`get_prior_spatial_state` returns ``None`` for
  those and the caller skips the PRIOR-STATE fence.
* A conversation passed as an in-memory ``history`` list (chat endpoint
  history arg) may or may not contain the spatial keys. Both shapes are
  accepted by :func:`get_prior_spatial_state`.

The helpers are deliberately pure-Python and free of Flask so they can be
imported from ``boot.py`` (server-agnostic) or from tests without a server.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Default sessions root. Tests override via ``sessions_root=`` kwarg on
# :func:`save_turn_spatial_state` / :func:`load_conversation_json`.
_DEFAULT_SESSIONS_ROOT = Path.home() / "ora" / "sessions"

# The three optional turn fields WP-5.3 persists. Kept as a module-level
# tuple so :func:`save_turn_spatial_state` and tests can enumerate them.
TURN_SPATIAL_FIELDS: tuple[str, ...] = (
    "spatial_representation",
    "annotations",
    "vision_extraction_result",
)


# ---------------------------------------------------------------------------
# Conversation JSON I/O
# ---------------------------------------------------------------------------


def _conversation_path(conversation_id: str, sessions_root: Path) -> Path:
    """Return the absolute path to the conversation.json for a given id."""
    return Path(sessions_root) / conversation_id / "conversation.json"


def load_conversation_json(
    conversation_id: str,
    sessions_root: Path | None = None,
) -> dict[str, Any] | None:
    """Read the conversation.json for a conversation_id, or None if missing.

    Returns the raw dict including the ``messages`` list. Never raises on
    parse error — corrupted files return ``None``, so callers can fall back
    to the in-memory ``history`` arg without blowing up the pipeline.
    """
    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    path = _conversation_path(conversation_id, root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("messages"), list):
        return None
    return data


def save_turn_spatial_state(
    conversation_id: str,
    user_input: str,
    ai_response: str,
    *,
    spatial_representation: dict | None = None,
    annotations: dict | list | None = None,
    vision_extraction_result: dict | None = None,
    timestamp: str | None = None,
    sessions_root: Path | None = None,
) -> Path | None:
    """Append a user+assistant pair to conversation.json with optional
    spatial fields on the user turn.

    Creates the session directory + file on first write. On subsequent
    writes, appends to ``messages[]`` preserving prior turns.

    The user turn carries the three optional spatial fields. The assistant
    turn is written with the same three fields set to ``None`` (reserved —
    future assistants may emit spatial state too). Keys are always present
    (never absent) so downstream code can rely on the shape.

    Returns the path written, or ``None`` on I/O failure (non-blocking; the
    persistence step must never break the conversation flow).
    """
    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    path = _conversation_path(conversation_id, root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None

    existing: dict[str, Any] | None = None
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                existing = None
            elif not isinstance(existing.get("messages"), list):
                existing = None
        except (OSError, json.JSONDecodeError):
            existing = None

    if existing is None:
        existing = {
            "conversation_id": conversation_id,
            "messages": [],
        }

    # Normalize annotations payload: accept either wrapper dict or bare list.
    annotations_normalized: Any
    if annotations is None:
        annotations_normalized = None
    elif isinstance(annotations, dict) and "annotations" in annotations:
        annotations_normalized = annotations.get("annotations")
    elif isinstance(annotations, list):
        annotations_normalized = annotations
    else:
        # Unknown shape — store verbatim rather than dropping it.
        annotations_normalized = annotations

    user_turn = {
        "role": "user",
        "content": user_input,
        "timestamp": timestamp,
        "spatial_representation": spatial_representation,
        "annotations": annotations_normalized,
        "vision_extraction_result": vision_extraction_result,
    }
    assistant_turn = {
        "role": "assistant",
        "content": ai_response,
        "timestamp": timestamp,
        "spatial_representation": None,
        "annotations": None,
        "vision_extraction_result": None,
    }

    existing["messages"].append(user_turn)
    existing["messages"].append(assistant_turn)

    try:
        path.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        return None
    return path


# ---------------------------------------------------------------------------
# Prior-state retrieval
# ---------------------------------------------------------------------------


def get_prior_spatial_state(
    conversation_id: str,
    history: list | None,
    *,
    sessions_root: Path | None = None,
) -> dict | None:
    """Return the most recent user-turn spatial_representation, or None.

    Search order:
      1. Walk ``history`` backwards (cheapest — already in memory).
      2. If nothing found, load conversation.json from disk and walk its
         ``messages[]`` backwards.

    Only user turns are considered (assistant/system turns don't carry
    user-drawn spatial state). A snapshot is returned (``copy.deepcopy``) so
    the caller can mutate it without corrupting the history.
    """
    # Walk in-memory history first.
    if history and isinstance(history, list):
        for turn in reversed(history):
            if not isinstance(turn, dict):
                continue
            if turn.get("role") != "user":
                continue
            rep = turn.get("spatial_representation")
            if rep:
                return copy.deepcopy(rep)

    # Fall through to disk.
    data = load_conversation_json(conversation_id, sessions_root=sessions_root)
    if data is None:
        return None
    for turn in reversed(data.get("messages") or []):
        if not isinstance(turn, dict):
            continue
        if turn.get("role") != "user":
            continue
        rep = turn.get("spatial_representation")
        if rep:
            return copy.deepcopy(rep)
    return None


def get_prior_annotations(
    conversation_id: str,
    history: list | None,
    *,
    sessions_root: Path | None = None,
) -> list | None:
    """Return the most recent user-turn annotations list, or None.

    Same search rule as :func:`get_prior_spatial_state`. Persistent edit
    intent tends to span turns, so we expose this for the rare mode where
    the model needs to see what the user previously wanted annotated.
    """
    if history and isinstance(history, list):
        for turn in reversed(history):
            if not isinstance(turn, dict):
                continue
            if turn.get("role") != "user":
                continue
            annots = turn.get("annotations")
            if annots:
                return copy.deepcopy(annots)

    data = load_conversation_json(conversation_id, sessions_root=sessions_root)
    if data is None:
        return None
    for turn in reversed(data.get("messages") or []):
        if not isinstance(turn, dict):
            continue
        if turn.get("role") != "user":
            continue
        annots = turn.get("annotations")
        if annots:
            return copy.deepcopy(annots)
    return None


__all__ = [
    "TURN_SPATIAL_FIELDS",
    "load_conversation_json",
    "save_turn_spatial_state",
    "get_prior_spatial_state",
    "get_prior_annotations",
]
