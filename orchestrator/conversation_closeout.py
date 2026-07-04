"""V3 Phase 1.5 — Conversation close-out dispatch.

The V3 mode mechanism (Phase 1.1) carries each conversation's mode as a
``tag`` field on the conversation.json envelope (empty / ``stealth`` /
``private``). When the user closes a conversation, this module dispatches
the appropriate cleanup based on tag:

* empty (standard) → hide from sidebar. The envelope is stamped
  ``closed: true``; iter_conversations filters those out. Chunks,
  ChromaDB records, and vault exports are retained. Reversible by
  clearing the flag.
* ``stealth`` → full purge. All artifacts associated with the
  conversation are deleted: the session directory under ``~/ora/sessions/``,
  the per-pair chunk files in ``~/Documents/conversations/``, the raw
  session log in ``~/Documents/conversations/raw/``, and the ChromaDB
  records in the ``conversations`` collection. (Vault artifacts under
  ``~/Documents/vault/Sessions/`` are not auto-deleted today — that is
  marked as a follow-up; users only land in vault by explicit export, and
  if a stealth conversation was exported there, the user did so
  intentionally.)
* ``private`` → hide from sidebar (same ``closed: true`` flag). The tag
  is retained intact so RAG queries continue to filter the data out by
  default. The conversation persists on disk.

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

from . import runtime_paths as _rp
from .conversation_memory import get_conversation_tag, set_conversation_closed


# Purge-target roots flow from runtime_paths (ORA_HOME / ORA_VAULT /
# ORA_CONVERSATIONS relocatable) so the purge always looks where the
# writers actually wrote. Peer writers: conversation_memory (envelope),
# server.py (chunks / raw / manifest / failures log), vault_export
# (vault Sessions dir). test_portability asserts the roots agree.
_DEFAULT_SESSIONS_ROOT = _rp.ORA_HOME / "sessions"
_DEFAULT_CONVERSATIONS_DIR = _rp.CONVERSATIONS
_DEFAULT_CONVERSATIONS_RAW = _rp.CONVERSATIONS / "raw"
_DEFAULT_CHROMADB_PATH = _rp.ORA_HOME / "chromadb"
_DEFAULT_VAULT_SESSIONS = _rp.VAULT / "Sessions"


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
    # empty → standard close.
    # Phase 5.8: finalize chunk metadata for retained conversations —
    # update total_turns to the final pair count and mark is_last_turn
    # on the highest-turn chunk. This applies to non-stealth tags only;
    # stealth tags purge in _purge_stealth above.
    # Hide the conversation from the sidebar by stamping `closed: true`
    # on the envelope. iter_conversations filters these out; the data
    # itself is retained on disk and can be restored by clearing the flag.
    finalize = _finalize_conversation_chunks(
        conversation_id, chromadb_path=chromadb_path,
    )
    errors = list(finalize.get("errors", []))
    closed_path = set_conversation_closed(
        conversation_id, True, sessions_root=sessions_root,
    )
    if closed_path is None:
        errors.append("set_conversation_closed: envelope missing or unwritable")
    return {
        "conversation_id": conversation_id,
        "tag": tag,
        "action": "close",
        "closed":          closed_path is not None,
        "finalize":        finalize,
        "errors":          errors,
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

    # --- Layer 6: Pipeline forensic traces ----------------------------------
    # Defence-in-depth (2026-05-15). Stealth conversations are supposed
    # to skip trace creation entirely via ``pipeline_trace.start_trace``'s
    # stealth flag, so this directory should not exist for a stealth
    # conversation. But the trace layer is large and easy to bypass
    # accidentally if a future caller forgets to thread the stealth flag.
    # This layer guarantees that even if a trace dir somehow landed for a
    # stealth conversation_id, the purge wipes it. ``purge_conversation_traces``
    # is a no-op when no directory exists.
    deleted["pipeline_traces"] = False
    try:
        from orchestrator import pipeline_trace as _pt
        pt_result = _pt.purge_conversation_traces(conversation_id)
        deleted["pipeline_traces"] = pt_result["deleted"]
        deleted["pipeline_traces_path"] = pt_result["path"]
        if pt_result.get("error"):
            errors.append(f"pipeline_traces {pt_result['path']}: {pt_result['error']}")
    except Exception as e:
        errors.append(f"pipeline_traces: {e}")

    # --- Layer 8: Manifest-driven orphan recovery ---------------------------
    # ChromaDB-based discovery (Layer 1) misses chunk_path / raw_path when
    # the original indexing attempt failed (because no metadata was ever
    # written). server.py::_save_conversation writes an authoritative
    # manifest entry to ~/ora/data/conversation-manifest.jsonl BEFORE the
    # ChromaDB attempt, so the on-disk artifacts are recoverable even when
    # ChromaDB never received them. This layer reads that manifest, deletes
    # any chunk_path / raw_path it carries for this conversation that
    # weren't already purged, and strips matching entries from the manifest
    # atomically.
    deleted["manifest_orphans_removed"] = 0
    try:
        import json as _json_mf
        # Read at call time from runtime_paths so the purge follows an
        # ORA_HOME relocation (same pattern as Layers 6a/9 below).
        manifest_path = Path(os.path.join(
            _rp.DATA_DIR_STR, "conversation-manifest.jsonl"
        ))
        if manifest_path.exists():
            kept_lines: list[str] = []
            already_deleted_chunk = {str(p) for p in deleted["chunk_files"]}
            removed = 0
            with open(manifest_path) as f:
                for line in f:
                    line = line.rstrip("\n")
                    if not line.strip():
                        continue
                    try:
                        rec = _json_mf.loads(line)
                    except Exception:
                        kept_lines.append(line)
                        continue
                    if rec.get("conversation_id") != conversation_id:
                        kept_lines.append(line)
                        continue
                    # Matched record — delete chunk_path and raw_path if
                    # they still exist on disk and weren't already removed
                    # by Layer 2 / Layer 3.
                    cp = rec.get("chunk_path")
                    rp = rec.get("raw_path")
                    if cp and cp not in already_deleted_chunk:
                        try:
                            p = Path(cp)
                            if p.exists():
                                p.unlink()
                                deleted["chunk_files"].append(str(p))
                                already_deleted_chunk.add(str(p))
                        except Exception as e:
                            errors.append(f"manifest chunk_file {cp}: {e}")
                    if rp and not deleted["raw_log"]:
                        try:
                            p = Path(rp)
                            if p.exists():
                                p.unlink()
                                deleted["raw_log"] = True
                        except Exception as e:
                            errors.append(f"manifest raw_log {rp}: {e}")
                    removed += 1
            if removed:
                tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
                with open(tmp, "w") as f:
                    for line in kept_lines:
                        f.write(line + "\n")
                tmp.replace(manifest_path)
                deleted["manifest_orphans_removed"] = removed
    except Exception as e:
        errors.append(f"manifest: {e}")

    # --- Layer 9: Oversight logs (events / actions / human-queue) -----------
    # Defence-in-depth (2026-05-17). Stealth conversations are supposed
    # to skip these writes via ``oversight_events.emit``'s stealth-context
    # gate plus the matching guards in ``oversight_actions._append_human_queue``
    # and ``_append_actions_log``. The thread-local that drives those
    # guards is now set at the very top of ``server.py::_pipeline_stream``
    # (above all four short-circuits), but the prior shape of that
    # function set it only after the runtime/resolution/elicitation/
    # framework-slash short-circuits had returned — so a stealth turn
    # that hit any of those four paths leaked the prompt text into
    # events.jsonl via the ``FrameworkStarted`` (and similar) payloads
    # that carry ``user_input``. This layer is the post-hoc scrub that
    # guarantees zero residue even when a future code path forgets to
    # set the thread-local, by stripping any record matching the purged
    # conversation_id. Records are stamped with ``conversation_id`` by
    # ``oversight_events.emit`` and the two write helpers in
    # ``oversight_actions`` when the per-thread context is set.
    # The scrub targets must be the files the writers actually write:
    # both flow from runtime_paths (ORA_HOME-relocatable), read at call
    # time so a purge can never silently miss a relocated sink.
    from . import runtime_paths as _rp_purge
    OVERSIGHT_DIR = Path(os.path.join(_rp_purge.DATA_DIR_STR, "oversight"))
    deleted["oversight_log_entries"] = {
        "events.jsonl": 0,
        "actions.jsonl": 0,
        "human-queue.jsonl": 0,
    }

    # --- Layer 6a: global tool-event sink (Execution Review Phase 1) ------
    # Turn-scoped tool events live in the pipeline-trace turn dirs (removed
    # wholesale by the trace purge above); events that landed in the global
    # sink (direct-mode turns, daemons) are stamped with a top-level
    # conversation_id by tool_events.record precisely so this rewrite can
    # reach them. Suppression-at-write is the primary stealth control; this
    # is defence-in-depth for anything correlated that slipped through.
    try:
        import json as _json_te
        from . import tool_events as _te_mod
        _te_path = Path(_te_mod.global_sink_path())
        deleted["tool_event_entries"] = 0
        if _te_path.exists():
            kept: list[str] = []
            removed = 0
            with open(_te_path) as f:
                for line in f:
                    line = line.rstrip("\n")
                    if not line.strip():
                        continue
                    try:
                        rec = _json_te.loads(line)
                    except Exception:
                        kept.append(line)
                        continue
                    if rec.get("conversation_id") == conversation_id:
                        removed += 1
                        continue
                    kept.append(line)
            if removed:
                tmp = _te_path.with_suffix(_te_path.suffix + ".tmp")
                with open(tmp, "w") as f:
                    for line in kept:
                        f.write(line + "\n")
                tmp.replace(_te_path)
                deleted["tool_event_entries"] = removed
    except Exception as e:
        errors.append(f"tool_events purge: {e}")

    # --- Layer 6b: task-approval tokens (Execution Review Phase 2) ---------
    # A stealth conversation's tier=irreversible hold mints a task_execute
    # token in data/execution-approvals.json carrying the conversation_id.
    # Scrub any token bound to the purged conversation so the stealth
    # zero-residue promise covers the approval store too (condition 9).
    try:
        import json as _json_tok
        from . import tool_events as _te_tok
        _appr = Path(_te_tok.APPROVALS_PATH)
        deleted["task_tokens"] = 0
        if _appr.exists():
            with open(_appr) as f:
                data = _json_tok.load(f)
            toks = data.get("tokens", [])
            kept_toks = [t for t in toks
                         if t.get("conversation_id") != conversation_id]
            dropped = len(toks) - len(kept_toks)
            if dropped:
                data["tokens"] = kept_toks
                tmp = _appr.with_suffix(_appr.suffix + ".tmp")
                with open(tmp, "w") as f:
                    _json_tok.dump(data, f)
                tmp.replace(_appr)
                deleted["task_tokens"] = dropped
    except Exception as e:
        errors.append(f"task_tokens purge: {e}")

    try:
        import json as _json_ov
        for log_name in ("events.jsonl", "actions.jsonl", "human-queue.jsonl"):
            log_path = OVERSIGHT_DIR / log_name
            if not log_path.exists():
                continue
            kept_lines: list[str] = []
            removed = 0
            try:
                with open(log_path) as f:
                    for line in f:
                        line = line.rstrip("\n")
                        if not line.strip():
                            continue
                        try:
                            rec = _json_ov.loads(line)
                        except Exception:
                            kept_lines.append(line)
                            continue
                        if rec.get("conversation_id") == conversation_id:
                            removed += 1
                            continue
                        kept_lines.append(line)
                if removed:
                    tmp = log_path.with_suffix(log_path.suffix + ".tmp")
                    with open(tmp, "w") as f:
                        for line in kept_lines:
                            f.write(line + "\n")
                    tmp.replace(log_path)
                    deleted["oversight_log_entries"][log_name] = removed
            except OSError as e:
                errors.append(f"oversight_log {log_name}: {e}")
    except Exception as e:
        errors.append(f"oversight_logs: {e}")

    # --- Layer 7: Conversation indexing-failure log -------------------------
    # Defence-in-depth (2026-05-15, fix #12). server.py::_save_conversation
    # writes ChromaDB indexing failures to
    # ~/ora/data/conversation-indexing-failures.jsonl. The write site
    # skips stealth conversations entirely, but if a stealth conversation
    # ever leaked an entry (e.g., the tag was set after the failure was
    # already logged), this layer strips entries matching the stealth
    # conversation_id without disturbing entries for other conversations.
    deleted["indexing_failures_log_entries"] = 0
    try:
        import json as _json
        log_path = Path(os.path.join(
            _rp.DATA_DIR_STR, "conversation-indexing-failures.jsonl"
        ))
        if log_path.exists():
            kept_lines: list[str] = []
            removed = 0
            with open(log_path) as f:
                for line in f:
                    line = line.rstrip("\n")
                    if not line.strip():
                        continue
                    try:
                        rec = _json.loads(line)
                    except Exception:
                        # Corrupt line — keep it, don't lose other content
                        kept_lines.append(line)
                        continue
                    if rec.get("conversation_id") == conversation_id:
                        removed += 1
                        continue
                    kept_lines.append(line)
            if removed:
                # Atomic replace
                tmp = log_path.with_suffix(log_path.suffix + ".tmp")
                with open(tmp, "w") as f:
                    for line in kept_lines:
                        f.write(line + "\n")
                tmp.replace(log_path)
                deleted["indexing_failures_log_entries"] = removed
    except Exception as e:
        errors.append(f"indexing_failures_log: {e}")

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
