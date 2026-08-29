"""Conversation lifecycle persistence and close-out dispatch.

The V3 mode mechanism (Phase 1.1) carries each conversation's mode as a
``tag`` field on the conversation.json envelope (empty / ``stealth`` /
``private``). When the user closes a conversation, this module dispatches
the appropriate cleanup based on tag.  The lifecycle service also owns the
runtime propagation required when a retained conversation is renamed or moves
between Standard and Private, plus the explicit Delete Forever operation:

* empty (standard) → hide from sidebar. The envelope is stamped
  ``closed: true``; iter_conversations filters those out. Chunks,
  ChromaDB records, and vault exports are retained. Reversible by
  clearing the flag.
* ``stealth`` → full purge. All Ora-managed artifacts associated with the
  conversation are deleted: the session directory under ``~/ora/sessions/``,
  the per-pair chunk files in ``~/Documents/conversations/``, the raw
  session log in ``~/Documents/conversations/raw/``, and the ChromaDB
  records in the logical ``conversations`` collection. Explicit flat exports
  under ``~/Documents/vault/Sessions/*.md`` and their referenced sidecars are
  retained because the user deliberately created them. A legacy Ora-managed
  ``Sessions/<conversation_id>/`` directory is deleted.
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

import gzip
import json
import os
import re
import shutil
import sys
import threading
from pathlib import Path
from typing import Any, Callable

from . import runtime_paths as _rp
from .conversation_memory import (
    detach_direct_fork_children,
    get_conversation_tag,
    load_conversation_json,
    read_conversation_history_envelope,
    set_conversation_closed,
)


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

# Import-time value of the Layer 9 oversight-log root; patch-detection anchor
# (a test that patches runtime_paths.DATA_DIR_STR must win over the
# ORA_OVERSIGHT_SANDBOX quarantine, same precedence as every oversight writer).
_LIVE_OVERSIGHT_DIR = os.path.join(_rp.DATA_DIR_STR, "oversight")


def _validate_conversation_id(conversation_id: str) -> str:
    """Return a safe, non-empty filesystem segment or raise ``ValueError``.

    Conversation ids are also used as directory names.  Reject separators,
    traversal segments, control characters, and unreasonably long values
    before any path is derived.  Punctuation otherwise remains accepted for
    compatibility with legacy panel ids.
    """
    if not isinstance(conversation_id, str):
        raise ValueError("conversation_id must be a string")
    cid = conversation_id.strip()
    if not cid or cid in {".", ".."}:
        raise ValueError("conversation_id must be non-empty")
    if len(cid) > 255:
        raise ValueError("conversation_id is too long")
    if "/" in cid or "\\" in cid or "\x00" in cid:
        raise ValueError("conversation_id may not contain path separators")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in cid):
        raise ValueError("conversation_id may not contain control characters")
    return cid


def _conversation_identity(value: Any) -> str | None:
    """Return the case-stable lifecycle identity without folding punctuation."""
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized.casefold() if normalized else None


def _same_conversation(value: Any, conversation_id: str) -> bool:
    identity = _conversation_identity(value)
    return identity is not None and identity == conversation_id.casefold()


def _conversation_id_variants(conversation_id: str) -> tuple[str, ...]:
    """Return stored spellings queried during mixed-case migration."""
    folded = conversation_id.casefold()
    return ((conversation_id,) if folded == conversation_id
            else (conversation_id, folded))


def _record_error(errors: list[str], label: str, exc: BaseException | str) -> None:
    """Collect and loudly report a best-effort lifecycle failure."""
    message = f"{label}: {exc}"
    errors.append(message)
    print(f"[WARNING] conversation lifecycle {message}", file=sys.stderr, flush=True)


def _purge_framework_scratch_backstop(
    conversation_id: str,
    deleted: dict[str, Any],
    errors: list[str],
) -> None:
    """Remove orphaned Stealth Framework scratch owned by this conversation."""
    deleted["framework_scratch_execution_ids"] = []
    try:
        from orchestrator.scratch import purge_conversation_scratch

        result = purge_conversation_scratch(conversation_id)
        removed = result.get("removed") if isinstance(result, dict) else []
        deleted["framework_scratch_execution_ids"] = list(removed or [])
        for error in (result.get("errors") or []) if isinstance(result, dict) else []:
            _record_error(errors, "framework scratch", error)
    except Exception as exc:
        _record_error(errors, "framework scratch", exc)


def _atomic_write_text(path: Path, text: str) -> None:
    """Replace ``path`` without exposing a partially-written lifecycle file."""
    _rp.atomic_write_text(path, text)


def _safe_child(root: Path, name: str) -> Path:
    """Build one direct child without resolving/following a child symlink."""
    root_abs = Path(os.path.abspath(os.path.expanduser(str(root))))
    child = root_abs / name
    if child.parent != root_abs:
        raise ValueError(f"unsafe child path: {child}")
    return child


def _remove_tree_without_following(path: Path) -> bool:
    """Remove a tree or its symlink, never following a symlink target."""
    if path.is_symlink():
        path.unlink()
        return True
    if not path.exists():
        return False
    if not path.is_dir():
        raise ValueError(f"expected directory, found non-directory: {path}")
    shutil.rmtree(path)
    return True


def _unlink_without_following(path: Path) -> bool:
    """Unlink one file or symlink; reject directories and never recurse."""
    if path.is_symlink():
        path.unlink()
        return True
    if not path.exists():
        return False
    if not path.is_file():
        raise ValueError(f"expected file, found non-file: {path}")
    path.unlink()
    return True


def _artifact_path(value: str, *, within: Path | None = None) -> Path:
    """Validate an authoritative stored artifact path before mutation."""
    path = Path(os.path.expanduser(value))
    if not path.is_absolute():
        raise ValueError(f"artifact path must be absolute: {value!r}")
    if within is not None and not _rp.within_base(path, within):
        raise ValueError(
            f"artifact path is outside expected root {within}: {value!r}"
        )
    return path


def _record_matches(record: Any, conversation_id: str) -> bool:
    """Match lifecycle ownership keys at any bounded JSON nesting depth."""
    seen: set[int] = set()

    def visit(value: Any, depth: int = 0) -> bool:
        if depth > 32 or not isinstance(value, (dict, list, tuple)):
            return False
        identity = id(value)
        if identity in seen:
            return False
        seen.add(identity)
        if isinstance(value, dict):
            if (_same_conversation(value.get("conversation_id"), conversation_id)
                    or _same_conversation(value.get("panel_id"), conversation_id)):
                return True
            return any(visit(child, depth + 1) for child in value.values())
        return any(visit(child, depth + 1) for child in value)

    return visit(record)


def _rewrite_jsonl_unlocked(
    path: Path,
    *,
    errors: list[str],
    label: str,
    mutate: Callable[[dict[str, Any]], dict[str, Any] | None],
) -> int:
    """Atomically mutate/drop matching JSONL records, preserving bad lines.

    ``mutate`` returns the record to keep or ``None`` to drop it. Corrupt
    records are retained and reported loudly because silently discarding an
    unrelated record would be worse than leaving an unclassified residue.
    """
    if not path.exists():
        return 0
    if path.is_symlink() or not path.is_file():
        _record_error(errors, label, f"refusing non-regular file {path}")
        return 0
    changed = 0
    output: list[str] = []
    try:
        for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not raw.strip():
                continue
            try:
                record = json.loads(raw)
            except Exception as exc:
                _record_error(errors, f"{label} line {line_no}", exc)
                output.append(raw)
                continue
            if not isinstance(record, dict):
                output.append(raw)
                continue
            replacement = mutate(record)
            if replacement is None:
                changed += 1
                continue
            if replacement != record:
                changed += 1
                output.append(json.dumps(replacement, ensure_ascii=False))
            else:
                output.append(raw)
        if changed:
            text = "".join(line + "\n" for line in output)
            _atomic_write_text(path, text)
    except Exception as exc:
        _record_error(errors, label, exc)
        return 0
    return changed


def _rewrite_jsonl(
    path: Path,
    *,
    errors: list[str],
    label: str,
    mutate: Callable[[dict[str, Any]], dict[str, Any] | None],
) -> int:
    """Lock a JSONL sidecar across its complete read-modify-replace cycle."""
    if not path.exists():
        return 0
    try:
        with _rp.locked_file(path):
            return _rewrite_jsonl_unlocked(
                path, errors=errors, label=label, mutate=mutate,
            )
    except Exception as exc:
        _record_error(errors, f"{label} lock", exc)
        return 0


def _rewrite_gzip_jsonl(
    path: Path,
    *,
    errors: list[str],
    label: str,
    drop: Callable[[dict[str, Any]], bool],
) -> int:
    """Drop matching records from a gzip JSONL archive under its sidecar lock.

    Retention uses the same ``locked_file(path)`` convention before creating or
    deleting a rotated tool-event archive.  The identity check is an additional
    backstop against an older/uncoordinated process replacing the pathname while
    this process is reading it: never overwrite a different archive generation.
    """
    if not path.exists():
        return 0
    try:
        with _rp.locked_file(path):
            if not path.exists():
                return 0
            if path.is_symlink() or not path.is_file():
                _record_error(errors, label, f"refusing non-regular file {path}")
                return 0

            before = path.stat()
            identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            kept: list[str] = []
            removed = 0
            try:
                with gzip.open(path, "rt", encoding="utf-8") as fh:
                    for line_no, raw in enumerate(fh, 1):
                        line = raw.rstrip("\n")
                        if not line.strip():
                            continue
                        try:
                            record = json.loads(line)
                        except Exception as exc:
                            _record_error(errors, f"{label} line {line_no}", exc)
                            kept.append(line)
                            continue
                        if isinstance(record, dict) and drop(record):
                            removed += 1
                        else:
                            kept.append(line)
            except Exception as exc:
                _record_error(errors, label, exc)
                return 0

            if not removed:
                return 0

            tmp = path.with_name(
                f".{path.name}.tmp-{os.getpid()}-{threading.get_ident()}"
            )
            try:
                with gzip.open(tmp, "wt", encoding="utf-8") as fh:
                    for line in kept:
                        fh.write(line + "\n")

                if not path.exists():
                    # Retention removed the whole archive; do not resurrect it.
                    return 0
                current = path.stat()
                current_identity = (
                    current.st_dev,
                    current.st_ino,
                    current.st_size,
                    current.st_mtime_ns,
                )
                if current_identity != identity:
                    _record_error(
                        errors,
                        label,
                        "archive changed while locked; refusing replacement",
                    )
                    return 0
                os.replace(tmp, path)
                return removed
            finally:
                try:
                    if tmp.exists() or tmp.is_symlink():
                        tmp.unlink()
                except OSError:
                    pass
    except Exception as exc:
        _record_error(errors, f"{label} lock", exc)
        return 0


def _is_chromadb_collection_not_found(exc: BaseException) -> bool:
    """Return True only for Chroma's explicit collection-not-found error.

    Operational failures (corruption, permissions, an unavailable database,
    embedding binding errors, and so on) must remain visible to Delete Forever
    and privacy/rename callers.  Message matching would incorrectly turn any of
    those into an idempotent no-op, so use Chroma's typed error exclusively.
    """
    try:
        from chromadb.errors import NotFoundError  # type: ignore
    except Exception:
        return False
    return isinstance(exc, NotFoundError)


def _open_logical_collections(
    logical_name: str,
    *,
    chromadb_path: Path | None,
    collection: Any | None,
    errors: list[str],
) -> list[tuple[str, Any]]:
    """Open every active/rollback-visible physical copy of a logical corpus."""
    if collection is not None:
        return [("injected", collection)]
    chroma = Path(chromadb_path) if chromadb_path else _DEFAULT_CHROMADB_PATH
    try:
        import chromadb  # type: ignore
        from orchestrator.embedding import (
            discover_collection_copies,
            get_collection as _bound_get_collection,
            resolve_collection,
        )
        client = chromadb.PersistentClient(path=str(chroma))
        active = resolve_collection(logical_name)
        opened: list[tuple[str, Any]] = []
        for physical_name in discover_collection_copies(
            client, logical_name,
        ):
            try:
                if physical_name == active:
                    current = _bound_get_collection(client, logical_name)
                else:
                    # Metadata-only lifecycle operations do not embed, so an
                    # old collection can be opened without binding today's
                    # dimension-incompatible embedding function.
                    current = client.get_collection(name=physical_name)
                if current is not None:
                    opened.append((physical_name, current))
            except Exception as exc:
                if _is_chromadb_collection_not_found(exc):
                    continue
                _record_error(
                    errors,
                    f"chromadb {logical_name} collection {physical_name}", exc,
                )
        return opened
    except Exception as exc:
        _record_error(errors, f"chromadb {logical_name} open", exc)
        return []


def _open_conversations_collections(
    *,
    chromadb_path: Path | None,
    collection: Any | None,
    errors: list[str],
) -> list[tuple[str, Any]]:
    return _open_logical_collections(
        "conversations",
        chromadb_path=chromadb_path,
        collection=collection,
        errors=errors,
    )


def _conversation_collection_rows(
    collection: Any,
    conversation_id: str,
    *,
    errors: list[str],
    label: str,
) -> dict[str, dict[str, Any]]:
    """Collect exact/original plus casefolded conversation metadata rows."""
    rows: dict[str, dict[str, Any]] = {}
    for variant in _conversation_id_variants(conversation_id):
        try:
            result = collection.get(where={"conversation_id": variant})
            ids = result.get("ids") or []
            metas = result.get("metadatas") or []
            if len(ids) != len(metas):
                _record_error(
                    errors, label,
                    f"returned {len(ids)} ids but {len(metas)} metadata rows "
                    f"for {variant!r}",
                )
            for row_id, meta in zip(ids, metas):
                if not isinstance(meta, dict):
                    _record_error(
                        errors, f"{label} {row_id}", "metadata is not an object",
                    )
                    continue
                rows[str(row_id)] = meta
        except Exception as exc:
            _record_error(errors, f"{label} {variant}", exc)
    return rows


def _frontmatter_value(text: str, key: str) -> str | None:
    """Read a simple scalar from the first YAML frontmatter block."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    match = re.search(
        rf"(?m)^{re.escape(key)}\s*:\s*([^#\n]*?)\s*$", text[3:end]
    )
    if not match:
        return None
    value = match.group(1).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1]
    return value


def _set_private_frontmatter_tag(path: Path, private: bool) -> bool:
    """Add/remove the controlled ``private`` YAML tag in one chunk file."""
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"refusing non-regular chunk file {path}")
    text = path.read_text(encoding="utf-8")
    opening_end = text.find("\n") + 1
    if opening_end <= 0 or text[:opening_end].strip() != "---":
        raise ValueError("missing YAML frontmatter")
    close = text.find("\n---", opening_end)
    if close < 0:
        raise ValueError("unterminated YAML frontmatter")

    front = text[opening_end:close]
    lines = front.splitlines()
    tag_idx = next(
        (idx for idx, line in enumerate(lines) if re.match(r"^\s*tags\s*:", line)),
        None,
    )
    tags: list[str] = []
    start = end = len(lines)
    indent = ""
    if tag_idx is not None:
        start = tag_idx
        match = re.match(r"^(\s*)tags\s*:\s*(.*?)\s*$", lines[tag_idx])
        assert match is not None
        indent, inline = match.groups()
        if inline:
            try:
                import yaml  # type: ignore
                parsed = yaml.safe_load(inline)
                if isinstance(parsed, list):
                    tags = [str(item) for item in parsed if str(item).strip()]
                elif parsed not in (None, ""):
                    tags = [str(parsed)]
            except Exception:
                tags = [
                    part.strip(" '\"")
                    for part in inline.strip("[]").split(",")
                    if part.strip()
                ]
        end = tag_idx + 1
        while end < len(lines):
            item = re.match(rf"^{re.escape(indent)}\s+-\s+(.+?)\s*$", lines[end])
            if not item:
                break
            value = item.group(1).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            if value:
                tags.append(value)
            end += 1
    else:
        # Keep core properties together: insert before the first date field,
        # otherwise append at the end of frontmatter.
        start = next(
            (
                idx for idx, line in enumerate(lines)
                if re.match(r"^date (created|modified)\s*:", line)
            ),
            len(lines),
        )
        end = start

    deduped: list[str] = []
    for value in tags:
        if value != "private" and value not in deduped:
            deduped.append(value)
    if private:
        deduped.append("private")
    replacement = [f"{indent}tags:"]
    replacement.extend(f"{indent}  - {value}" for value in deduped)
    new_lines = lines[:start] + replacement + lines[end:]
    # Recovered pending chunks also carry a legacy scalar ``tag`` field.
    # Keep it synchronized when present; canonical chunks do not have it.
    for idx, line in enumerate(new_lines):
        match = re.match(r"^(\s*)tag\s*:\s*.*$", line)
        if match:
            new_lines[idx] = f"{match.group(1)}tag: {('private' if private else '')}"
            break
    new_front = "\n".join(new_lines)
    new_text = text[:opening_end] + new_front + text[close:]
    if new_text == text:
        return False
    _atomic_write_text(path, new_text)
    return True


def _scan_recovered_chunks(root: Path, conversation_id: str) -> list[Path]:
    """Find orphan-recovery chunks whose YAML records this conversation."""
    found: list[Path] = []
    if not root.exists() or root.is_symlink() or not root.is_dir():
        return found
    for path in root.rglob("*.md"):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                head = fh.read(8192)
        except OSError:
            continue
        if (_same_conversation(
                _frontmatter_value(head, "conversation_id"), conversation_id)
                or _same_conversation(
                    _frontmatter_value(head, "panel_id"), conversation_id)):
            found.append(path)
    return found


def _has_conversation_marker(text: str, conversation_id: str) -> bool:
    """Match the redundant JSON marker using the casefold lifecycle identity."""
    for raw in re.findall(r"(?m)^<!-- ora-conversation-id:\s*(.+?)\s*-->$", text):
        try:
            value = json.loads(raw)
        except Exception:
            continue
        if _same_conversation(value, conversation_id):
            return True
    return False


def _scan_owned_chunks(root: Path, conversation_id: str) -> list[Path]:
    """Find canonical chunks by their redundant exact ownership marker.

    The marker is written into every new chunk before indexing. It is the
    final recovery path when both Chroma and the manifest write failed; unlike
    a lossy filename slug it cannot conflate two conversation ids.
    """
    found: list[Path] = []
    if not root.exists() or root.is_symlink() or not root.is_dir():
        return found
    for path in root.rglob("*.md"):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                head = fh.read(8192)
        except OSError:
            continue
        if _has_conversation_marker(head, conversation_id):
            found.append(path)
    return found


def _owned_chunk_path(
    value: str,
    *,
    default_root: Path,
    conversation_id: str,
    manifest_record: dict[str, Any] | None = None,
) -> Path:
    """Validate a default or explicitly-ledgered custom chunk path.

    Legacy live chunks under the configured conversations root predate
    ownership markers and remain eligible. Historical-import migration is
    never allowed that fallback: its old computed filenames can collide with
    unrelated files, so the safe historical id requires an exact marker even
    under the default root. A custom path is eligible only when the
    current file carries the exact conversation marker; manifest-discovered
    custom paths additionally require the new typed ownership fields and an
    exact parent/root match. This preserves custom output destinations without
    turning a corrupted manifest into arbitrary-file mutation authority.
    """
    path = _artifact_path(value)
    require_historical_marker = bool(
        re.fullmatch(r"historical-[0-9a-f]{12}", conversation_id)
    )
    if _rp.within_base(path, default_root) and not require_historical_marker:
        return path
    if manifest_record is not None:
        if (manifest_record.get("artifact_kind") != "conversation_chunk"
                or manifest_record.get("managed_by") != "ora"):
            raise ValueError("custom chunk lacks typed Ora ownership fields")
        root_value = manifest_record.get("chunk_root")
        if not isinstance(root_value, str) or not root_value:
            raise ValueError("custom chunk lacks chunk_root")
        root = _artifact_path(root_value)
        if path.parent != root:
            raise ValueError("custom chunk path is outside its recorded root")
    if path.is_symlink() or not path.is_file():
        raise ValueError("custom chunk is missing or not a regular file")
    with open(path, encoding="utf-8") as stream:
        head = stream.read(8192)
    if not _has_conversation_marker(head, conversation_id):
        raise ValueError("custom chunk ownership marker mismatch")
    return path


def _iter_regular_markdown(
    root: Path, *, errors: list[str] | None = None,
):
    """Yield markdown below ``root`` and report incomplete scans loudly."""
    try:
        if not root.exists():
            return
        if root.is_symlink() or not root.is_dir():
            if errors is not None:
                _record_error(errors, f"runtime derivative scan {root}",
                              "refusing symlinked/non-directory root")
            return
    except OSError as exc:
        if errors is not None:
            _record_error(errors, f"runtime derivative scan {root}", exc)
        return

    def onerror(exc: OSError) -> None:
        if errors is not None:
            _record_error(errors, f"runtime derivative scan {root}", exc)

    for dirpath, dirnames, filenames in os.walk(
        root, followlinks=False, onerror=onerror,
    ):
        base = Path(dirpath)
        safe_dirs: list[str] = []
        for name in dirnames:
            child = base / name
            try:
                if not child.is_symlink():
                    safe_dirs.append(name)
            except OSError as exc:
                if errors is not None:
                    _record_error(errors, f"runtime derivative scan {child}", exc)
        dirnames[:] = safe_dirs
        for name in filenames:
            if not name.endswith(".md"):
                continue
            path = base / name
            try:
                if not path.is_symlink() and path.is_file():
                    yield path
            except OSError as exc:
                if errors is not None:
                    _record_error(errors, f"runtime derivative scan {path}", exc)


def _note_has_runtime_provenance(
    path: Path,
    source_ids: set[str],
    *,
    strict_ownership: bool = False,
    errors: list[str] | None = None,
) -> bool:
    """Return whether an auto-derived note belongs to one source exactly."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        if errors is not None:
            _record_error(errors, f"runtime derivative read {path}", exc)
        return False
    source_identities = {value.casefold() for value in source_ids}
    source = _frontmatter_value(text, "source_file")
    source_matches = (
        isinstance(source, str) and source.casefold() in source_identities
    )
    legacy_matches = any(
        re.search(
            rf"(?m)^- Source: extracted from session {re.escape(source_id)}\s*$",
            text,
            re.IGNORECASE,
        )
        for source_id in source_ids
    )
    if strict_ownership and (source_matches or legacy_matches):
        owned = (
            _frontmatter_value(text, "artifact_kind")
            == "conversation_runtime_derivative"
            and _frontmatter_value(text, "managed_by") == "ora"
        )
        if not owned and errors is not None:
            _record_error(
                errors,
                f"ambiguous runtime derivative {path}",
                "matching source provenance lacks the complete Ora ownership "
                "marker; retained to protect user-authored vault content",
            )
        return bool(owned and source_matches)
    if source_matches:
        return True
    # Compatibility for runtime notes produced before source_file was emitted
    # into YAML. This is accepted only in Ora's non-vault data roots.
    return legacy_matches


def _add_runtime_source_id(source_ids: set[str], value: str) -> None:
    """Add the stored spelling plus the cross-platform lifecycle identity."""
    if not isinstance(value, str) or not value:
        return
    source_ids.add(value)
    source_ids.add(value.casefold())


def _runtime_derivative_roots(vault_root: Path | None = None) -> tuple[Path, ...]:
    """Ora-managed note roots; explicit ``Vault/Sessions`` is absent."""
    vault = Path(vault_root) if vault_root else Path(_rp.VAULT_STR)
    return (
        Path(_rp.DATA_DIR_STR) / "extraction-staging",
        Path(_rp.DATA_DIR_STR) / "extraction-promoted",
        vault / "Engrams",
        vault / "Incubator",
    )


def _managed_transcript_files(
    source_ids: set[str], vault_root: Path | None = None,
    *, errors: list[str] | None = None,
) -> list[Path]:
    """Find root-level transcripts carrying the complete Ora ownership triple."""
    vault = Path(vault_root) if vault_root else Path(_rp.VAULT_STR)
    found: list[Path] = []
    source_identities = {value.casefold() for value in source_ids}
    try:
        if not vault.exists():
            return found
        if vault.is_symlink() or not vault.is_dir():
            if errors is not None:
                _record_error(errors, f"managed transcript scan {vault}",
                              "refusing symlinked/non-directory vault root")
            return found
    except OSError as exc:
        if errors is not None:
            _record_error(errors, f"managed transcript scan {vault}", exc)
        return found
    try:
        candidates = list(vault.iterdir())
    except OSError as exc:
        if errors is not None:
            _record_error(errors, f"managed transcript scan {vault}", exc)
        return found
    for path in candidates:
        try:
            eligible = (
                path.suffix.lower() == ".md"
                and not path.is_symlink()
                and path.is_file()
            )
        except OSError as exc:
            if errors is not None:
                _record_error(errors, f"managed transcript scan {path}", exc)
            continue
        if not eligible:
            continue
        try:
            with open(path, encoding="utf-8") as stream:
                head = stream.read(8192)
        except OSError as exc:
            if errors is not None:
                _record_error(errors, f"managed transcript read {path}", exc)
            continue
        source = _frontmatter_value(head, "source_file")
        if (_frontmatter_value(head, "artifact_kind")
                != "conversation_transcript"
                or _frontmatter_value(head, "managed_by") != "ora"
                or not isinstance(source, str)
                or source.casefold() not in source_identities):
            continue
        found.append(path)
    return found


def _runtime_derivative_files(
    source_ids: set[str], vault_root: Path | None = None,
    *, errors: list[str] | None = None,
) -> list[Path]:
    found: list[Path] = []
    roots = _runtime_derivative_roots(vault_root)
    for index, root in enumerate(roots):
        for path in _iter_regular_markdown(root, errors=errors) or ():
            if _note_has_runtime_provenance(
                path,
                source_ids,
                strict_ownership=index >= 2,
                errors=errors,
            ):
                found.append(path)
    for path in _managed_transcript_files(
        source_ids, vault_root, errors=errors,
    ):
        if path not in found:
            found.append(path)
    return found


def _retire_legacy_entity_index(errors: list[str]) -> bool:
    """Remove the unused title-only entity cache as one disposable derivative.

    ``runtime_pipeline`` was the only writer and the repository has no reader.
    The legacy format carries no source identity, so selective privacy/delete
    updates are impossible; removing the unused cache is the only exact and
    lossless lifecycle behavior.
    """
    path = Path(_rp.DATA_DIR_STR) / "entity-index.json"
    try:
        if not (path.exists() or path.is_symlink()):
            return False
        if path.is_dir() and not path.is_symlink():
            raise ValueError(f"refusing non-file entity index {path}")
        path.unlink()
        return True
    except Exception as exc:
        _record_error(errors, "retired entity index", exc)
        return False


def _remove_paths_from_vault_index(
    paths: list[Path], errors: list[str],
) -> int:
    """Remove exact managed artifact paths from the historical vault cache."""
    if not paths:
        return 0
    index_path = Path(_rp.DATA_DIR_STR) / "vault-index.json"
    if not index_path.exists():
        return 0
    try:
        with _rp.locked_file(index_path):
            if index_path.is_symlink() or not index_path.is_file():
                raise ValueError(f"refusing non-regular vault index {index_path}")
            payload = json.loads(index_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("vault index is not an object")
            entries = payload.get("entries")
            if not isinstance(entries, list):
                raise ValueError("vault index entries are not a list")
            root_value = payload.get("vault_path")
            if not isinstance(root_value, str) or not root_value:
                raise ValueError("vault index has no vault_path")
            vault_root = Path(os.path.abspath(os.path.expanduser(root_value)))
            target_keys = {_rp.norm_key(path) for path in paths}
            kept: list[Any] = []
            removed = 0
            for entry in entries:
                if not isinstance(entry, dict):
                    kept.append(entry)
                    continue
                relative = entry.get("vault_path")
                if not isinstance(relative, str) or not relative:
                    kept.append(entry)
                    continue
                candidate = vault_root / relative
                if (not _rp.within_base(candidate, vault_root)
                        or _rp.norm_key(candidate) not in target_keys):
                    kept.append(entry)
                    continue
                removed += 1
            if removed:
                payload["entries"] = kept
                _atomic_write_text(
                    index_path,
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                )
            return removed
    except Exception as exc:
        _record_error(errors, "vault index cleanup", exc)
        return 0


def _add_paths_to_vault_index(
    paths: list[Path], errors: list[str], *, vault_root: Path | None = None,
) -> int:
    """Synchronously restore exact Standard derivatives to the vault cache."""
    if not paths:
        return 0
    index_path = Path(_rp.DATA_DIR_STR) / "vault-index.json"
    if not index_path.exists():
        return 0
    try:
        from orchestrator.tools import vault_indexer
        with _rp.locked_file(index_path):
            if index_path.is_symlink() or not index_path.is_file():
                raise ValueError(f"refusing non-regular vault index {index_path}")
            payload = json.loads(index_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("vault index is not an object")
            entries = payload.get("entries")
            if not isinstance(entries, list):
                raise ValueError("vault index entries are not a list")
            root_value = payload.get("vault_path")
            root = (
                Path(vault_root).expanduser().resolve(strict=False)
                if vault_root is not None
                else Path(str(root_value or "")).expanduser().resolve(strict=False)
            )
            if not str(root_value or "") and vault_root is None:
                raise ValueError("vault index has no vault_path")

            by_relative = {
                entry.get("vault_path"): entry
                for entry in entries if isinstance(entry, dict)
                and isinstance(entry.get("vault_path"), str)
            }
            next_id = 1
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                match = re.fullmatch(r"vault-(\d+)", str(entry.get("id") or ""))
                if match:
                    next_id = max(next_id, int(match.group(1)) + 1)

            changed = 0
            for path in paths:
                candidate = path.expanduser().resolve(strict=False)
                if (candidate.is_symlink() or not candidate.is_file()
                        or not _rp.within_base(candidate, root)):
                    continue
                relative = str(candidate.relative_to(root))
                existing = by_relative.get(relative)
                entry_id = (
                    str(existing.get("id") or "")
                    if isinstance(existing, dict) else ""
                )
                if not entry_id:
                    entry_id = f"vault-{next_id:04d}"
                    next_id += 1
                replacement = vault_indexer.build_entry(
                    candidate, root, entry_id,
                )
                replacement_dict = {
                    field: getattr(replacement, field)
                    for field in replacement.__dataclass_fields__
                }
                if existing is None:
                    entries.append(replacement_dict)
                else:
                    entries[entries.index(existing)] = replacement_dict
                by_relative[relative] = replacement_dict
                changed += 1
            if changed:
                payload["entries"] = entries
                payload["vault_path"] = str(root)
                _atomic_write_text(
                    index_path,
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                )
            return changed
    except Exception as exc:
        _record_error(errors, "vault index restore", exc)
        return 0


def _metadata_with_private_tag(meta: dict[str, Any], private: bool) -> dict[str, Any]:
    replacement = dict(meta)
    raw_tags = replacement.get("tags") or []
    if isinstance(raw_tags, str):
        try:
            decoded = json.loads(raw_tags)
            tags = decoded if isinstance(decoded, list) else [raw_tags]
        except Exception:
            tags = [part.strip() for part in raw_tags.split(",") if part.strip()]
    elif isinstance(raw_tags, list):
        tags = list(raw_tags)
    else:
        tags = []
    tags = [str(value) for value in tags if str(value) != "private"]
    if private:
        tags.append("private")
    if tags:
        replacement["tags"] = tags
    else:
        replacement.pop("tags", None)
    replacement["tag_private"] = private
    return replacement


def _open_knowledge_collections(
    chromadb_path: Path,
    errors: list[str],
    *,
    collection: Any | None = None,
) -> list[tuple[str, Any]]:
    return _open_logical_collections(
        "knowledge",
        chromadb_path=chromadb_path,
        collection=collection,
        errors=errors,
    )


def _runtime_knowledge_row_owned(
    row_id: str,
    metadata: dict[str, Any],
    owned_paths: list[Path],
) -> bool:
    """Require a typed marker or an exact already-validated derivative path."""
    if (metadata.get("artifact_kind") == "conversation_runtime_derivative"
            and metadata.get("managed_by") == "ora"):
        return True
    keys = {_rp.norm_key(path) for path in owned_paths}
    candidates: list[str] = []
    path_value = metadata.get("path")
    if isinstance(path_value, str) and path_value:
        candidates.append(path_value)
    raw_id = str(row_id or "")
    if raw_id:
        candidates.append(re.sub(r"#chunk-\d+$", "", raw_id))
    return any(_rp.norm_key(value) in keys for value in candidates)


def _refresh_ped_derivative_indexes(
    report: dict[str, Any],
    *,
    chromadb_path: Path,
    vault_root: Path,
    errors: list[str],
    collection: Any | None = None,
    remove_vault_first: bool,
) -> dict[str, Any]:
    """Replace caches after a surgical managed PED block mutation.

    Existing knowledge rows are deleted before any read/embed attempt. If the
    Markdown mutation, read, embedding, or add fails, the old row therefore
    cannot keep exposing the pre-lifecycle block.
    """
    result: dict[str, Any] = {
        "paths": [],
        "knowledge_rows_removed": 0,
        "knowledge_files_reindexed": 0,
        "vault_entries_removed": 0,
        "vault_entries_refreshed": 0,
    }
    root = Path(vault_root).expanduser().resolve(strict=False)
    failed_keys = {
        _rp.norm_key(value) for value in report.get("failed_paths") or []
    }
    paths: list[Path] = []
    for raw_path in report.get("requires_reindex") or []:
        try:
            path = Path(str(raw_path)).expanduser().absolute()
            if not _rp.within_base(path, root):
                raise ValueError(f"PED path is outside vault root {root}: {path}")
            if path.is_symlink():
                raise ValueError(f"refusing symlinked PED path {path}")
            if all(_rp.norm_key(path) != _rp.norm_key(existing) for existing in paths):
                paths.append(path)
        except Exception as exc:
            _record_error(errors, "PED index path", exc)
    result["paths"] = [str(path) for path in paths]

    if remove_vault_first:
        result["vault_entries_removed"] = _remove_paths_from_vault_index(
            paths, errors,
        )
    safe_paths = [
        path for path in paths if _rp.norm_key(path) not in failed_keys
    ]

    try:
        from orchestrator.tools import knowledge_index
        collections = _open_knowledge_collections(
            chromadb_path, errors, collection=collection,
        )
        deleted_ok: set[tuple[str, str]] = set()
        # Pass 1 is exhaustive and fail-overprotective: no embedding/read/add
        # failure on an early path can leave a later stale row untouched.
        for physical_name, current in collections:
            for path in paths:
                try:
                    # Strict preflight: unlike the compatibility helper's
                    # best-effort fallback, lifecycle refresh must know that
                    # chunked ids were resolved before it can safely re-add.
                    knowledge_index.resolve_file_ids(current, str(path))
                    removed = knowledge_index.delete_file_records(
                        current, str(path),
                    )
                except Exception as exc:
                    removed = 0
                    _record_error(
                        errors,
                        f"PED knowledge delete {physical_name} {path}", exc,
                    )
                if removed <= 0:
                    _record_error(
                        errors,
                        f"PED knowledge delete {physical_name} {path}",
                        "delete_file_records failed",
                    )
                    continue
                result["knowledge_rows_removed"] += removed
                deleted_ok.add((physical_name, _rp.norm_key(path)))

        # Pass 2 re-adds only successfully mutated/readable paths whose old
        # rows were removed in Pass 1. Each path failure is independent.
        for physical_name, current in collections:
            for path in safe_paths:
                if (physical_name, _rp.norm_key(path)) not in deleted_ok:
                    continue
                try:
                    exists = path.exists()
                except OSError as exc:
                    _record_error(
                        errors,
                        f"PED knowledge reindex {physical_name} {path}",
                        exc,
                    )
                    continue
                if not exists:
                    continue
                if not path.is_file() or path.is_symlink():
                    _record_error(
                        errors,
                        f"PED knowledge reindex {physical_name} {path}",
                        "refusing non-regular PED path",
                    )
                    continue
                stats = {"indexed": 0, "skipped": 0, "errors": 0}
                try:
                    knowledge_index.index_file(
                        current, str(path), stats, force=False, verbose=False,
                    )
                except Exception as exc:
                    _record_error(
                        errors,
                        f"PED knowledge reindex {physical_name} {path}", exc,
                    )
                    continue
                if stats.get("indexed"):
                    result["knowledge_files_reindexed"] += 1
                else:
                    _record_error(
                        errors,
                        f"PED knowledge reindex {physical_name} {path}",
                        f"indexer did not add a row: {stats}",
                    )
    except Exception as exc:
        _record_error(errors, "PED knowledge refresh", exc)

    # Refresh the non-vector vault cache from the now-scrubbed/restored file.
    # Tightening/Delete removed every old entry first; failed paths stay absent.
    result["vault_entries_refreshed"] = _add_paths_to_vault_index(
        safe_paths, errors, vault_root=root,
    )
    return result


def _update_runtime_derivative_privacy(
    source_ids: set[str],
    private: bool,
    *,
    chromadb_path: Path,
    errors: list[str],
    vault_root: Path | None = None,
    collection: Any | None = None,
) -> tuple[list[str], int, int]:
    """Retag auto-derived notes and their logical knowledge index rows."""
    paths = _runtime_derivative_files(source_ids, vault_root, errors=errors)
    updated_files: list[str] = []
    for path in paths:
        try:
            if _set_private_frontmatter_tag(path, private):
                updated_files.append(str(path))
        except Exception as exc:
            _record_error(errors, f"runtime derivative privacy {path}", exc)

    vault_index_entries = (
        _remove_paths_from_vault_index(paths, errors)
        if private
        else _add_paths_to_vault_index(
            paths, errors, vault_root=vault_root,
        )
    )
    collections = _open_knowledge_collections(
        chromadb_path, errors, collection=collection,
    )
    if not collections:
        return updated_files, 0, vault_index_entries
    updated_rows = 0
    for physical_name, current in collections:
        rows: dict[str, dict[str, Any]] = {}
        for source_id in source_ids:
            try:
                result = current.get(where={"source_file": source_id})
                for row_id, meta in zip(
                    result.get("ids") or [], result.get("metadatas") or [],
                ):
                    if (isinstance(meta, dict)
                            and _runtime_knowledge_row_owned(
                                str(row_id), meta, paths,
                            )):
                        rows[str(row_id)] = meta
                    elif isinstance(meta, dict):
                        _record_error(
                            errors,
                            f"ambiguous runtime knowledge row {physical_name} "
                            f"{row_id}",
                            "matching source_file lacks typed Ora ownership or "
                            "an exact validated derivative path; retained",
                        )
            except Exception as exc:
                _record_error(
                    errors,
                    f"runtime derivative metadata query {physical_name} "
                    f"{source_id}", exc,
                )
        # Compatibility: old rows may lack source_file, but knowledge_index
        # uses each absolute note path as its stable id.
        for path in paths:
            row_ids = {
                os.path.abspath(str(path)),
                str(path.resolve(strict=False)),
            }
            for row_id in row_ids:
                try:
                    # HCP chunked rows use ``<absolute path>#chunk-N`` ids, so
                    # an exact bare-id probe cannot find them. Their durable
                    # path metadata remains the compatibility identity.
                    result = current.get(where={"path": row_id})
                    for found_id, meta in zip(
                        result.get("ids") or [], result.get("metadatas") or [],
                    ):
                        if isinstance(meta, dict):
                            rows[str(found_id)] = meta
                except Exception as exc:
                    _record_error(
                        errors,
                        f"runtime derivative metadata-path query "
                        f"{physical_name} "
                        f"{path}", exc,
                    )
            for row_id in row_ids:
                if row_id in rows:
                    continue
                try:
                    result = current.get(ids=[row_id])
                    ids = result.get("ids") or []
                    metas = result.get("metadatas") or []
                    if ids and metas and isinstance(metas[0], dict):
                        rows[str(ids[0])] = metas[0]
                except Exception as exc:
                    _record_error(
                        errors,
                        f"runtime derivative path query {physical_name} "
                        f"{path}", exc,
                    )
        for row_id, meta in rows.items():
            try:
                current.update(
                    ids=[row_id],
                    metadatas=[_metadata_with_private_tag(meta, private)],
                )
                updated_rows += 1
            except Exception as exc:
                _record_error(
                    errors,
                    f"runtime derivative metadata {physical_name} {row_id}", exc,
                )
    return updated_files, updated_rows, vault_index_entries


def _delete_runtime_derivatives(
    source_ids: set[str],
    *,
    chromadb_path: Path,
    errors: list[str],
    vault_root: Path | None = None,
) -> tuple[list[str], int, list[str], int]:
    """Delete auto-derived notes/logs/index rows, never explicit exports."""
    paths = _runtime_derivative_files(source_ids, vault_root, errors=errors)
    vault_index_entries = _remove_paths_from_vault_index(paths, errors)
    collections = _open_knowledge_collections(chromadb_path, errors)
    indexed_count = 0
    for physical_name, collection in collections:
        indexed_ids: set[str] = set()
        for source_id in source_ids:
            try:
                result = collection.get(where={"source_file": source_id})
                for row_id, meta in zip(
                    result.get("ids") or [], result.get("metadatas") or [],
                ):
                    if (isinstance(meta, dict)
                            and _runtime_knowledge_row_owned(
                                str(row_id), meta, paths,
                            )):
                        indexed_ids.add(str(row_id))
                    elif isinstance(meta, dict):
                        _record_error(
                            errors,
                            f"ambiguous runtime knowledge delete row "
                            f"{physical_name} {row_id}",
                            "matching source_file lacks typed Ora ownership or "
                            "an exact validated derivative path; retained",
                        )
            except Exception as exc:
                _record_error(
                    errors,
                    f"runtime derivative delete query {physical_name} "
                    f"{source_id}", exc,
                )
        for path in paths:
            row_ids = {
                os.path.abspath(str(path)),
                str(path.resolve(strict=False)),
            }
            for row_id in row_ids:
                try:
                    # HCP chunked rows keep the absolute note path in metadata
                    # while suffixing each row id with ``#chunk-N``.
                    result = collection.get(where={"path": row_id})
                    indexed_ids.update(
                        str(value) for value in result.get("ids") or []
                    )
                except Exception as exc:
                    _record_error(
                        errors,
                        f"runtime derivative delete metadata-path query "
                        f"{physical_name} "
                        f"{path}", exc,
                    )
            for row_id in row_ids:
                if row_id in indexed_ids:
                    continue
                try:
                    result = collection.get(ids=[row_id])
                    indexed_ids.update(
                        str(value) for value in result.get("ids") or []
                    )
                except Exception as exc:
                    _record_error(
                        errors,
                        f"runtime derivative delete path query {physical_name} "
                        f"{path}", exc,
                    )
        if indexed_ids:
            try:
                collection.delete(ids=sorted(indexed_ids))
                indexed_count += len(indexed_ids)
            except Exception as exc:
                _record_error(
                    errors,
                    f"runtime derivative metadata delete {physical_name}", exc,
                )

    removed_files: list[str] = []
    for path in paths:
        try:
            if _unlink_without_following(path):
                removed_files.append(str(path))
        except Exception as exc:
            _record_error(errors, f"runtime derivative file {path}", exc)

    removed_logs: list[str] = []
    log_root = Path(_rp.DATA_DIR_STR) / "session-logs"
    for source_id in source_ids:
        for suffix in (".json", "-runtime.json"):
            try:
                log_path = _safe_child(log_root, f"{source_id}{suffix}")
                if _unlink_without_following(log_path):
                    removed_logs.append(str(log_path))
            except Exception as exc:
                _record_error(errors, f"runtime session log {source_id}", exc)
    return removed_files, indexed_count, removed_logs, vault_index_entries


def refresh_conversation_title_metadata(
    conversation_id: str,
    title: str,
    *,
    chromadb_path: Path | None = None,
    collection: Any | None = None,
    previous_title: str = "",
    daily_notes_dir: Path | None = None,
) -> dict[str, Any]:
    """Refresh ``conversation_title`` on every logical conversation chunk.

    The conversation envelope remains authoritative; this function updates
    only the retrieval denormalization after ``set_display_name`` has
    succeeded. All other metadata keys are preserved verbatim.
    """
    cid = _validate_conversation_id(conversation_id)
    # Stored display names are authoritative up to the envelope's 200-char
    # limit. Derived fallbacks arrive already capped by the caller.
    normalized_title = str(title or "").strip()[:200]
    if not normalized_title:
        raise ValueError("conversation_title must be non-empty")
    errors: list[str] = []
    updated = 0
    collections = _open_conversations_collections(
        chromadb_path=chromadb_path, collection=collection, errors=errors,
    )
    for physical_name, col in collections:
        rows = _conversation_collection_rows(
            col, cid, errors=errors,
            label=f"title metadata query {physical_name}",
        )
        for chunk_id, meta in rows.items():
            replacement = dict(meta)
            replacement["conversation_title"] = normalized_title
            try:
                col.update(ids=[chunk_id], metadatas=[replacement])
                updated += 1
            except Exception as exc:
                _record_error(
                    errors, f"title metadata {physical_name} {chunk_id}", exc,
                )

    daily_notes: dict[str, Any] = {}
    try:
        from orchestrator.tools.daily_note import reconcile_conversation_summaries
        daily_notes = reconcile_conversation_summaries(
            cid,
            action="rename",
            new_display_name=normalized_title,
            previous_display_name=previous_title,
            daily_notes_dir=daily_notes_dir,
        )
        for error in daily_notes.get("errors") or []:
            _record_error(errors, "daily-note title", error)
    except Exception as exc:
        _record_error(errors, "daily-note title", exc)
    return {
        "conversation_id": cid,
        "conversation_title": normalized_title,
        "chromadb_records": updated,
        "daily_notes": daily_notes,
        "errors": errors,
    }


def _update_submission_tags(
    raw_root: Path,
    conversation_id: str,
    tag: str,
    errors: list[str],
) -> int:
    updated = 0
    for bucket in ("pending", "processed"):
        directory = _safe_child(raw_root, bucket)
        if not directory.exists():
            continue
        if directory.is_symlink() or not directory.is_dir():
            _record_error(errors, f"submission tags {directory}", "refusing non-directory")
            continue
        for path in sorted(directory.glob("*.json")):
            if path.is_symlink() or not path.is_file():
                _record_error(errors, f"submission tags {path}", "refusing non-regular file")
                continue
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                if not _record_matches(record, conversation_id):
                    continue
                if record.get("tag") == tag:
                    continue
                record["tag"] = tag
                _atomic_write_text(
                    path, json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                )
                updated += 1
            except Exception as exc:
                _record_error(errors, f"submission tags {path}", exc)
    return updated


def _delete_submission_records(
    raw_root: Path,
    conversation_id: str,
    errors: list[str],
) -> int:
    removed = 0
    for bucket in ("pending", "processed"):
        directory = _safe_child(raw_root, bucket)
        if not directory.exists():
            continue
        if directory.is_symlink() or not directory.is_dir():
            _record_error(errors, f"submission purge {directory}", "refusing non-directory")
            continue
        for path in sorted(directory.glob("*.json")):
            if path.is_symlink() or not path.is_file():
                _record_error(errors, f"submission purge {path}", "refusing non-regular file")
                continue
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                if _record_matches(record, conversation_id) and _unlink_without_following(path):
                    removed += 1
            except Exception as exc:
                _record_error(errors, f"submission purge {path}", exc)
    return removed


def _update_raw_log_privacy_headers(
    raw_root: Path,
    conversation_id: str,
    private: bool,
    errors: list[str],
) -> list[str]:
    """Retag exact owned raw-audit headers without touching exchange text."""
    updated: list[str] = []
    if not raw_root.exists():
        return updated
    if raw_root.is_symlink() or not raw_root.is_dir():
        _record_error(errors, f"raw privacy {raw_root}",
                      "refusing non-directory")
        return updated
    for path in sorted(raw_root.glob("*.md")):
        if path.is_symlink() or not path.is_file():
            _record_error(errors, f"raw privacy {path}",
                          "refusing non-regular file")
            continue
        try:
            with _rp.locked_file(path):
                text = path.read_text(encoding="utf-8")
                boundary = re.search(r"(?m)^---\s*$", text)
                if boundary is None:
                    continue
                header = text[:boundary.start()]
                panel = re.search(
                    r"(?m)^panel_id\s*:\s*([^#\n]*?)\s*$", header,
                )
                value = panel.group(1).strip() if panel else ""
                if (len(value) >= 2 and value[0] == value[-1]
                        and value[0] in "'\""):
                    value = value[1:-1]
                if not _same_conversation(value, conversation_id):
                    continue

                tag_value = "private" if private else ""
                replacement_header = header
                if re.search(r"(?m)^tag\s*:", replacement_header):
                    replacement_header = re.sub(
                        r"(?m)^tag\s*:.*$", f"tag: {tag_value}",
                        replacement_header, count=1,
                    )
                else:
                    replacement_header += f"tag: {tag_value}\n"
                bool_value = "true" if private else "false"
                if re.search(r"(?m)^tag_private\s*:", replacement_header):
                    replacement_header = re.sub(
                        r"(?m)^tag_private\s*:.*$",
                        f"tag_private: {bool_value}",
                        replacement_header, count=1,
                    )
                else:
                    replacement_header += f"tag_private: {bool_value}\n"
                replacement = replacement_header + text[boundary.start():]
                if replacement != text:
                    _atomic_write_text(path, replacement)
                    updated.append(str(path))
        except Exception as exc:
            _record_error(errors, f"raw privacy {path}", exc)
    return updated


def update_conversation_privacy_tag(
    conversation_id: str,
    tag: str,
    *,
    sessions_root: Path | None = None,
    conversations_dir: Path | None = None,
    conversations_raw: Path | None = None,
    chromadb_path: Path | None = None,
    collection: Any | None = None,
    knowledge_collection: Any | None = None,
    vault_root: Path | None = None,
) -> dict[str, Any]:
    """Cross-process-serialized Standard/Private mutation."""
    cid = _validate_conversation_id(conversation_id)
    with _rp.conversation_lifecycle_lock(cid):
        return _update_conversation_privacy_tag_unlocked(
            cid,
            tag,
            sessions_root=sessions_root,
            conversations_dir=conversations_dir,
            conversations_raw=conversations_raw,
            chromadb_path=chromadb_path,
            collection=collection,
            knowledge_collection=knowledge_collection,
            vault_root=vault_root,
        )


def _update_conversation_privacy_tag_unlocked(
    conversation_id: str,
    tag: str,
    *,
    sessions_root: Path | None = None,
    conversations_dir: Path | None = None,
    conversations_raw: Path | None = None,
    chromadb_path: Path | None = None,
    collection: Any | None = None,
    knowledge_collection: Any | None = None,
    vault_root: Path | None = None,
) -> dict[str, Any]:
    """Move a retained conversation between Standard and Private.

    Stealth is creation-only and cannot enter or leave through this path.
    Privacy-tightening writes searchable/file denormalizations before the
    envelope; privacy-relaxing writes the envelope first and leaves stale
    denormalizations over-protective if a later layer fails. Every layer is
    best-effort and failures are both returned and logged loudly.
    """
    cid = _validate_conversation_id(conversation_id)
    if tag not in {"", "private"}:
        raise ValueError("privacy tag must be standard ('') or 'private'")
    previous_tag = get_conversation_tag(cid, sessions_root=sessions_root)
    if previous_tag == "stealth":
        raise PermissionError("Off Record is creation-only and cannot be retagged")

    sroot = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    cdir = Path(conversations_dir) if conversations_dir else _DEFAULT_CONVERSATIONS_DIR
    craw = Path(conversations_raw) if conversations_raw else _DEFAULT_CONVERSATIONS_RAW
    chroma = Path(chromadb_path) if chromadb_path else _DEFAULT_CHROMADB_PATH
    errors: list[str] = []
    chunk_paths: set[Path] = set()
    runtime_source_ids: set[str] = set()
    _add_runtime_source_id(runtime_source_ids, cid)
    envelope_updated = False
    chroma_updated = 0

    def update_envelope() -> None:
        nonlocal envelope_updated
        try:
            from .conversation_memory import set_conversation_tag
            envelope_path = set_conversation_tag(cid, tag, sessions_root=sroot)
            envelope_updated = envelope_path is not None
            if envelope_path is None:
                _record_error(errors, "privacy envelope", "envelope missing or unwritable")
        except Exception as exc:
            _record_error(errors, "privacy envelope", exc)

    # When relaxing privacy, make the source of truth Standard first. Until
    # caches catch up they remain Private and therefore over-protective.
    if tag == "":
        update_envelope()
        if not envelope_updated:
            return {
                "conversation_id": cid,
                "previous_tag": previous_tag,
                "tag": tag,
                "envelope_updated": False,
                "chromadb_records": 0,
                "chunk_files": [],
                "runtime_derivative_files": [],
                "runtime_knowledge_records": 0,
                "vault_index_entries": 0,
                "manifest_entries": 0,
                "indexing_failure_entries": 0,
                "submission_records": 0,
                "trace_manifests": {},
                "visual_emission_entries": 0,
                "entity_index_retired": False,
                "errors": errors,
            }

    # Search/retrieval cache first when tightening privacy.
    collections = _open_conversations_collections(
        chromadb_path=chromadb_path, collection=collection, errors=errors,
    )
    for physical_name, col in collections:
        rows = _conversation_collection_rows(
            col, cid, errors=errors,
            label=f"privacy metadata query {physical_name}",
        )
        for chunk_id, meta in rows.items():
            cp = meta.get("chunk_path") or meta.get("obsidian_path")
            if isinstance(cp, str) and cp:
                try:
                    chunk_paths.add(_owned_chunk_path(
                        cp,
                        default_root=cdir,
                        conversation_id=cid,
                    ))
                except Exception as exc:
                    _record_error(
                        errors,
                        f"privacy chunk path {physical_name} {chunk_id}", exc,
                    )
            runtime_session_id = meta.get("session_id")
            if isinstance(runtime_session_id, str) and runtime_session_id:
                _add_runtime_source_id(runtime_source_ids, runtime_session_id)
            replacement = dict(meta)
            replacement["tag"] = tag
            replacement["tag_private"] = tag == "private"
            try:
                col.update(ids=[chunk_id], metadatas=[replacement])
                chroma_updated += 1
            except Exception as exc:
                _record_error(
                    errors, f"privacy metadata {physical_name} {chunk_id}", exc,
                )

    manifest_path = Path(_rp.DATA_DIR_STR) / "conversation-manifest.jsonl"

    def update_manifest(record: dict[str, Any]) -> dict[str, Any]:
        if not _record_matches(record, cid):
            return record
        cp = record.get("chunk_path")
        if isinstance(cp, str) and cp:
            try:
                chunk_paths.add(_owned_chunk_path(
                    cp,
                    default_root=cdir,
                    conversation_id=cid,
                    manifest_record=record,
                ))
            except Exception as exc:
                _record_error(errors, "privacy manifest chunk path", exc)
        replacement = dict(record)
        replacement["tag"] = tag
        return replacement

    manifest_updated = _rewrite_jsonl(
        manifest_path,
        errors=errors,
        label="privacy manifest",
        mutate=update_manifest,
    )
    failure_updated = _rewrite_jsonl(
        Path(_rp.DATA_DIR_STR) / "conversation-indexing-failures.jsonl",
        errors=errors,
        label="privacy indexing failures",
        mutate=lambda record: (
            {**record, "tag": tag} if _record_matches(record, cid) else record
        ),
    )
    submissions_updated = _update_submission_tags(craw, cid, tag, errors)
    trace_manifests: dict[str, Any] = {}
    try:
        from orchestrator import pipeline_trace as _pipeline_trace
        # This function already runs inside the per-Dialogue lifecycle lock.
        # Use the unlocked trace helper so privacy mutation and trace creation,
        # deletion, or another retag remain one serialized transaction without
        # attempting to re-enter the cross-process file lock.
        trace_manifests = (
            _pipeline_trace._retag_conversation_trace_manifests_unlocked(
                cid, tag,
            )
        )
        for error in trace_manifests.get("errors") or []:
            _record_error(errors, "privacy trace manifest", error)
        emission_updated = _rewrite_jsonl(
            Path(_pipeline_trace.emission_log_path()),
            errors=errors,
            label="privacy visual emission log",
            mutate=lambda record: (
                {**record, "tag": tag}
                if _record_matches(record, cid) else record
            ),
        )
    except Exception as exc:
        emission_updated = 0
        _record_error(errors, "privacy visual emission log", exc)

    raw_headers_updated = _update_raw_log_privacy_headers(
        craw, cid, tag == "private", errors,
    )

    daily_notes: dict[str, Any] = {}
    if tag == "private":
        try:
            from orchestrator.tools.daily_note import reconcile_conversation_summaries
            daily_notes = reconcile_conversation_summaries(
                cid,
                action="hide_private",
                daily_notes_dir=(
                    Path(vault_root) / "Daily Notes"
                    if vault_root is not None else None
                ),
            )
            for error in daily_notes.get("errors") or []:
                _record_error(errors, "daily-note privacy", error)
        except Exception as exc:
            _record_error(errors, "daily-note privacy", exc)
    chunk_paths.update(_scan_recovered_chunks(cdir, cid))
    chunk_paths.update(_scan_owned_chunks(cdir, cid))

    chunks_updated: list[str] = []
    for path in sorted(chunk_paths, key=str):
        try:
            if _set_private_frontmatter_tag(path, tag == "private"):
                chunks_updated.append(str(path))
        except Exception as exc:
            _record_error(errors, f"privacy chunk {path}", exc)

    (
        runtime_files_updated,
        runtime_records_updated,
        vault_index_entries_removed,
    ) = (
        _update_runtime_derivative_privacy(
            runtime_source_ids,
            tag == "private",
            chromadb_path=chroma,
            errors=errors,
            vault_root=vault_root,
            collection=knowledge_collection,
        )
    )

    ped_derivatives: dict[str, Any] = {}
    ped_indexes: dict[str, Any] = {}
    resolved_vault_root = (
        Path(vault_root) if vault_root is not None else Path(_rp.VAULT_STR)
    )
    try:
        from orchestrator import oversight_actions
        ped_derivatives = (
            oversight_actions.set_conversation_ped_derivatives_private(
                cid,
                tag == "private",
                discover_root=resolved_vault_root,
            )
        )
        for error in ped_derivatives.get("errors") or []:
            _record_error(errors, "PED derivative privacy", error)
        ped_indexes = _refresh_ped_derivative_indexes(
            ped_derivatives,
            chromadb_path=chroma,
            vault_root=resolved_vault_root,
            errors=errors,
            collection=knowledge_collection,
            remove_vault_first=tag == "private",
        )
    except Exception as exc:
        _record_error(errors, "PED derivative privacy", exc)

    # When tightening privacy, the envelope is last: readers never see a
    # Private source-of-truth until every denormalized update has been
    # attempted. Failures remain loud but never become an approval gate: the
    # authoritative privacy choice is still committed, and an idempotent
    # retry can repair any reported stale copy.
    if tag == "private":
        update_envelope()

    # This obsolete cache has no reader and no conversation provenance. Retire
    # it after the authoritative mutation decision so a cleanup failure remains
    # fail-open (loudly reported) rather than becoming a new privacy gate.
    entity_index_retired = _retire_legacy_entity_index(errors)

    return {
        "conversation_id": cid,
        "previous_tag": previous_tag,
        "tag": tag,
        "envelope_updated": envelope_updated,
        "chromadb_records": chroma_updated,
        "chunk_files": chunks_updated,
        "runtime_derivative_files": runtime_files_updated,
        "runtime_knowledge_records": runtime_records_updated,
        "vault_index_entries": vault_index_entries_removed,
        "entity_index_retired": entity_index_retired,
        "manifest_entries": manifest_updated,
        "indexing_failure_entries": failure_updated,
        "submission_records": submissions_updated,
        "trace_manifests": trace_manifests,
        "visual_emission_entries": emission_updated,
        "raw_header_logs": raw_headers_updated,
        "daily_notes": daily_notes,
        "ped_derivatives": ped_derivatives,
        "ped_indexes": ped_indexes,
        "errors": errors,
    }


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
    conversation_id = _validate_conversation_id(conversation_id)
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
        _record_error(errors, "set_conversation_closed", "envelope missing or unwritable")
    return {
        "conversation_id": conversation_id,
        "tag": tag,
        "action": "close",
        "closed":          closed_path is not None,
        "finalize":        finalize,
        "errors":          errors,
    }


def delete_conversation_forever(
    conversation_id: str,
    *,
    sessions_root: Path | None = None,
    conversations_dir: Path | None = None,
    conversations_raw: Path | None = None,
    chromadb_path: Path | None = None,
    vault_sessions: Path | None = None,
) -> dict[str, Any]:
    """Delete all Ora-managed copies of a Stealth conversation.

    Explicit flat vault exports and their sidecars are deliberately retained.
    The operation is idempotent and best-effort: one failed layer never blocks
    the remaining layers, and every failure is both logged and returned.  A
    retained Standard or Private Dialogue must be closed, never purged.
    """
    cid = _validate_conversation_id(conversation_id)
    sroot = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    with _rp.conversation_lifecycle_lock(cid):
        envelope = read_conversation_history_envelope(
            cid, sessions_root=sroot,
        )
        if envelope is None:
            # Legacy session-directory symlinks are deliberately unlinked by
            # the purge without following or deleting their targets.  Read the
            # pointed envelope only to prove this exact Dialogue is Stealth.
            for container in (sroot, sroot / "archived"):
                candidate = _safe_child(container, cid) / "conversation.json"
                if not candidate.parent.is_symlink():
                    continue
                try:
                    pointed = json.loads(candidate.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if (isinstance(pointed, dict)
                        and isinstance(pointed.get("messages"), list)
                        and _same_conversation(pointed.get("conversation_id"), cid)):
                    envelope = pointed
                    break
        if envelope is None:
            # Missing state is an idempotent retry.  Existing unreadable state
            # is not: without its authoritative tag, Stealth cannot be proven.
            live_path = _safe_child(sroot, cid) / "conversation.json"
            retained_path = _safe_child(sroot / "archived", cid) / "conversation.json"
            if live_path.exists() or live_path.is_symlink() or (
                retained_path.exists() or retained_path.is_symlink()
            ):
                raise PermissionError(
                    "Delete Forever requires a readable Off Record Dialogue"
                )
            original_tag = ""
        else:
            original_tag = envelope.get("tag", "")
            if original_tag != "stealth":
                raise PermissionError(
                    "Delete Forever is available only for Off Record Dialogues; "
                    "use Close for Standard or Private Dialogues"
                )
        result = _purge_stealth_unlocked(
            cid,
            sessions_root=sroot,
            conversations_dir=conversations_dir,
            conversations_raw=conversations_raw,
            chromadb_path=chromadb_path,
            vault_sessions=vault_sessions,
        )
    result["tag"] = original_tag
    result["action"] = "delete_forever"
    result["retained"] = {
        "explicit_vault_exports": True,
    }
    return result


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
        row_errors: list[str] = []
        collections = _open_conversations_collections(
            chromadb_path=chroma, collection=None, errors=row_errors,
        )
        out["errors"].extend(row_errors)
        for physical_name, col in collections:
            row_errors = []
            rows = _conversation_collection_rows(
                col, conversation_id, errors=row_errors,
                label=f"finalize metadata query {physical_name}",
            )
            out["errors"].extend(row_errors)
            ids = list(rows)
            metas = [rows[row_id] for row_id in ids]
            if not ids:
                continue

            final_turn = 0
            for meta in metas:
                ti = meta.get("turn_index")
                if isinstance(ti, int) and ti > final_turn:
                    final_turn = ti
            out["final_turn"] = max(out["final_turn"], final_turn)

            # Each rollback corpus is finalized against the rows it actually
            # contains, so a rollback cannot expose an obsolete last-turn bit.
            for row_id, meta in zip(ids, metas):
                new_meta = dict(meta)
                new_meta["total_turns"] = final_turn
                new_meta["is_last_turn"] = bool(
                    meta.get("turn_index") == final_turn
                )
                try:
                    col.update(ids=[row_id], metadatas=[new_meta])
                    out["chunks_updated"] += 1
                except Exception as exc:
                    out["errors"].append(
                        f"update {physical_name} {row_id}: {exc}"
                    )
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
    """Cross-process-serialized wrapper for all managed lifecycle mutation."""
    cid = _validate_conversation_id(conversation_id)
    # Ordering is deliberate: per-conversation lock first, then the global
    # Daily Notes root lock acquired inside reconciliation.
    with _rp.conversation_lifecycle_lock(cid):
        return _purge_stealth_unlocked(
            cid,
            sessions_root=sessions_root,
            conversations_dir=conversations_dir,
            conversations_raw=conversations_raw,
            chromadb_path=chromadb_path,
            vault_sessions=vault_sessions,
        )


def _purge_stealth_unlocked(
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
    conversation_id = _validate_conversation_id(conversation_id)
    sroot = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    cdir = Path(conversations_dir) if conversations_dir else _DEFAULT_CONVERSATIONS_DIR
    craw = Path(conversations_raw) if conversations_raw else _DEFAULT_CONVERSATIONS_RAW
    chroma = Path(chromadb_path) if chromadb_path else _DEFAULT_CHROMADB_PATH
    vroot = Path(vault_sessions) if vault_sessions else _DEFAULT_VAULT_SESSIONS

    parent_envelope = load_conversation_json(
        conversation_id, sessions_root=sroot,
    )
    parent_messages = (
        parent_envelope.get("messages")
        if isinstance(parent_envelope, dict)
        and isinstance(parent_envelope.get("messages"), list)
        else None
    )

    errors: list[str] = []
    deleted: dict[str, Any] = {
        "session_dir": False,
        "session_symlink_removed": False,
        "session_symlink_target_residue": [],
        "chromadb_records": 0,
        "chunk_files": [],
        "raw_log": False,
        "vault_dir": False,
        "archived_session_dir": False,
        "recovered_chunk_files": [],
        "raw_header_logs": [],
        "submission_records": 0,
        "rotated_tool_event_entries": 0,
        "risk_sticky": False,
        "daily_note_summaries": 0,
    }

    # Existing Path-2 imports once used their source path as identity. Resolve
    # the confirmed safe historical id and migrate exact managed ownership at
    # this lifecycle boundary; this is synchronous runtime compatibility, not
    # deferred maintenance.
    try:
        from orchestrator.historical.path2_orchestrator import (
            migrate_path2_identity_for_safe_id,
        )
        historical_migration = migrate_path2_identity_for_safe_id(
            conversation_id,
            conversations_dir=cdir,
            chromadb_path=chroma,
            manifest_path=(
                Path(_rp.DATA_DIR_STR) / "conversation-manifest.jsonl"
            ),
        )
        deleted["historical_identity_migration"] = historical_migration
        for error in historical_migration.get("errors") or []:
            _record_error(errors, "historical identity migration", error)
    except Exception as exc:
        _record_error(errors, "historical identity migration", exc)

    # --- Layer 0: generated Daily Note summaries ---------------------------
    # This runs before chunk and envelope deletion so legacy pre-provenance
    # lines can be reconstructed exactly. Explicit user-authored Daily Note
    # content is never selected; edited generated lines fail loudly.
    try:
        from orchestrator.tools.daily_note import reconcile_conversation_summaries
        daily_result = reconcile_conversation_summaries(
            conversation_id,
            action="delete",
            daily_notes_dir=vroot.parent / "Daily Notes",
        )
        deleted["daily_note_summaries"] = int(
            daily_result.get("summaries_removed") or 0
        )
        deleted["daily_note_files"] = list(
            daily_result.get("files_updated") or []
        )
        for error in daily_result.get("errors") or []:
            _record_error(errors, "daily-note purge", error)
    except Exception as exc:
        _record_error(errors, "daily-note purge", exc)

    # --- Layer 0b: conversation-owned project PED derivatives -------------
    # The project file itself is user-owned and remains. Remove only hidden
    # marker-bounded blocks, delete the reversible sidecar entries/counters,
    # then synchronously replace every affected retrieval cache.
    try:
        from orchestrator import oversight_actions
        ped_result = oversight_actions.purge_conversation_ped_derivatives(
            conversation_id,
            discover_root=vroot.parent,
        )
        deleted["ped_derivatives"] = ped_result
        for error in ped_result.get("errors") or []:
            _record_error(errors, "PED derivative purge", error)
        deleted["ped_indexes"] = _refresh_ped_derivative_indexes(
            ped_result,
            chromadb_path=chroma,
            vault_root=vroot.parent,
            errors=errors,
            remove_vault_first=True,
        )
    except Exception as exc:
        deleted["ped_derivatives"] = {}
        deleted["ped_indexes"] = {}
        _record_error(errors, "PED derivative purge", exc)

    # --- Layer 1: ChromaDB records (read paths first, then delete) -----------
    chunk_paths: list[str] = []
    raw_paths: set[str] = set()
    runtime_source_ids: set[str] = set()
    _add_runtime_source_id(runtime_source_ids, conversation_id)
    try:
        collections = _open_conversations_collections(
            chromadb_path=chroma,
            collection=None,
            errors=errors,
        )
        for physical_name, col in collections:
            rows = _conversation_collection_rows(
                col, conversation_id, errors=errors,
                label=f"chromadb query {physical_name}",
            )
            ids = list(rows)
            metas = [rows[row_id] for row_id in ids]
            for _cid, meta in zip(ids, metas):
                if isinstance(meta, dict):
                    cp = meta.get("chunk_path")
                    if isinstance(cp, str) and cp:
                        chunk_paths.append(cp)
                    rp = meta.get("raw_path")
                    if isinstance(rp, str) and rp:
                        raw_paths.add(rp)
                    runtime_session_id = meta.get("session_id")
                    if isinstance(runtime_session_id, str) and runtime_session_id:
                        _add_runtime_source_id(runtime_source_ids, runtime_session_id)
            if ids:
                try:
                    col.delete(ids=ids)
                    deleted["chromadb_records"] += len(ids)
                except Exception as exc:
                    _record_error(
                        errors, f"chromadb delete {physical_name}", exc,
                    )
    except Exception as e:
        _record_error(errors, "chromadb", e)

    # --- Layer 2: Chunk files ------------------------------------------------
    for cp in chunk_paths:
        try:
            p = _owned_chunk_path(
                cp,
                default_root=cdir,
                conversation_id=conversation_id,
            )
            if _unlink_without_following(p):
                deleted["chunk_files"].append(str(p))
        except Exception as e:
            _record_error(errors, f"chunk_file {cp}", e)

    # Recovered interrupted-submission chunks never reached ChromaDB and may
    # never have reached the manifest. Their YAML frontmatter carries both
    # ``conversation_id`` and ``panel_id``, so scan the configured processed
    # conversation root without following symlinks and remove exact matches.
    already_deleted_chunk = {str(Path(p)) for p in deleted["chunk_files"]}
    try:
        recovered_paths = (
            _scan_recovered_chunks(cdir, conversation_id)
            + _scan_owned_chunks(cdir, conversation_id)
        )
        for path in recovered_paths:
            if str(path) in already_deleted_chunk:
                continue
            try:
                if _unlink_without_following(path):
                    deleted["chunk_files"].append(str(path))
                    deleted["recovered_chunk_files"].append(str(path))
                    already_deleted_chunk.add(str(path))
            except Exception as exc:
                _record_error(errors, f"recovered chunk {path}", exc)
    except Exception as exc:
        _record_error(errors, f"recovered chunk scan {cdir}", exc)

    # --- Layer 3: Raw log fragment(s) ---------------------------------------
    # A conversation typically has exactly one raw log; the set lets us
    # tolerate the rare case where chunks point at different raw_paths
    # (shouldn't happen in normal flow, but defensive).
    deleted_raw_paths: set[str] = set()
    for rp in raw_paths:
        try:
            p = _artifact_path(rp, within=craw)
            if _unlink_without_following(p):
                deleted["raw_log"] = True
                deleted_raw_paths.add(str(p))
        except Exception as e:
            _record_error(errors, f"raw_log {rp}", e)

    # Chroma/manifest pointers can be absent after a crash. Raw logs have a
    # stable header, so scan the configured raw root as a fallback. Only the
    # exact scalar ``panel_id`` match is eligible; symlinks are never read.
    try:
        if craw.exists() and not craw.is_symlink() and craw.is_dir():
            for path in sorted(craw.glob("*.md")):
                if path.is_symlink() or not path.is_file():
                    continue
                try:
                    with open(path, encoding="utf-8") as fh:
                        head = fh.read(8192)
                    session_match = re.search(
                        r"(?m)^# Session\s+([^\s]+)\s*$", head,
                    )
                    match = re.search(r"(?m)^panel_id\s*:\s*([^#\n]*?)\s*$", head)
                    value = match.group(1).strip() if match else ""
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                        value = value[1:-1]
                    if not _same_conversation(value, conversation_id):
                        continue
                    # Session ids are derivative provenance only after this raw
                    # log has been proven to belong to the target Dialogue.
                    if session_match:
                        _add_runtime_source_id(
                            runtime_source_ids, session_match.group(1),
                        )
                    if _unlink_without_following(path):
                        deleted["raw_log"] = True
                        deleted["raw_header_logs"].append(str(path))
                        deleted_raw_paths.add(str(path))
                except Exception as exc:
                    _record_error(errors, f"raw header {path}", exc)
    except Exception as exc:
        _record_error(errors, f"raw header scan {craw}", exc)

    # --- Layer 4: Session directory -----------------------------------------
    for storage_id in _conversation_id_variants(conversation_id):
        session_dir = _safe_child(sroot, storage_id)
        try:
            if session_dir.is_symlink():
                target = session_dir.resolve(strict=False)
                session_dir.unlink()
                deleted["session_symlink_removed"] = True
                if target.exists() or target.is_symlink():
                    deleted["session_symlink_target_residue"].append(str(target))
                _record_error(
                    errors,
                    f"session_dir {session_dir}",
                    f"removed symlink entry without traversing external target "
                    f"{target}; target residue requires explicit owner action",
                )
                continue
            if _remove_tree_without_following(session_dir):
                deleted["session_dir"] = True
        except Exception as e:
            _record_error(errors, f"session_dir {session_dir}", e)

    # Retention may have moved a closed session into sessions/archived/<id>.
    archive_root = _safe_child(sroot, "archived")
    try:
        if (archive_root.is_symlink()
                or (archive_root.exists() and not archive_root.is_dir())):
            raise ValueError(
                f"refusing symlinked/non-directory archive root {archive_root}"
            )
        for storage_id in _conversation_id_variants(conversation_id):
            archived_session = _safe_child(archive_root, storage_id)
            if _remove_tree_without_following(archived_session):
                deleted["archived_session_dir"] = True
    except Exception as e:
        _record_error(errors, f"archived_session_dir {archive_root}", e)

    # --- Layer 5: Vault session directory -----------------------------------
    # A legacy per-ID directory was Ora-managed and predates the current flat
    # exporter, so it remains eligible. Normal flat exports and their sidecars
    # are user-owned and are never scanned or deleted here.
    for storage_id in _conversation_id_variants(conversation_id):
        vault_dir = _safe_child(vroot, storage_id)
        try:
            if _remove_tree_without_following(vault_dir):
                deleted["vault_dir"] = True
        except Exception as e:
            _record_error(errors, f"vault_dir {vault_dir}", e)

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
        trace_paths: list[str] = []
        for storage_id in _conversation_id_variants(conversation_id):
            # _purge_stealth_unlocked is already inside the same lifecycle
            # lock. Avoid trying to re-enter the cross-process lock here.
            pt_result = _pt._purge_conversation_traces_unlocked(storage_id)
            deleted["pipeline_traces"] = bool(
                deleted["pipeline_traces"] or pt_result["deleted"]
            )
            trace_paths.append(pt_result["path"])
            if pt_result.get("error"):
                _record_error(
                    errors, f"pipeline_traces {pt_result['path']}",
                    pt_result["error"],
                )
        deleted["pipeline_traces_path"] = trace_paths[0] if trace_paths else ""
        deleted["pipeline_traces_paths"] = trace_paths
    except Exception as e:
        _record_error(errors, "pipeline_traces", e)

    # --- Layer 6b: Framework scratch backstop -----------------------------
    # Framework execution deletes Stealth scratch on each controlled terminal
    # path. Conversation closeout is the orphan backstop for abrupt process
    # loss between scratch creation and terminal handling. Manifest ownership
    # is exact, and normal-run resumable scratch is never selected.
    _purge_framework_scratch_backstop(conversation_id, deleted, errors)

    # --- Layer 6c: corpus-wide visual-emission observability ----------------
    # Unlike per-turn traces, this JSONL is global and therefore is not removed
    # by deleting the trace directory. The writer shares this sidecar lock.
    deleted["visual_emission_entries"] = 0
    try:
        from orchestrator import pipeline_trace as _pipeline_trace
        deleted["visual_emission_entries"] = _rewrite_jsonl(
            Path(_pipeline_trace.emission_log_path()),
            errors=errors,
            label="visual emission log",
            mutate=lambda record: (
                None if _record_matches(record, conversation_id) else record
            ),
        )
    except Exception as exc:
        _record_error(errors, "visual emission log", exc)

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
        # Read at call time from runtime_paths so the purge follows an
        # ORA_HOME relocation (same pattern as Layers 6a/9 below).
        manifest_path = Path(os.path.join(
            _rp.DATA_DIR_STR, "conversation-manifest.jsonl"
        ))
        already_deleted_chunk = {str(p) for p in deleted["chunk_files"]}

        def drop_manifest_record(rec: dict[str, Any]) -> dict[str, Any] | None:
            if not _record_matches(rec, conversation_id):
                return rec
            artifact_failed = False
            chunk_id = rec.get("chunk_id")
            if isinstance(chunk_id, str):
                match = re.match(r"^session-(.+)-pair-\d+$", chunk_id)
                if match:
                    _add_runtime_source_id(runtime_source_ids, match.group(1))
            cp = rec.get("chunk_path")
            rp = rec.get("raw_path")
            if isinstance(cp, str) and cp and cp not in already_deleted_chunk:
                try:
                    p = _owned_chunk_path(
                        cp,
                        default_root=cdir,
                        conversation_id=conversation_id,
                        manifest_record=rec,
                    )
                    if _unlink_without_following(p):
                        deleted["chunk_files"].append(str(p))
                        already_deleted_chunk.add(str(p))
                except Exception as e:
                    _record_error(errors, f"manifest chunk_file {cp}", e)
                    artifact_failed = True
            if isinstance(rp, str) and rp:
                try:
                    # Raw logs always live under the configured raw root.
                    # Retain and report a manifest record that claims any
                    # other path instead of turning corrupted metadata into
                    # an arbitrary-file deletion primitive.
                    p = _artifact_path(rp, within=craw)
                    if str(p) in deleted_raw_paths:
                        return rec if artifact_failed else None
                    if _unlink_without_following(p):
                        deleted["raw_log"] = True
                        deleted_raw_paths.add(str(p))
                except Exception as e:
                    _record_error(errors, f"manifest raw_log {rp}", e)
                    artifact_failed = True
            # Keep the pointer if an artifact could not be removed so a
            # later idempotent retry can still locate the residue.
            return rec if artifact_failed else None

        deleted["manifest_orphans_removed"] = _rewrite_jsonl(
            manifest_path,
            errors=errors,
            label="manifest",
            mutate=drop_manifest_record,
        )
    except Exception as e:
        _record_error(errors, "manifest", e)

    # --- Layer 8a: pre-pipeline submission records -------------------------
    # pending/ and processed/ are independent durable copies created before
    # the pipeline and after save. Both carry conversation_id/panel_id.
    try:
        deleted["submission_records"] = _delete_submission_records(
            craw, conversation_id, errors,
        )
    except Exception as e:
        _record_error(errors, "submission records", e)

    # --- Layer 9: Oversight logs (events / actions / router / human-queue) --
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
    # guarantees no structured oversight residue even when a future code path
    # forgets to set the thread-local, by stripping any record matching the purged
    # conversation_id. Records are stamped with ``conversation_id`` by
    # ``oversight_events.emit`` and the two write helpers in
    # ``oversight_actions`` when the per-thread context is set.
    # The scrub targets must be the files the writers actually write:
    # both flow from runtime_paths (ORA_HOME-relocatable), read at call
    # time so a purge can never silently miss a relocated sink.
    from . import runtime_paths as _rp_purge
    # Precedence (same rule as every oversight writer): an explicit
    # DATA_DIR_STR patch wins; otherwise under ORA_OVERSIGHT_SANDBOX (test
    # runs) the writers landed in the quarantine dir with a FLAT layout, so
    # the scrub must target the sandbox root itself — never rewrite the
    # live logs from a test process.
    _candidate = os.path.join(_rp_purge.DATA_DIR_STR, "oversight")
    if _candidate != _LIVE_OVERSIGHT_DIR:
        OVERSIGHT_DIR = Path(_candidate)
    else:
        OVERSIGHT_DIR = Path(_rp_purge.oversight_sandbox_dir() or _candidate)
    deleted["oversight_log_entries"] = {
        "events.jsonl": 0,
        "actions.jsonl": 0,
        "router.jsonl": 0,
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
        from . import tool_events as _te_mod
        _te_path = Path(_te_mod.global_sink_path())
        # Retention holds this source lock from rename through completed gzip
        # creation. Keep it across both the live rewrite and archive scan so a
        # rotation can never make the source disappear before its destination
        # pathname exists and thereby escape both halves of this purge.
        with _rp.locked_file(_te_path):
            deleted["tool_event_entries"] = _rewrite_jsonl_unlocked(
                _te_path,
                errors=errors,
                label="tool_events purge",
                mutate=lambda record: (
                    None if _record_matches(record, conversation_id) else record
                ),
            )

            # Rotated tool-event archives contain the same JSONL records in
            # gzip form. Retention takes the source lock and then each archive
            # lock in this same order for creation; expiry takes the archive
            # lock before unlinking.
            archive_dir = Path(_rp.DATA_DIR_STR) / "archive"
            if (archive_dir.exists() and not archive_dir.is_symlink()
                    and archive_dir.is_dir()):
                for archive in sorted(archive_dir.glob("tool-events*.gz")):
                    deleted["rotated_tool_event_entries"] += _rewrite_gzip_jsonl(
                        archive,
                        errors=errors,
                        label=f"rotated tool events {archive}",
                        drop=lambda record: _record_matches(
                            record, conversation_id,
                        ),
                    )
    except Exception as e:
        _record_error(errors, "tool_events purge", e)

    # --- Layer 6b: task-approval tokens (Execution Review Phase 2) ---------
    # A stealth conversation's tier=irreversible hold mints a task_execute
    # token in data/execution-approvals.json carrying the conversation_id.
    # Scrub any token bound to the purged conversation so the stealth
    # zero-residue promise covers the approval store too (condition 9).
    deleted["task_tokens"] = 0
    try:
        from . import tool_events as _te_tok

        def drop_conversation_tokens() -> int:
            data = _te_tok._load_approvals_locked()
            tokens = data.get("tokens", [])
            kept = [
                token for token in tokens
                if not _record_matches(token, conversation_id)
            ]
            dropped = len(tokens) - len(kept)
            if dropped:
                data["tokens"] = kept
                # Re-sign through the approval authority's existing atomic
                # writer; a raw rewrite would invalidate the v2 store MAC.
                _te_tok._save_approvals(data)
            return dropped

        deleted["task_tokens"] = _te_tok._with_approvals_lock(
            drop_conversation_tokens,
        )
    except Exception as e:
        _record_error(errors, "task_tokens purge", e)

    try:
        for log_name in (
            "events.jsonl", "actions.jsonl", "router.jsonl",
            "human-queue.jsonl",
        ):
            log_path = OVERSIGHT_DIR / log_name

            def mutate_oversight(record: dict[str, Any], *, _name=log_name):
                if _record_matches(record, conversation_id):
                    return None
                # A Paused-queue entry can belong to another source
                # conversation while linking to this Dialogue as its separate
                # resolution discussion. Preserve the queue item but sever the
                # now-invalid link.
                if (_name == "human-queue.jsonl"
                        and _same_conversation(
                            record.get("discussion_conversation_id"),
                            conversation_id,
                        )):
                    replacement = dict(record)
                    replacement["discussion_conversation_id"] = None
                    return replacement
                return record

            deleted["oversight_log_entries"][log_name] = _rewrite_jsonl(
                log_path,
                errors=errors,
                label=f"oversight_log {log_name}",
                mutate=mutate_oversight,
            )
    except Exception as e:
        _record_error(errors, "oversight_logs", e)

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
        log_path = Path(os.path.join(
            _rp.DATA_DIR_STR, "conversation-indexing-failures.jsonl"
        ))
        deleted["indexing_failures_log_entries"] = _rewrite_jsonl(
            log_path,
            errors=errors,
            label="indexing_failures_log",
            mutate=lambda record: (
                None if _record_matches(record, conversation_id) else record
            ),
        )
    except Exception as e:
        _record_error(errors, "indexing_failures_log", e)

    # --- Layer 10: Execution-review durable store (Phase 7) ------------------
    # The non-git operational store data/execution-records/ holds the tiered-
    # persistence ledger + per-conversation durable notes. Write-time stealth
    # gating (execution_persistence.persist_packet) is primary; this is the
    # post-hoc backstop for a conversation marked stealth AFTER a durable record
    # was written for a normal turn. execution_persistence.purge_conversation
    # reads its own roots at call time (the Layers 6a/8/9 idiom): it rmtree's the
    # per-conversation note subdir (the store is git-ignored → no history residue)
    # and scrubs the ledger jsonl by conversation_id (Layer-9 style).
    deleted["execution_records"] = {}
    try:
        try:
            import execution_persistence as _epersist
        except ImportError:  # pragma: no cover
            from orchestrator import execution_persistence as _epersist
        _er_res = _epersist.purge_conversation(conversation_id)
        deleted["execution_records"] = _er_res
        for _e in (_er_res.get("errors") or []):
            _record_error(errors, "execution_records", _e)
    except Exception as e:
        _record_error(errors, "execution_records", e)

    # --- Layer 10b: Trace-debug learning library -----------------------------
    deleted["trace_debug_learning"] = {}
    try:
        try:
            import trace_debug as _tdbg
        except ImportError:  # pragma: no cover
            from orchestrator import trace_debug as _tdbg
        _td_res = _tdbg.purge_conversation_unlocked(conversation_id)
        deleted["trace_debug_learning"] = _td_res
        for _e in (_td_res.get("errors") or []):
            _record_error(errors, "trace_debug_learning", _e)
    except Exception as e:
        _record_error(errors, "trace_debug_learning", e)

    # --- Layer 11: sticky risk-floor state ---------------------------------
    # This small JSON map is another conversation-keyed persistence surface.
    # Rewrite it directly (using risk_gate's authoritative sandbox-aware
    # path) so failures are observable rather than swallowed by set_sticky.
    try:
        from . import risk_gate as _risk_gate
        sticky_path = Path(_risk_gate._sticky_path())
        if sticky_path.exists():
            with _rp.locked_file(sticky_path):
                if sticky_path.is_symlink() or not sticky_path.is_file():
                    raise ValueError(f"refusing non-regular sticky store {sticky_path}")
                sticky = json.loads(sticky_path.read_text(encoding="utf-8"))
                if not isinstance(sticky, dict):
                    raise ValueError("sticky store is not an object")
                matching_keys = [
                    key for key in sticky
                    if _same_conversation(key, conversation_id)
                ]
                if matching_keys:
                    for key in matching_keys:
                        sticky.pop(key, None)
                    _atomic_write_text(
                        sticky_path,
                        json.dumps(sticky, ensure_ascii=False, indent=2) + "\n",
                    )
                    deleted["risk_sticky"] = True
    except Exception as e:
        _record_error(errors, "risk sticky", e)

    # --- Layer 12: runtime extraction derivatives --------------------------
    # These are automatically generated working/promoted notes and knowledge
    # index rows, not explicit flat Vault/Sessions exports. The lifecycle lock
    # in server.py waits for the runtime worker before this layer runs, so no
    # derivative can reappear after the scan completes.
    try:
        (
            runtime_files,
            runtime_records,
            runtime_logs,
            vault_index_entries,
        ) = _delete_runtime_derivatives(
                runtime_source_ids,
                chromadb_path=chroma,
                errors=errors,
                vault_root=vroot.parent,
            )
        deleted["runtime_derivative_files"] = runtime_files
        deleted["runtime_knowledge_records"] = runtime_records
        deleted["runtime_session_logs"] = runtime_logs
        deleted["vault_index_entries"] = vault_index_entries
    except Exception as exc:
        _record_error(errors, "runtime derivatives", exc)

    deleted["entity_index_retired"] = _retire_legacy_entity_index(errors)

    # Retire the old dispatcher sink corpus-wide. Its historical records did
    # not carry a conversation identity, so selective deletion is impossible;
    # the sink itself is no longer written and all files are Ora-managed.
    try:
        from . import dispatcher as _dispatcher
        dispatch_logs = _dispatcher.retire_legacy_session_logs()
        deleted["legacy_dispatch_session_logs"] = list(
            dispatch_logs.get("removed") or []
        )
        for error in dispatch_logs.get("errors") or []:
            _record_error(errors, "legacy dispatcher logs", error)
    except Exception as exc:
        deleted["legacy_dispatch_session_logs"] = []
        _record_error(errors, "legacy dispatcher logs", exc)

    # --- Final layer: direct fork detachment -------------------------------
    # The parent envelope has now been purged. Current children contain only
    # local turns; legacy copied-history children are scrubbed only when the
    # deleted parent's complete transcript is an exact prefix.
    try:
        fork_children = detach_direct_fork_children(
            conversation_id,
            parent_messages=parent_messages,
            sessions_root=sroot,
        )
        deleted["fork_children"] = fork_children
        for error in fork_children.get("errors") or []:
            _record_error(errors, "fork child detachment", error)
    except Exception as exc:
        deleted["fork_children"] = {}
        _record_error(errors, "fork child detachment", exc)

    return {
        "conversation_id": conversation_id,
        "tag": "stealth",
        "action": "purge",
        "deleted": deleted,
        "retained": {"explicit_vault_exports": True},
        "errors": errors,
    }


__all__ = [
    "close_conversation",
    "delete_conversation_forever",
    "refresh_conversation_title_metadata",
    "update_conversation_privacy_tag",
    "_finalize_conversation_chunks",
    "_purge_stealth",
]
