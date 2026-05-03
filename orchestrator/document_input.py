#!/usr/bin/env python3
"""V3 Input Handling Phase 8 — document file ingestion manager.

Mirrors the shape of ``orchestrator/transcription.py``: per-document
processing IDs, a job state dict, and an SSE fanout for progress events.
The frontend's ``document-input.js`` module talks to this through the
companion endpoints in ``server.py``:

  POST /api/document/process            — start a job
  GET  /api/document/<id>/state         — poll state
  GET  /api/document/stream             — SSE event stream

For v1, processing is intentionally lightweight:

  1. The uploaded file is staged to ``~/ora/staging/documents/``.
  2. A background thread converts the document to markdown via
     ``orchestrator.tools.format_convert.convert_to_markdown``.
  3. The markdown is written to the vault under ``Incubator/`` with
     YAML frontmatter declaring ``type: incubator`` and tags including
     ``incubating`` (and ``private`` when the conversation requests it).
  4. The job emits ``queued → converting → writing → complete`` events.

Full Document Processing (atomic-note extraction, ChromaDB ingestion,
quality gate, etc.) is NOT run synchronously here — that's the heavier
``BatchProcessor`` pipeline, which the user can invoke later via the
framework picker on the staged note. v1's deliverable is "the document
is in the vault, indexed by RAG when the user runs Document Processing
on it." That keeps the input pane responsive and matches the design
doc's "async, non-blocking" intent.

Stealth-mode handling: when the caller passes ``tag="stealth"`` the
output bypasses the vault entirely and lands in a temp directory keyed
to the conversation. The conversation closeout flow (Phase 1.5) is
responsible for purging the temp dir on stealth close.
"""
from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from tools.format_convert import convert_to_markdown  # type: ignore

# ── Paths ───────────────────────────────────────────────────────────────

STAGING_DIR = os.path.expanduser("~/ora/staging/documents/")
VAULT_INCUBATOR_DIR = os.path.expanduser("~/Documents/vault/Incubator/")
STEALTH_TEMP_ROOT = os.path.expanduser("~/ora/sessions/")

os.makedirs(STAGING_DIR, exist_ok=True)
# Vault Incubator dir is created lazily on first write so the framework
# does not assume it exists in fresh installs.

# ── Per-process job table + SSE fanout ──────────────────────────────────

_jobs_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}

_subscribers_lock = threading.Lock()
_subscribers: list[Callable[[dict], None]] = []


def subscribe(callback: Callable[[dict], None]) -> None:
    """Register a callback that fires for every state event. Used by
    server.py to fan events out to the SSE stream.
    """
    with _subscribers_lock:
        _subscribers.append(callback)


def _emit(event: dict) -> None:
    with _subscribers_lock:
        listeners = list(_subscribers)
    for cb in listeners:
        try:
            cb(event)
        except Exception:
            pass


def _set_state(processing_id: str, state: str, **extra: Any) -> None:
    with _jobs_lock:
        job = _jobs.get(processing_id)
        if job is None:
            return
        job["state"] = state
        job["updated_at"] = time.time()
        for k, v in extra.items():
            job[k] = v
    event = {
        "type": "state",
        "processing_id": processing_id,
        "state": state,
        **extra,
    }
    _emit(event)


# ── Public API ──────────────────────────────────────────────────────────

def start(
    source_path: str,
    options: dict | None = None,
) -> str:
    """Begin a document-processing job for the staged file at ``source_path``.

    Returns the new ``processing_id``. The caller is responsible for having
    already saved the upload to ``source_path`` (server.py's POST endpoint
    does this before calling start).

    ``options`` keys:
      - ``conversation_id`` (str) — used for stealth temp-dir routing
      - ``tag`` (str) — empty | ``private`` | ``stealth``; controls write
        destination + tags on the resulting vault note
      - ``original_name`` (str) — pretty filename for display
    """
    options = options or {}
    processing_id = uuid.uuid4().hex[:12]

    job = {
        "processing_id": processing_id,
        "source_path":   source_path,
        "original_name": options.get("original_name") or os.path.basename(source_path),
        "tag":           options.get("tag", "") or "",
        "conversation_id": options.get("conversation_id", "") or "",
        "state":         "queued",
        "created_at":    time.time(),
        "updated_at":    time.time(),
        "vault_path":    None,
        "error":         None,
    }
    with _jobs_lock:
        _jobs[processing_id] = job

    _emit({"type": "state", "processing_id": processing_id, "state": "queued"})

    thread = threading.Thread(
        target=_run_job, args=(processing_id,), daemon=True,
    )
    thread.start()
    return processing_id


def get_state(processing_id: str) -> dict[str, Any]:
    """Return a copy of the job state. Raises KeyError if unknown."""
    with _jobs_lock:
        job = _jobs.get(processing_id)
        if job is None:
            raise KeyError(processing_id)
        return dict(job)


# ── Worker ──────────────────────────────────────────────────────────────

def _run_job(processing_id: str) -> None:
    try:
        with _jobs_lock:
            job = dict(_jobs.get(processing_id) or {})
        if not job:
            return

        source_path = job["source_path"]
        original_name = job["original_name"]
        tag = (job.get("tag") or "").strip()
        conversation_id = (job.get("conversation_id") or "").strip()

        _set_state(processing_id, "converting")
        try:
            markdown = convert_to_markdown(source_path)
        except Exception as e:
            _set_state(processing_id, "failed", error=f"format conversion failed: {e}")
            return

        _set_state(processing_id, "writing")
        try:
            output_path = _write_destination(
                markdown=markdown,
                original_name=original_name,
                tag=tag,
                conversation_id=conversation_id,
            )
        except Exception as e:
            _set_state(processing_id, "failed", error=f"vault write failed: {e}")
            return

        _set_state(processing_id, "complete", vault_path=output_path)

    except Exception as e:  # pragma: no cover — defensive
        _set_state(processing_id, "failed", error=f"unhandled: {e}")


# ── Output destination ──────────────────────────────────────────────────

def _slug(name: str) -> str:
    """Sanitize a filename stem into a vault-friendly title."""
    base = os.path.splitext(os.path.basename(name))[0]
    base = re.sub(r"[^\w\s-]", "", base, flags=re.UNICODE).strip()
    base = re.sub(r"\s+", " ", base)
    return base or "Untitled"


def _yaml_frontmatter(tags: list[str]) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    tag_lines = "\n".join(f"  - {t}" for t in tags)
    return (
        "---\n"
        "type: incubator\n"
        f"tags:\n{tag_lines}\n"
        f"date created: {today}\n"
        f"date modified: {today}\n"
        "---\n"
    )


def _write_destination(
    markdown: str,
    original_name: str,
    tag: str,
    conversation_id: str,
) -> str:
    """Write the converted markdown to the right destination based on tag.

    Returns the absolute path written.
    """
    title = _slug(original_name)
    body = (
        f"# {title}\n\n"
        f"_Converted from: {original_name}_\n\n"
        f"---\n\n"
        f"{markdown}\n"
    )

    if tag == "stealth":
        # Ephemeral conversation-keyed temp dir; conversation closeout
        # purges it on stealth close (Phase 1.5).
        conv_slug = re.sub(r"[^A-Za-z0-9_-]", "_", conversation_id) or "default"
        out_dir = os.path.join(STEALTH_TEMP_ROOT, conv_slug, "documents")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{title}.md")
        # Stealth notes still get YAML for consistency, but tag carries
        # ``stealth`` so any code that later scans these dirs knows.
        frontmatter = _yaml_frontmatter(["incubating", "stealth"])
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(frontmatter + body)
        return out_path

    # Vault path — Incubator/, with private tag when requested.
    os.makedirs(VAULT_INCUBATOR_DIR, exist_ok=True)
    base_name = title
    out_path = os.path.join(VAULT_INCUBATOR_DIR, base_name + ".md")
    # Title-based dedup per design doc Q2: skip if a file with the same
    # title already exists in Incubator/. The user can re-attach the
    # same document multiple times across conversations and we link to
    # the existing entry instead of creating duplicates.
    if os.path.exists(out_path):
        return out_path

    tags = ["incubating"]
    if tag == "private":
        tags.append("private")
    frontmatter = _yaml_frontmatter(tags)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(frontmatter + body)
    return out_path


# ── Convenience helpers used by tests / repl ────────────────────────────

def reset_for_tests() -> None:
    """Clear the in-process job table. Used by unit tests."""
    with _jobs_lock:
        _jobs.clear()
    with _subscribers_lock:
        _subscribers.clear()
