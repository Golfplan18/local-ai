"""V3 Phase 1.5 — Conversation close-out dispatch.

The V3 mode mechanism (Phase 1.1) carries each conversation's mode as a
``tag`` field on the conversation.json envelope (empty / ``stealth`` /
``private``). When the user closes a conversation, this module dispatches
the appropriate cleanup based on tag:

* empty (standard) → no-op. The conversation file, chunks, ChromaDB
  records, and any vault exports stay. The UI removes the row from its
  active list.
* ``stealth`` → full purge. All artifacts associated with the
  conversation are deleted: the session directory under ``~/ora/sessions/``,
  the per-pair chunk files in ``~/Documents/conversations/``, the raw
  session log in ``~/Documents/conversations/raw/``, and the ChromaDB
  records in the ``conversations`` collection. (Vault artifacts under
  ``~/Documents/vault/Sessions/`` are not auto-deleted today — that is
  marked as a follow-up; users only land in vault by explicit export, and
  if a stealth conversation was exported there, the user did so
  intentionally.)
* ``private`` → no-op server-side. The conversation is retained with its
  tag intact so RAG queries continue to filter it out by default. The UI
  removes the row from the active list but the data persists.

The purge is best-effort: each layer's deletion is wrapped in a try/except
so a failure in one layer doesn't block deletion of the others. The result
dict reports what was deleted and what failed.

Identification keys:
  * conversation_id (= panel_id in the server's vocabulary): identifies the
    session directory and is denormalized onto each chunk's ChromaDB
    metadata as ``conversation_id``.
  * Chunks: located via ChromaDB ``where`` filter on conversation_id;
    ``chunk_path`` and ``raw_path`` are read from chunk metadata so the
    filesystem deletes can target the right files without scanning
    directories.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from .conversation_memory import get_conversation_tag


_DEFAULT_SESSIONS_ROOT = Path.home() / "ora" / "sessions"
_DEFAULT_CONVERSATIONS_DIR = Path.home() / "Documents" / "conversations"
_DEFAULT_CONVERSATIONS_RAW = Path.home() / "Documents" / "conversations" / "raw"
_DEFAULT_CHROMADB_PATH = Path.home() / "ora" / "chromadb"
_DEFAULT_VAULT_SESSIONS = Path.home() / "Documents" / "vault" / "Sessions"


def close_conversation(
    conversation_id: str,
    *,
    sessions_root: Path | None = None,
    conversations_dir: Path | None = None,
    conversations_raw: Path | None = None,
    chromadb_path: Path | None = None,
    vault_sessions: Path | None = None,
) -> dict[str, Any]:
    """Dispatch close-out for a conversation based on its tag.

    Returns a dict reporting the dispatch decision and (for stealth) what
    was deleted::

        {
          "conversation_id": "<id>",
          "tag": "" | "stealth" | "private",
          "action": "noop" | "purge",
          "deleted": {            # only present when action == "purge"
            "session_dir": True | False,
            "chromadb_records": <int>,
            "chunk_files": [<path>, ...],
            "raw_log": True | False,
            "vault_dir": True | False,
          },
          "errors": [<str>, ...],  # any per-layer failures (best-effort)
        }
    """
    tag = get_conversation_tag(conversation_id, sessions_root=sessions_root)

    if tag == "stealth":
        return _purge_stealth(
            conversation_id,
            sessions_root=sessions_root,
            conversations_dir=conversations_dir,
            conversations_raw=conversations_raw,
            chromadb_path=chromadb_path,
            vault_sessions=vault_sessions,
        )

    # private → keep but flag (no server-side state to change beyond what
    # already lives on the envelope and chunk metadata).
    # empty → standard close (no server-side work).
    # Phase 5.8: finalize chunk metadata for retained conversations —
    # update total_turns to the final pair count and mark is_last_turn
    # on the highest-turn chunk. This applies to non-stealth tags only;
    # stealth tags purge in _purge_stealth above.
    finalize = _finalize_conversation_chunks(
        conversation_id, chromadb_path=chromadb_path,
    )
    return {
        "conversation_id": conversation_id,
        "tag": tag,
        "action": "noop",
        "finalize":        finalize,
        "errors":          finalize.get("errors", []),
    }


def _finalize_conversation_chunks(
    conversation_id: str,
    *,
    chromadb_path: Path | None = None,
) -> dict[str, Any]:
    """Phase 5.8 close-out finalization.

    For non-stealth conversations: walk all chunks of the conversation,
    set ``total_turns`` to the highest observed ``turn_index``, and mark
    ``is_last_turn = True`` on the chunk(s) with the highest turn index.

    Returns a dict reporting what was updated and any errors. Best-
    effort — failures are collected and returned, not raised.
    """
    chroma = Path(chromadb_path) if chromadb_path else _DEFAULT_CHROMADB_PATH

    out: dict[str, Any] = {
        "chunks_updated":  0,
        "final_turn":      0,
        "errors":          [],
    }

    try:
        import chromadb  # type: ignore
        from orchestrator.embedding import get_collection as _bound_get_collection
        client = chromadb.PersistentClient(path=str(chroma))
        try:
            col = _bound_get_collection(client, "conversations")
        except Exception:
            return out  # No conversations collection yet — nothing to finalize.

        results = col.get(where={"conversation_id": conversation_id})
        ids = results.get("ids") or []
        metas = results.get("metadatas") or []
        if not ids:
            return out

        final_turn = 0
        for meta in metas:
            if not isinstance(meta, dict):
                continue
            ti = meta.get("turn_index")
            if isinstance(ti, int) and ti > final_turn:
                final_turn = ti
        out["final_turn"] = final_turn

        # Update each chunk's total_turns; mark is_last_turn on the
        # highest-turn chunk(s).
        for cid, meta in zip(ids, metas):
            if not isinstance(meta, dict):
                continue
            new_meta = dict(meta)
            new_meta["total_turns"] = final_turn
            new_meta["is_last_turn"] = bool(meta.get("turn_index") == final_turn)
            try:
                col.update(ids=[cid], metadatas=[new_meta])
                out["chunks_updated"] += 1
            except Exception as e:
                out["errors"].append(f"update {cid}: {e}")
    except Exception as e:
        out["errors"].append(f"chromadb finalize: {e}")

    return out


def _purge_stealth(
    conversation_id: str,
    *,
    sessions_root: Path | None,
    conversations_dir: Path | None,
    conversations_raw: Path | None,
    chromadb_path: Path | None,
    vault_sessions: Path | None,
) -> dict[str, Any]:
    """Best-effort full purge of a stealth-tagged conversation.

    Each layer's deletion is independent — a failure in one does not block
    the others. All errors are collected and returned so the caller can
    surface them.
    """
    sroot = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    cdir = Path(conversations_dir) if conversations_dir else _DEFAULT_CONVERSATIONS_DIR
    craw = Path(conversations_raw) if conversations_raw else _DEFAULT_CONVERSATIONS_RAW
    chroma = Path(chromadb_path) if chromadb_path else _DEFAULT_CHROMADB_PATH
    vroot = Path(vault_sessions) if vault_sessions else _DEFAULT_VAULT_SESSIONS

    errors: list[str] = []
    deleted: dict[str, Any] = {
        "session_dir": False,
        "chromadb_records": 0,
        "chunk_files": [],
        "raw_log": False,
        "vault_dir": False,
    }

    # --- Layer 1: ChromaDB records (read paths first, then delete) -----------
    chunk_paths: list[str] = []
    raw_paths: set[str] = set()
    chroma_ids: list[str] = []
    try:
        import chromadb  # type: ignore
        from orchestrator.embedding import get_collection as _bound_get_collection
        client = chromadb.PersistentClient(path=str(chroma))
        try:
            col = _bound_get_collection(client, "conversations")
        except Exception:
            col = None
        if col is not None:
            results = col.get(where={"conversation_id": conversation_id})
            ids = results.get("ids") or []
            metas = results.get("metadatas") or []
            for cid, meta in zip(ids, metas):
                chroma_ids.append(cid)
                if isinstance(meta, dict):
                    cp = meta.get("chunk_path")
                    if isinstance(cp, str) and cp:
                        chunk_paths.append(cp)
                    rp = meta.get("raw_path")
                    if isinstance(rp, str) and rp:
                        raw_paths.add(rp)
            if chroma_ids:
                col.delete(ids=chroma_ids)
                deleted["chromadb_records"] = len(chroma_ids)
    except Exception as e:
        errors.append(f"chromadb: {e}")

    # --- Layer 2: Chunk files ------------------------------------------------
    for cp in chunk_paths:
        try:
            p = Path(cp)
            if p.exists():
                p.unlink()
                deleted["chunk_files"].append(str(p))
        except Exception as e:
            errors.append(f"chunk_file {cp}: {e}")

    # --- Layer 3: Raw log fragment(s) ---------------------------------------
    # A conversation typically has exactly one raw log; the set lets us
    # tolerate the rare case where chunks point at different raw_paths
    # (shouldn't happen in normal flow, but defensive).
    for rp in raw_paths:
        try:
            p = Path(rp)
            if p.exists():
                p.unlink()
                deleted["raw_log"] = True
        except Exception as e:
            errors.append(f"raw_log {rp}: {e}")

    # --- Layer 4: Session directory -----------------------------------------
    session_dir = sroot / conversation_id
    try:
        if session_dir.exists() and session_dir.is_dir():
            shutil.rmtree(session_dir)
            deleted["session_dir"] = True
    except Exception as e:
        errors.append(f"session_dir {session_dir}: {e}")

    # --- Layer 5: Vault session directory -----------------------------------
    # Spec item 1: stealth purge deletes vault artifacts under that
    # conversation_id. Vault export is opt-in, so the directory may not
    # exist for many stealth conversations — that's fine, we just skip.
    vault_dir = vroot / conversation_id
    try:
        if vault_dir.exists() and vault_dir.is_dir():
            shutil.rmtree(vault_dir)
            deleted["vault_dir"] = True
    except Exception as e:
        errors.append(f"vault_dir {vault_dir}: {e}")

    return {
        "conversation_id": conversation_id,
        "tag": "stealth",
        "action": "purge",
        "deleted": deleted,
        "errors": errors,
    }


__all__ = [
    "close_conversation",
    "_finalize_conversation_chunks",
]
