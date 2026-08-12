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

import hashlib
import json
import os
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from orchestrator import runtime_paths as _rp
from orchestrator.conversation_chunk import (
    _extract_keywords,
    append_chunk_manifest,
    attach_chunk_ownership,
    build_chroma_metadata,
    build_chunk_filename,
    build_chunk_markdown,
    build_embedding_orientation,
    build_retrieval_document,
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

DEFAULT_CLEANED_PAIR_DIR  = str(_rp.historical_archive_dir())
DEFAULT_CONVERSATIONS_DIR = str(_rp.conversations_dir())
# Live pipeline writes to ~/ora/chromadb/ — Phase 2 must match so
# historical chunks land in the same `conversations` collection that
# RAG queries hit.
DEFAULT_CHROMADB_PATH     = str(_rp.chromadb_dir())

# The tracked BGE-M3 install default has an 8,192-token context, and alternate
# configured embedders may impose their own bound. Keep a conservative common
# cap for long pairs (Bible quotes, book outlines, etc.). 10K chars handles
# dense content (code, non-ASCII, repeated tokens) that can approach ~2
# chars/token. The stored document and chunk Markdown remain complete; only
# the separate query-facing embedding orientation is bounded.
MAX_EMBED_CHARS = 10_000

_OWNERSHIP_ID_RE = re.compile(
    r'<!-- ora-conversation-id: (?P<value>"(?:[^"\\]|\\.)*") -->'
)
_CHUNK_ID_RE = re.compile(
    r'<!-- ora-chunk-id: (?P<value>"(?:[^"\\]|\\.)*") -->'
)
_PAIR_ID_RE = re.compile(r"^session-.+-pair-(\d+)$")
_SAFE_HISTORICAL_ID_RE = re.compile(r"^historical-[0-9a-f]{12}$")


def historical_conversation_id(source_chat: str) -> str:
    """Return the filesystem-safe lifecycle identity for one source chat."""
    source = str(source_chat or "").strip()
    if not source:
        raise ValueError("historical source_chat must be non-empty")
    return f"historical-{derive_session_id(source)}"


def _historical_record(metadata: Any) -> bool:
    if not isinstance(metadata, dict):
        return False
    platform = str(metadata.get("source_platform") or "").casefold()
    model = str(metadata.get("model_id") or "").casefold()
    return platform.startswith("historical") or model.startswith("historical")


def _replacement_chunk_id(value: Any, session_id: str,
                          metadata: dict | None = None) -> str | None:
    pair_num: int | None = None
    if isinstance(metadata, dict):
        candidate = metadata.get("turn_index")
        if isinstance(candidate, int) and not isinstance(candidate, bool) and candidate > 0:
            pair_num = candidate
    if pair_num is None and isinstance(value, str):
        match = _PAIR_ID_RE.match(value)
        if match:
            pair_num = int(match.group(1))
    if pair_num is None:
        return None
    return f"session-{session_id}-pair-{pair_num:03d}"


def _chunk_file_owned_by(path: str | Path, conversation_id: str,
                         chunk_id: str) -> bool:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        return False
    try:
        text = candidate.read_text(encoding="utf-8")
        owner = _OWNERSHIP_ID_RE.search(text)
        chunk = _CHUNK_ID_RE.search(text)
        return bool(
            owner and chunk
            and json.loads(owner.group("value")) == conversation_id
            and json.loads(chunk.group("value")) == chunk_id
        )
    except (OSError, json.JSONDecodeError):
        return False


def migrate_legacy_path2_identity(
    source_chat: str,
    *,
    conversations_dir: str | Path,
    chromadb_path: str | Path,
    manifest_path: str | Path | None = None,
    legacy_conversation_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Idempotently migrate prior Path-2 ownership to the safe identity.

    This compatibility pass runs synchronously when Path 2 runs; it is never a
    scheduled cleanup. It updates every discoverable physical conversation
    collection, exact Ora ownership markers, and the ownership manifest. The
    imported source itself is retained: legacy ``raw_path`` provenance is
    moved to ``source_path`` so lifecycle cannot mistake it for an Ora raw log.
    """
    source = str(source_chat or "").strip()
    safe_id = historical_conversation_id(source)
    session_id = derive_session_id(source)
    legacy_hints = {
        value for value in legacy_conversation_ids
        if isinstance(value, str) and value
    }
    source_aliases = {source, safe_id}
    result: dict[str, Any] = {
        "conversation_id": safe_id,
        "source_path": source,
        "chromadb_records": 0,
        "chunk_files": 0,
        "manifest_entries": 0,
        "errors": [],
    }
    known_chunk_paths: set[Path] = set()
    chunk_id_map: dict[str, str] = {}

    try:
        import chromadb
        from orchestrator import embedding

        client = chromadb.PersistentClient(path=str(chromadb_path))
        try:
            physical_names = embedding.discover_collection_copies(
                client, "conversations",
            )
        except Exception as exc:
            result["errors"].append(
                f"discover historical ChromaDB copies: {exc}"
            )
            physical_names = embedding.resolve_collection_copies("conversations")

        for physical_name in physical_names:
            try:
                collection = embedding.get_collection(client, physical_name)
            except Exception:
                # A configured rollback name need not exist on every machine.
                continue
            try:
                try:
                    rows = collection.get(
                        where={"raw_path": source},
                        include=["metadatas", "documents", "embeddings"],
                    )
                except Exception:
                    rows = collection.get(
                        where={"raw_path": source},
                        include=["metadatas", "documents"],
                    )
                # Already-migrated rows carry source_path instead.
                migrated_rows = collection.get(
                    where={"source_path": source},
                    include=["metadatas", "documents"],
                )
            except Exception as exc:
                result["errors"].append(
                    f"query historical ChromaDB {physical_name}: {exc}"
                )
                continue

            combined: dict[str, tuple[dict, Any, Any]] = {}
            for payload in (rows, migrated_rows):
                ids = list(payload.get("ids") or [])
                metadatas = list(payload.get("metadatas") or [])
                documents = list(payload.get("documents") or [])
                raw_embeddings = payload.get("embeddings")
                embeddings = (
                    list(raw_embeddings) if raw_embeddings is not None else []
                )
                for index, row_id in enumerate(ids):
                    metadata = (
                        metadatas[index]
                        if index < len(metadatas) and isinstance(metadatas[index], dict)
                        else {}
                    )
                    document = documents[index] if index < len(documents) else None
                    vector = embeddings[index] if index < len(embeddings) else None
                    combined[str(row_id)] = (metadata, document, vector)

            for old_id, (metadata, document, vector) in combined.items():
                if not _historical_record(metadata):
                    continue
                owner = metadata.get("conversation_id")
                chunk_path = metadata.get("chunk_path") or metadata.get("obsidian_path")
                if isinstance(chunk_path, str) and chunk_path:
                    known_chunk_paths.add(Path(chunk_path).expanduser().absolute())
                replacement_id = _replacement_chunk_id(old_id, session_id, metadata)
                if replacement_id is None:
                    result["errors"].append(
                        f"historical ChromaDB {physical_name} {old_id}: "
                        "missing positive turn_index; identity retained"
                    )
                    continue
                replacement = dict(metadata)
                replacement["conversation_id"] = safe_id
                replacement["session_id"] = session_id
                replacement["source_path"] = source
                replacement["raw_path"] = ""
                chunk_id_map[old_id] = replacement_id
                try:
                    if replacement_id == old_id:
                        collection.update(ids=[old_id], metadatas=[replacement])
                    else:
                        kwargs: dict[str, Any] = {
                            "ids": [replacement_id],
                            "metadatas": [replacement],
                        }
                        if vector is not None:
                            kwargs["embeddings"] = [vector]
                        elif isinstance(document, str):
                            kwargs["documents"] = [document]
                        else:
                            raise ValueError(
                                "record has neither embedding nor document"
                            )
                        collection.upsert(**kwargs)
                        collection.delete(ids=[old_id])
                    result["chromadb_records"] += 1
                except Exception as exc:
                    result["errors"].append(
                        f"migrate historical ChromaDB {physical_name} "
                        f"{old_id}: {exc}"
                    )
    except Exception as exc:
        result["errors"].append(f"open historical ChromaDB: {exc}")

    root = Path(conversations_dir).expanduser().absolute()
    candidates: set[Path] = set(known_chunk_paths)
    if root.exists() and not root.is_symlink() and root.is_dir():
        candidates.update(path.absolute() for path in root.glob("*.md"))
    elif root.exists():
        result["errors"].append(
            f"historical chunk migration: refusing non-directory {root}"
        )

    try:
        from orchestrator import runtime_paths as rp
    except ImportError:  # pragma: no cover - legacy top-level context
        import runtime_paths as rp  # type: ignore

    root_resolved = root.resolve(strict=False)
    for path in sorted(candidates, key=str):
        try:
            absolute = path.expanduser().absolute()
            if absolute.is_symlink() or not absolute.is_file():
                continue
            if root_resolved not in absolute.resolve(strict=False).parents:
                continue
            text = absolute.read_text(encoding="utf-8")
            owner_match = _OWNERSHIP_ID_RE.search(text)
            chunk_match = _CHUNK_ID_RE.search(text)
            if owner_match is None or chunk_match is None:
                continue
            owner = json.loads(owner_match.group("value"))
            old_chunk_id = json.loads(chunk_match.group("value"))
            eligible = (
                absolute in known_chunk_paths
                or (isinstance(owner, str) and owner in source_aliases)
                or (
                    isinstance(owner, str)
                    and owner not in {"", safe_id}
                    and historical_conversation_id(owner) == safe_id
                )
            )
            if not eligible:
                if isinstance(owner, str) and owner in legacy_hints:
                    result["errors"].append(
                        f"historical chunk {absolute}: legacy alias {owner!r} "
                        "is not tied to this source by ChromaDB; retained"
                    )
                continue
            new_chunk_id = chunk_id_map.get(old_chunk_id)
            if new_chunk_id is None:
                new_chunk_id = _replacement_chunk_id(old_chunk_id, session_id)
            if new_chunk_id is None:
                result["errors"].append(
                    f"historical chunk {absolute}: cannot derive pair identity"
                )
                continue
            replacement = _OWNERSHIP_ID_RE.sub(
                "<!-- ora-conversation-id: "
                + json.dumps(safe_id, ensure_ascii=False)
                + " -->",
                text,
                count=1,
            )
            replacement = _CHUNK_ID_RE.sub(
                "<!-- ora-chunk-id: "
                + json.dumps(new_chunk_id, ensure_ascii=False)
                + " -->",
                replacement,
                count=1,
            )
            if replacement != text:
                rp.atomic_write_text(absolute, replacement)
                result["chunk_files"] += 1
            if isinstance(old_chunk_id, str):
                chunk_id_map[old_chunk_id] = new_chunk_id
            known_chunk_paths.add(absolute)
        except Exception as exc:
            result["errors"].append(
                f"migrate historical chunk {path}: {exc}"
            )

    destination = (
        Path(manifest_path) if manifest_path is not None
        else Path(rp.DATA_DIR_STR) / "conversation-manifest.jsonl"
    )
    if destination.exists():
        try:
            with rp.locked_file(destination):
                if destination.is_symlink() or not destination.is_file():
                    raise ValueError(f"refusing non-regular manifest {destination}")
                output: list[str] = []
                changed = False
                for line_no, line in enumerate(
                    destination.read_text(encoding="utf-8").splitlines(), 1
                ):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exc:
                        result["errors"].append(
                            f"historical manifest {destination}:{line_no}: {exc}"
                        )
                        output.append(line)
                        continue
                    if not isinstance(record, dict):
                        output.append(line)
                        continue
                    owner = record.get("conversation_id")
                    old_chunk_id = record.get("chunk_id")
                    record_path = record.get("chunk_path")
                    try:
                        absolute_record_path = (
                            Path(record_path).expanduser().absolute()
                            if isinstance(record_path, str) and record_path else None
                        )
                    except Exception:
                        absolute_record_path = None
                    eligible = (
                        record.get("managed_by") == "ora"
                        and record.get("artifact_kind") == "conversation_chunk"
                        and (
                            (
                                isinstance(owner, str)
                                and owner in source_aliases
                            )
                            or (
                                isinstance(old_chunk_id, str)
                                and old_chunk_id in chunk_id_map
                            )
                            or absolute_record_path in known_chunk_paths
                        )
                    )
                    if not eligible:
                        if isinstance(owner, str) and owner in legacy_hints:
                            result["errors"].append(
                                f"historical manifest {destination}:{line_no}: "
                                f"legacy alias {owner!r} is ambiguous without "
                                "an exact source-linked chunk; retained"
                            )
                        output.append(line)
                        continue
                    replacement = dict(record)
                    replacement["conversation_id"] = safe_id
                    replacement["source_path"] = source
                    replacement["raw_path"] = ""
                    new_chunk_id = chunk_id_map.get(old_chunk_id)
                    if new_chunk_id is None:
                        new_chunk_id = _replacement_chunk_id(old_chunk_id, session_id)
                    if new_chunk_id is not None:
                        replacement["chunk_id"] = new_chunk_id
                    output.append(json.dumps(replacement, ensure_ascii=False))
                    changed = changed or replacement != record
                    if replacement != record:
                        result["manifest_entries"] += 1
                if changed:
                    rp.atomic_write_text(destination, "\n".join(output) + "\n")
        except Exception as exc:
            result["errors"].append(
                f"migrate historical manifest {destination}: {exc}"
            )
    return result


def migrate_path2_identity_for_safe_id(
    conversation_id: str,
    *,
    conversations_dir: str | Path,
    chromadb_path: str | Path,
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Resolve and migrate an existing import from only its new safe id.

    Lifecycle endpoints call this synchronously before mutating a historical
    Dialogue. Source discovery uses durable provenance in the manifest,
    ownership markers, and every discoverable Chroma copy. A hash collision or
    conflicting provenance is retained and reported rather than guessed.
    """
    safe_id = str(conversation_id or "").strip()
    result: dict[str, Any] = {
        "conversation_id": safe_id,
        "matched_source": "",
        "chromadb_records": 0,
        "chunk_files": 0,
        "manifest_entries": 0,
        "errors": [],
    }
    if not _SAFE_HISTORICAL_ID_RE.fullmatch(safe_id):
        return result

    try:
        from orchestrator import runtime_paths as rp
    except ImportError:  # pragma: no cover - legacy top-level context
        import runtime_paths as rp  # type: ignore

    sources: set[str] = set()

    def consider(value: Any) -> None:
        if not isinstance(value, str) or not value or value == safe_id:
            return
        try:
            if historical_conversation_id(value) == safe_id:
                sources.add(value)
        except ValueError:
            return

    destination = (
        Path(manifest_path) if manifest_path is not None
        else Path(rp.DATA_DIR_STR) / "conversation-manifest.jsonl"
    )
    if destination.exists():
        try:
            with rp.locked_file(destination):
                if destination.is_symlink() or not destination.is_file():
                    raise ValueError(f"refusing non-regular manifest {destination}")
                for line_no, line in enumerate(
                    destination.read_text(encoding="utf-8").splitlines(), 1
                ):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exc:
                        result["errors"].append(
                            f"historical source discovery "
                            f"{destination}:{line_no}: {exc}"
                        )
                        continue
                    if (not isinstance(record, dict)
                            or record.get("managed_by") != "ora"
                            or record.get("artifact_kind") != "conversation_chunk"):
                        continue
                    consider(record.get("source_path"))
                    consider(record.get("conversation_id"))
        except Exception as exc:
            result["errors"].append(
                f"historical source discovery manifest {destination}: {exc}"
            )

    root = Path(conversations_dir).expanduser().absolute()
    if root.exists() and not root.is_symlink() and root.is_dir():
        for path in sorted(root.glob("*.md")):
            if path.is_symlink() or not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
                owner = _OWNERSHIP_ID_RE.search(text)
                if owner is not None:
                    consider(json.loads(owner.group("value")))
            except Exception as exc:
                result["errors"].append(
                    f"historical source discovery chunk {path}: {exc}"
                )
    elif root.exists():
        result["errors"].append(
            f"historical source discovery: refusing non-directory {root}"
        )

    try:
        import chromadb
        from orchestrator import embedding
        client = chromadb.PersistentClient(path=str(chromadb_path))
        for physical_name in embedding.discover_collection_copies(
            client, "conversations",
        ):
            try:
                collection = embedding.get_collection(client, physical_name)
            except Exception:
                continue
            try:
                rows = collection.get(include=["metadatas"])
                for metadata in rows.get("metadatas") or []:
                    if not _historical_record(metadata):
                        continue
                    consider(metadata.get("source_path"))
                    consider(metadata.get("raw_path"))
            except Exception as exc:
                result["errors"].append(
                    f"historical source discovery ChromaDB "
                    f"{physical_name}: {exc}"
                )
    except Exception as exc:
        result["errors"].append(f"historical source discovery ChromaDB: {exc}")

    if len(sources) > 1:
        result["errors"].append(
            f"historical identity {safe_id} resolves to conflicting sources: "
            + ", ".join(sorted(sources))
        )
        return result
    if not sources:
        return result
    source = next(iter(sources))
    migrated = migrate_legacy_path2_identity(
        source,
        conversations_dir=conversations_dir,
        chromadb_path=chromadb_path,
        manifest_path=manifest_path,
    )
    result.update({
        "matched_source": source,
        "chromadb_records": migrated.get("chromadb_records", 0),
        "chunk_files": migrated.get("chunk_files", 0),
        "manifest_entries": migrated.get("manifest_entries", 0),
    })
    result["errors"].extend(migrated.get("errors") or [])
    return result


def backfill_legacy_path2_identities(
    *,
    conversations_dir: str | Path,
    chromadb_path: str | Path,
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Explicit runtime backfill for every discoverable legacy Path-2 source.

    This function is intentionally callable, idempotent, and unscheduled. It
    scans only Ora-managed historical provenance, then delegates each source
    to the same exact migration used by the emitter and lifecycle boundary.
    """
    try:
        from orchestrator import runtime_paths as rp
    except ImportError:  # pragma: no cover - legacy top-level context
        import runtime_paths as rp  # type: ignore

    sources: set[str] = set()
    errors: list[str] = []

    def add_source(value: Any) -> None:
        if not isinstance(value, str):
            return
        source = value.strip()
        if not source or _SAFE_HISTORICAL_ID_RE.fullmatch(source):
            return
        # Legacy ownership was a source path. Do not reinterpret an arbitrary
        # user conversation id as a path-derived historical source.
        if ("/" in source or "\\" in source or source.startswith("~")
                or source.casefold().endswith(".md")):
            sources.add(source)

    destination = (
        Path(manifest_path) if manifest_path is not None
        else Path(rp.DATA_DIR_STR) / "conversation-manifest.jsonl"
    )
    if destination.exists():
        try:
            with rp.locked_file(destination):
                if destination.is_symlink() or not destination.is_file():
                    raise ValueError(f"refusing non-regular manifest {destination}")
                for line_no, line in enumerate(
                    destination.read_text(encoding="utf-8").splitlines(), 1
                ):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exc:
                        errors.append(
                            f"historical manifest {destination}:{line_no}: {exc}"
                        )
                        continue
                    if (isinstance(record, dict)
                            and record.get("managed_by") == "ora"
                            and record.get("artifact_kind") == "conversation_chunk"):
                        add_source(record.get("source_path"))
                        add_source(record.get("conversation_id"))
        except Exception as exc:
            errors.append(f"historical manifest discovery {destination}: {exc}")

    root = Path(conversations_dir).expanduser().absolute()
    if root.exists() and not root.is_symlink() and root.is_dir():
        for path in sorted(root.glob("*.md")):
            if path.is_symlink() or not path.is_file():
                continue
            try:
                match = _OWNERSHIP_ID_RE.search(
                    path.read_text(encoding="utf-8")
                )
                if match is not None:
                    add_source(json.loads(match.group("value")))
            except Exception as exc:
                errors.append(f"historical chunk discovery {path}: {exc}")
    elif root.exists():
        errors.append(f"historical chunk discovery: refusing non-directory {root}")

    try:
        import chromadb
        from orchestrator import embedding
        client = chromadb.PersistentClient(path=str(chromadb_path))
        for physical_name in embedding.discover_collection_copies(
            client, "conversations",
        ):
            try:
                collection = embedding.get_collection(client, physical_name)
            except Exception:
                continue
            try:
                rows = collection.get(include=["metadatas"])
                for metadata in rows.get("metadatas") or []:
                    if not _historical_record(metadata):
                        continue
                    add_source(metadata.get("source_path"))
                    add_source(metadata.get("raw_path"))
            except Exception as exc:
                errors.append(
                    f"historical ChromaDB discovery {physical_name}: {exc}"
                )
    except Exception as exc:
        errors.append(f"historical ChromaDB discovery: {exc}")

    migrations: dict[str, dict[str, Any]] = {}
    for source in sorted(sources):
        migrated = migrate_legacy_path2_identity(
            source,
            conversations_dir=conversations_dir,
            chromadb_path=chromadb_path,
            manifest_path=manifest_path,
        )
        migrations[historical_conversation_id(source)] = migrated
        errors.extend(migrated.get("errors") or [])
    return {
        "sources_discovered": len(sources),
        "migrations": migrations,
        "errors": errors,
    }


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
    manifest_path: str | Path | None = None,
    embedder: Callable[[list[str]], list[list[float]]] | None = None,
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
    conversation_id   = historical_conversation_id(source_chat)
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

    privacy_states: set[bool] = set()
    for candidate_path in cleaned_pair_paths:
        try:
            candidate = (
                first if candidate_path == cleaned_pair_paths[0]
                else load_cleaned_pair(candidate_path)
            )
        except Exception:
            continue
        privacy_states.add(
            any(str(value).casefold() == "private" for value in candidate.tags)
        )
    if len(privacy_states) > 1:
        result.errors.append(
            "conflicting Standard/Private tags across one historical source; "
            "no chunks emitted"
        )
        result.duration_secs = time.monotonic() - start
        return result
    conversation_tag = "private" if True in privacy_states else ""

    migration = migrate_legacy_path2_identity(
        source_chat,
        conversations_dir=conversations_dir,
        chromadb_path=chromadb_path,
        manifest_path=manifest_path,
        legacy_conversation_ids=(source_chat,),
    )
    result.errors.extend(migration.get("errors") or [])

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
        chunk_id = f"session-{session_id}-pair-{cp.source_pair_num:03d}"

        if chunk_path in seen_filenames:
            # Intra-session collision — suffix with pair number.
            stem, ext = os.path.splitext(base_name)
            chunk_path = os.path.join(
                conversations_dir,
                f"{stem}-pair{cp.source_pair_num:03d}{ext}",
            )
        elif os.path.lexists(chunk_path) and not _chunk_file_owned_by(
            chunk_path, conversation_id, chunk_id,
        ):
            stem, ext = os.path.splitext(base_name)
            chunk_path = os.path.join(
                conversations_dir,
                f"{stem}-pair{cp.source_pair_num:03d}{ext}",
            )

        if (os.path.lexists(chunk_path)
                and not _chunk_file_owned_by(
                    chunk_path, conversation_id, chunk_id,
                )
                and chunk_path not in seen_filenames):
            result.errors.append(
                f"chunk filename collision is not owned by {chunk_id}: "
                f"{chunk_path}"
            )
            continue

        # Skip-if-exists ONLY skips the file write (not the indexing).
        # ChromaDB upsert is idempotent — re-indexing an existing chunk
        # is safe, and this lets re-runs catch any pairs whose index
        # failed on a prior run (e.g. embedding-model errors).
        skip_write = (
            skip_if_chunk_exists
            and os.path.lexists(chunk_path)
            and _chunk_file_owned_by(chunk_path, conversation_id, chunk_id)
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
                chunk_md = attach_chunk_ownership(build_chunk_markdown(
                    user_input    = cp.cleaned_user_input,
                    ai_response   = cp.cleaned_ai_response,
                    context_header= context_header,
                    when          = when,
                    tag           = conversation_tag,
                ), conversation_id=conversation_id, chunk_id=chunk_id)
            except Exception as e:
                result.errors.append(
                    f"build chunk md pair {cp.source_pair_num}: {e}"
                )
                continue

            try:
                append_chunk_manifest(
                    conversation_id=conversation_id,
                    chunk_id=chunk_id,
                    chunk_path=chunk_path,
                    tag=conversation_tag,
                    # The source archive is imported input, not an Ora-owned
                    # raw log eligible for Delete Forever.
                    raw_path="",
                    source_path=source_chat,
                    manifest_path=manifest_path,
                )
            except Exception as e:
                result.errors.append(
                    f"manifest {os.path.basename(chunk_path)}: {e}"
                )

            try:
                from orchestrator import runtime_paths as rp
                rp.atomic_write_text(Path(chunk_path), chunk_md)
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
                raw_path          = "",
                chunk_path        = chunk_path,
                when              = when,
                first_user_input  = first_user_input,
                topic_primary     = topic_primary,
                topics            = topics,
                turn_summary      = cp.pair_context or context_header[:200],
                thread_id         = cp.thread_id,
                tag               = conversation_tag,
                source_platform   = f"historical-{source_platform}",
                chain_id          = chain_id,
                chain_label       = chain_label,
            )
            meta["source_path"] = source_chat
        except Exception as e:
            result.errors.append(
                f"build chroma meta pair {cp.source_pair_num}: {e}"
            )
            continue

        result.chunk_ids.append(chunk_id)

        # Explicit embedding orientation — paste-free user voice + context
        # header. The separately stored retrieval document remains complete,
        # including both speakers, so lexical and returned-document retrieval
        # never loses the assistant response or long exchange content.
        # We exclude pasted segments from the embedding so RAG queries
        # find the user's actual thinking, not pasted articles. The chunk
        # markdown file body still carries the full text including pastes
        # for visibility; only the embedded representation is paste-free.
        # If the user input was 100% paste (e.g. "[long article]"), we
        # fall back to context_header alone — at minimum the embedding
        # captures the conversation's session-level context.
        user_voice = _user_voice_only(cp)
        embedding_text = build_embedding_orientation(
            context_header, user_voice,
        )[:MAX_EMBED_CHARS]
        meta["embedding_text_sha256"] = hashlib.sha256(
            embedding_text.encode("utf-8")
        ).hexdigest()
        chroma_records.append({
            "id":       chunk_id,
            "document": build_retrieval_document(
                context_header, cp.cleaned_user_input, cp.cleaned_ai_response,
            ),
            "embedding_text": embedding_text,
            "metadata": meta,
        })

    # Bulk add to ChromaDB. ChromaDB upsert idempotency: ids are
    # deterministic, so re-running this orchestrator overwrites existing
    # records rather than duplicating them.
    if chroma_records:
        try:
            from orchestrator.embedding import EMBEDDING_DIM, get_embedding_function
            embedding_function = embedder or get_embedding_function()
            vectors = embedding_function([
                r["embedding_text"] for r in chroma_records
            ])
            if len(vectors) != len(chroma_records):
                raise ValueError("conversation embedder returned the wrong vector count")
            if any(len(vector) != EMBEDDING_DIM for vector in vectors):
                raise ValueError("conversation embedder returned the wrong vector dimension")
        except Exception as exc:
            result.errors.append(f"chromadb embedding: {str(exc)[:200]}")
            vectors = []

        if vectors:
            try:
                chromadb_collection.upsert(
                    ids       = [r["id"]       for r in chroma_records],
                    documents = [r["document"] for r in chroma_records],
                    metadatas = [r["metadata"] for r in chroma_records],
                    embeddings= vectors,
                )
                result.chunks_indexed = len(chroma_records)
            except Exception:
                # Preserve complete stored documents on batch failure. A
                # per-record retry isolates bad records without silently
                # truncating retrievable conversation content.
                indexed = 0
                for r, vector in zip(chroma_records, vectors):
                    try:
                        chromadb_collection.upsert(
                            ids=[r["id"]],
                            documents=[r["document"]],
                            metadatas=[r["metadata"]],
                            embeddings=[vector],
                        )
                        indexed += 1
                    except Exception as exc:
                        result.errors.append(
                            f"chromadb upsert {r['id']}: {str(exc)[:200]}"
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
    manifest_path:     str | Path | None = None,
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
        # A collection-open failure means no session can make progress.  The
        # old behavior returned synthetic error results without invoking the
        # progress callback, so the caller reported a zero-work success and
        # ingest exited 0.  Fail loudly instead: supervisors must retry or
        # stop, never mistake a broken database for a drained queue.
        raise RuntimeError(f"open ChromaDB conversations collection: {e}") from e

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
            manifest_path       = manifest_path,
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
    "historical_conversation_id",
    "migrate_legacy_path2_identity",
    "migrate_path2_identity_for_safe_id",
    "backfill_legacy_path2_identities",
    "emit_chunks_for_session",
    "emit_chunks_for_all_sessions",
    "group_cleaned_pairs_by_session",
]
