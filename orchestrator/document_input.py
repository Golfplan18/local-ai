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

  1. Conversation-owned uploads are staged under
     ``~/ora/staging/documents/<conversation_id>/`` so ownership survives a
     process restart; unassociated imports retain the flat legacy location.
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
import shutil
import stat
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from tools.format_convert import convert_to_markdown  # type: ignore

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover - package-qualified import context
    from orchestrator import runtime_paths as _rp

# ── Paths ───────────────────────────────────────────────────────────────
# Roots flow from runtime_paths (ORA_HOME / ORA_VAULT relocatable); the
# stealth temp root in particular must match the sessions root the purge
# (conversation_closeout Layer 4) deletes.

STAGING_DIR = os.path.join(_rp.WORKSPACE, "staging", "documents")
VAULT_INCUBATOR_DIR = os.path.join(_rp.VAULT_STR, "Incubator")
STEALTH_TEMP_ROOT = os.path.join(_rp.WORKSPACE, "sessions")

os.makedirs(STAGING_DIR, exist_ok=True)
# Vault Incubator dir is created lazily on first write so the framework
# does not assume it exists in fresh installs.

# ── Per-process job table + SSE fanout ──────────────────────────────────

_jobs_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}
_lifecycle_lock = threading.RLock()
_deleted_conversations: set[str] = set()

_subscribers_lock = threading.Lock()
_subscribers: list[Callable[[dict], None]] = []


def _canonical_conversation_id(value: Any) -> str:
    """Validate a new writer's portable conversation ID without sanitizing."""
    if not isinstance(value, str):
        raise ValueError("conversation_id must be a string")
    if (not value or value != value.strip() or len(value) > 255
            or not all(ch.isascii() and (ch.isdigit() or ch.islower() or ch in "_-")
                       for ch in value)):
        raise ValueError("invalid conversation_id")
    return value


def _conversation_key(value: Any) -> str:
    """Normalize identity for tombstones and legacy mixed-case cleanup."""
    return str(value or "").strip().casefold()


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

    raw_conversation_id = options.get("conversation_id", "") or ""
    conversation_id = (
        _canonical_conversation_id(raw_conversation_id)
        if raw_conversation_id else ""
    )
    tag = options.get("tag", "") or ""
    if tag == "stealth" and not conversation_id:
        raise ValueError("stealth document jobs require a conversation_id")

    job = {
        "processing_id": processing_id,
        "source_path":   source_path,
        "original_name": options.get("original_name") or os.path.basename(source_path),
        "tag":           tag,
        "conversation_id": conversation_id,
        "state":         "queued",
        "created_at":    time.time(),
        "updated_at":    time.time(),
        "vault_path":    None,
        "error":         None,
    }
    with _lifecycle_lock:
        if _conversation_key(job["conversation_id"]) in _deleted_conversations:
            raise RuntimeError("conversation was permanently deleted")
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
        conversation_id = (job.get("conversation_id") or "").strip()

        _set_state(processing_id, "converting")
        try:
            markdown = convert_to_markdown(source_path)
        except Exception as e:
            _set_state(processing_id, "failed", error=f"format conversion failed: {e}")
            return

        # Serialize the correlated write against Delete Forever. Conversion is
        # allowed to run without holding the lock; once deletion is marked the
        # result is discarded and cannot recreate a session/vault derivative.
        with _lifecycle_lock:
            if _conversation_key(conversation_id) in _deleted_conversations:
                try:
                    Path(source_path).unlink(missing_ok=True)
                except OSError:
                    pass
                return
            # Privacy can change while conversion runs. Re-read the live job
            # under the same lifecycle lock used by update_conversation_tag;
            # the creation-time copy above must never decide the final write.
            with _jobs_lock:
                live_job = _jobs.get(processing_id) or job
                tag = (live_job.get("tag") or "").strip()
            _set_state(processing_id, "writing")
            expected_output = (
                Path(STEALTH_TEMP_ROOT) / conversation_id / "documents" /
                f"{_slug(original_name)}.md"
                if tag == "stealth"
                else Path(VAULT_INCUBATOR_DIR) / f"{_slug(original_name)}.md"
            )
            output_existed = expected_output.exists()
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

            _set_state(
                processing_id,
                "complete",
                vault_path=output_path,
                output_created=not output_existed,
            )

    except Exception as e:  # pragma: no cover — defensive
        _set_state(processing_id, "failed", error=f"unhandled: {e}")


# ── Output destination ──────────────────────────────────────────────────

def _slug(name: str) -> str:
    """Sanitize a filename stem into a vault-friendly title."""
    base = os.path.splitext(os.path.basename(name))[0]
    base = re.sub(r"[^\w\s-]", "", base, flags=re.UNICODE).strip()
    base = re.sub(r"\s+", " ", base)
    return base or "Untitled"


def _yaml_frontmatter(tags: list[str], source_file: str = "") -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    tag_lines = "\n".join(f"  - {t}" for t in tags)
    source_line = (
        f"source_file: {json.dumps(source_file, ensure_ascii=False)}\n"
        if source_file else ""
    )
    return (
        "---\n"
        "type: incubator\n"
        f"tags:\n{tag_lines}\n"
        f"{source_line}"
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
        canonical_id = _canonical_conversation_id(conversation_id)
        out_dir = _rp.safe_owned_subdir(
            Path(STEALTH_TEMP_ROOT),
            canonical_id,
            "documents",
            create=True,
        )
        out_path = out_dir / f"{title}.md"
        # Stealth notes still get YAML for consistency, but tag carries
        # ``stealth`` so any code that later scans these dirs knows.
        frontmatter = _yaml_frontmatter(
            ["incubating", "stealth"], conversation_id,
        )
        _rp.atomic_write_text(out_path, frontmatter + body)
        return str(out_path)

    # Vault path — Incubator/, with private tag when requested.  The vault
    # root is user-configurable (and may itself be a trusted symlink), but the
    # Ora-managed Incubator child must be a real directory so a local symlink
    # cannot redirect a correlated write outside the vault.
    incubator = Path(VAULT_INCUBATOR_DIR)
    out_dir = _rp.safe_owned_subdir(
        incubator.parent, incubator.name, create=True,
    )
    base_name = title
    out_path = out_dir / f"{base_name}.md"
    # Title-based dedup per design doc Q2: skip if a file with the same
    # title already exists in Incubator/. The user can re-attach the
    # same document multiple times across conversations and we link to
    # the existing entry instead of creating duplicates.
    if out_path.is_symlink():
        raise ValueError(f"refusing symlinked Incubator note: {out_path}")
    if out_path.exists():
        if not out_path.is_file():
            raise ValueError(f"Incubator note is not a regular file: {out_path}")
        return str(out_path)

    tags = ["incubating"]
    if tag == "private":
        tags.append("private")
    frontmatter = _yaml_frontmatter(tags, conversation_id)
    _rp.atomic_write_text(out_path, frontmatter + body)
    return str(out_path)


def _absolute_entry(path: str | Path) -> Path:
    """Absolute lexical path without resolving its final symlink entry."""
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def _unlink_direct_owned_file(path: str | Path, owned_parent: Path) -> bool:
    """Unlink one exact entry below a validated Ora-owned parent.

    Resolving ``path`` here would be unsafe: if the final entry (or a managed
    child directory) were swapped for a symlink, ``Path.resolve`` could turn a
    precise cleanup into deletion of the link target.  Compare the lexical
    parent, inspect with ``lstat``, and unlink the directory entry itself.
    """
    entry = _absolute_entry(path)
    parent = _absolute_entry(owned_parent)
    if os.path.normcase(str(entry.parent)) != os.path.normcase(str(parent)):
        return False
    try:
        mode = entry.lstat().st_mode
    except FileNotFoundError:
        return False
    if not (stat.S_ISREG(mode) or stat.S_ISLNK(mode)):
        raise ValueError(f"refusing non-file owned entry: {entry}")
    entry.unlink()
    return True


# ── Convenience helpers used by tests / repl ────────────────────────────

def reset_for_tests() -> None:
    """Clear the in-process job table. Used by unit tests."""
    with _lifecycle_lock:
        with _jobs_lock:
            _jobs.clear()
        _deleted_conversations.clear()
    with _subscribers_lock:
        _subscribers.clear()


def update_conversation_tag(conversation_id: str, tag: str) -> dict[str, Any]:
    """Synchronize live document jobs and owned outputs to Standard/Private."""
    conversation_id = (conversation_id or "").strip()
    if tag not in {"", "private"}:
        raise ValueError("document jobs support only Standard/Private retagging")
    result: dict[str, Any] = {"jobs": 0, "outputs": 0, "errors": []}
    conversation_key = _conversation_key(conversation_id)
    with _lifecycle_lock:
        if conversation_key in _deleted_conversations:
            raise RuntimeError("conversation was permanently deleted")
        with _jobs_lock:
            matched = [job for job in _jobs.values()
                       if _conversation_key(job.get("conversation_id"))
                       == conversation_key]
            for job in matched:
                job["tag"] = tag
            outputs = [
                str(job.get("vault_path")) for job in matched
                if job.get("output_created") and job.get("vault_path")
            ]
        result["jobs"] = len(matched)
        try:
            try:
                from .conversation_closeout import _set_private_frontmatter_tag
            except ImportError:  # pragma: no cover - legacy top-level import
                from conversation_closeout import _set_private_frontmatter_tag
            for output in outputs:
                path = Path(output)
                if path.exists() and _set_private_frontmatter_tag(
                    path, tag == "private",
                ):
                    result["outputs"] += 1
        except Exception as exc:
            message = f"document output privacy: {exc}"
            result["errors"].append(message)
            print(f"[document-input privacy] {message}", flush=True)
    return result


def purge_conversation(conversation_id: str) -> dict[str, Any]:
    """Remove live document jobs and their Ora-owned correlated artifacts.

    Current uploads use a durable per-conversation staging subtree, which this
    helper can remove after a restart even when the in-memory job table is
    empty. Pre-change flat uploads remain attributable only while their live
    in-memory job survives; ambiguous orphaned legacy files are retained.
    """
    conversation_id = (conversation_id or "").strip()
    result: dict[str, Any] = {
        "jobs": 0,
        "staged_files": 0,
        "created_outputs": 0,
        "errors": [],
    }
    if (not conversation_id or conversation_id in {".", ".."}
            or len(conversation_id) > 255 or "/" in conversation_id
            or "\\" in conversation_id or "\x00" in conversation_id
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in conversation_id)):
        result["errors"].append("conversation_id is required")
        return result

    conversation_key = _conversation_key(conversation_id)
    with _lifecycle_lock:
        _deleted_conversations.add(conversation_key)
        with _jobs_lock:
            matched = [dict(job) for job in _jobs.values()
                       if _conversation_key(job.get("conversation_id"))
                       == conversation_key]
            for job in matched:
                _jobs.pop(str(job.get("processing_id") or ""), None)
        result["jobs"] = len(matched)

        staging_root = _rp.safe_owned_subdir(Path(STAGING_DIR), create=False)
        owned_staging_root = Path(STAGING_DIR) / conversation_key
        incubator = Path(VAULT_INCUBATOR_DIR)
        incubator_root: Path | None = None
        try:
            incubator_root = _rp.safe_owned_subdir(
                incubator.parent, incubator.name, create=False,
            )
        except Exception as exc:
            msg = f"Incubator ownership root {incubator}: {exc}"
            result["errors"].append(msg)
            print(f"[document-input purge] {msg}", flush=True)

        session_docs_root: Path | None = None
        try:
            session_docs_root = _rp.safe_owned_subdir(
                Path(STEALTH_TEMP_ROOT), conversation_key, "documents",
                create=False,
            )
        except Exception as exc:
            msg = f"session document ownership root: {exc}"
            result["errors"].append(msg)
            print(f"[document-input purge] {msg}", flush=True)

        for job in matched:
            source = job.get("source_path")
            if source:
                try:
                    source_parent = _absolute_entry(source).parent
                    owned_source_parent = staging_root
                    if os.path.normcase(str(source_parent)) == os.path.normcase(
                        str(_absolute_entry(owned_staging_root))
                    ):
                        owned_source_parent = _rp.safe_owned_subdir(
                            staging_root, conversation_key, create=False,
                        )
                    if _unlink_direct_owned_file(source, owned_source_parent):
                        result["staged_files"] += 1
                except Exception as exc:
                    msg = f"staged source {source}: {exc}"
                    result["errors"].append(msg)
                    print(f"[document-input purge] {msg}", flush=True)

            # Only delete a converted output this job actually created. A
            # title-deduplicated Incubator note may belong to another thread.
            output = job.get("vault_path")
            if output and job.get("output_created"):
                try:
                    removed = False
                    for owned_parent in (incubator_root, session_docs_root):
                        if owned_parent is not None and _unlink_direct_owned_file(
                            output, owned_parent,
                        ):
                            removed = True
                            break
                    if removed:
                        result["created_outputs"] += 1
                except Exception as exc:
                    msg = f"created output {output}: {exc}"
                    result["errors"].append(msg)
                    print(f"[document-input purge] {msg}", flush=True)

        # New uploads are grouped under an exact conversation-owned subtree,
        # so this remains precise after a process restart when `_jobs` is empty.
        try:
            if owned_staging_root.is_symlink():
                owned_staging_root.unlink()
                result["staged_files"] += 1
            elif owned_staging_root.is_dir():
                nested_files = 0
                for walk_root, dirnames, filenames in os.walk(
                    owned_staging_root, followlinks=False,
                ):
                    nested_files += len(filenames)
                    nested_files += sum(
                        1 for name in dirnames
                        if os.path.islink(os.path.join(walk_root, name))
                    )
                shutil.rmtree(owned_staging_root)
                result["staged_files"] += nested_files
            elif owned_staging_root.exists():
                raise ValueError(
                    f"refusing non-directory document staging path "
                    f"{owned_staging_root}"
                )
        except Exception as exc:
            msg = f"conversation staging {owned_staging_root}: {exc}"
            result["errors"].append(msg)
            print(f"[document-input purge] {msg}", flush=True)
    return result
