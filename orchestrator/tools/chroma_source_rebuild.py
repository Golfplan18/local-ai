#!/usr/bin/env python3
"""Source-driven Chroma rebuilds into an explicit, inactive store.

The live Chroma directory is a derived cache.  This module rebuilds logical
collections from their durable sources without reading the old Chroma store or
mutating those sources.  Implemented phases are:

* ``conversations`` — historical rows from the authoritative cleaned-pair
  archive plus manifest-owned live/legacy chunk Markdown;
* ``knowledge`` — vault Engrams, Resources, the Ora mental-model library, and
  the MSI News mirror with its special metadata/body filter and HCP layout;
* ``msi-news-articles`` — MSI's canonical published articles composed through
  the project-owned news indexer (the sibling Columns tree is not in scope).

All phases require an explicit inactive target, use deterministic ids and
atomic checkpoints for resume, and validate their complete source plans before
opening Chroma.  Source-derived phases batch ``embedding.embed_texts`` and pass
explicit 4,096-dimensional vectors to Chroma; ``--dry-run`` cannot call an
embedding API.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import stat
import struct
import subprocess
from collections import defaultdict, deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from orchestrator import runtime_paths as rp
from orchestrator.conversation_chunk import (
    build_chroma_metadata,
    build_embedding_orientation,
    build_retrieval_document,
)
from orchestrator.historical.chain_detector import derive_session_id
from orchestrator.historical.cleaned_pair_reader import (
    CleanedPairFile,
    _parse_frontmatter,
    _parse_iso_timestamp,
    _section,
    _strip_optional_subsection,
    _strip_yaml_quotes,
)
from orchestrator.historical.path2_orchestrator import (
    MAX_EMBED_CHARS,
    _compose_context_header,
    _historical_model_id,
    _topics_from_pair,
    _user_voice_only,
    historical_conversation_id,
)


_OWNER_RE = re.compile(
    r'<!-- ora-conversation-id: (?P<value>"(?:[^"\\]|\\.)*") -->'
)
_CHUNK_RE = re.compile(
    r'<!-- ora-chunk-id: (?P<value>"(?:[^"\\]|\\.)*") -->'
)
_LOCAL_CONTEXT_RE = re.compile(
    r"Local AI session on (?P<date>\d{4}-\d{2}-\d{2}), panel "
    r"'(?P<conversation>[^'\r\n]+)', model (?P<model>[^.\r\n]+)\. "
    r"Turn (?P<turn>\d+)\b"
)
_PAIR_CONTEXT_RE = re.compile(r"\bPair\s+(?P<turn>\d+)\s+of\s+(?P<total>\d+)\b")
_TITLE_RE = re.compile(r"\AConversation\s+'(?P<title>.+?)'\s+on\s+", re.DOTALL)
_SESSION_ID_RE = re.compile(r"\Asession-(?P<session>.+)-pair-(?P<turn>\d+)\Z")
_FILENAME_PAIR_RE = re.compile(r"(?:\A|[_-])pair-?(?P<turn>\d+)(?:[_-]|\.)")
_FILENAME_TIME_RE = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2})_(?P<hour>\d{2})-(?P<minute>\d{2})"
)
_SAFE_ID_RE = re.compile(r"\A[^/\\\x00\r\n]{1,255}\Z")


class RebuildError(RuntimeError):
    """A source or validation error that must stop before cutover."""


@dataclass(frozen=True)
class ReplayRecord:
    row_id: str
    document: str
    metadata: dict[str, Any]
    source_path: str
    source_kind: str
    embedding_text: str = ""

    def payload_fingerprint(self) -> str:
        payload = json.dumps(
            {"document": self.document, "metadata": self.metadata},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def source_fingerprint(self) -> str:
        """Fingerprint stored payload plus the exact text being embedded."""
        digest = hashlib.sha256()
        digest.update(self.payload_fingerprint().encode("ascii"))
        digest.update(b"\0")
        digest.update((self.embedding_text or self.document).encode("utf-8"))
        return digest.hexdigest()


@dataclass
class ConversationReplayPlan:
    records: list[ReplayRecord] = field(default_factory=list)
    planned_records: int = 0
    plan_fingerprint: str = ""
    historical_files: int = 0
    historical_sessions: int = 0
    live_files: int = 0
    derived_historical_files: int = 0
    shadowed_manifest_entries: int = 0
    ignored_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def require_valid(self) -> None:
        if self.errors:
            preview = "\n".join(f"- {error}" for error in self.errors[:20])
            remaining = len(self.errors) - min(len(self.errors), 20)
            if remaining:
                preview += f"\n- ... and {remaining} more"
            raise RebuildError(f"conversation replay plan is invalid:\n{preview}")

    def fingerprint(self) -> str:
        if self.plan_fingerprint:
            return self.plan_fingerprint
        digest = hashlib.sha256()
        for record in sorted(self.records, key=lambda item: item.row_id):
            digest.update(record.row_id.encode("utf-8"))
            digest.update(b"\0")
            digest.update(record.source_fingerprint().encode("ascii"))
            digest.update(b"\n")
        return digest.hexdigest()

    def summary(self) -> dict[str, Any]:
        return {
            "records": self.planned_records or len(self.records),
            "historical_files": self.historical_files,
            "historical_sessions": self.historical_sessions,
            "live_files": self.live_files,
            "derived_historical_files": self.derived_historical_files,
            "shadowed_manifest_entries": self.shadowed_manifest_entries,
            "ignored_files": len(self.ignored_files),
            "errors": len(self.errors),
            "fingerprint": self.fingerprint() if not self.errors else "",
        }


@dataclass(frozen=True)
class SourceSpec:
    """One immutable source-file snapshot in a derived-corpus plan."""

    path: Path
    root: Path
    source_kind: str
    identity: tuple[int, int, int, int]


@dataclass(frozen=True)
class SourcePartition:
    """Immutable inventory binding for one configured source root."""

    root: Path
    label: str
    source_kind: str
    root_identity: tuple[int, int]
    inventory: tuple[SourceSpec, ...]


@dataclass
class SourceReplayPlan:
    """Bounded-memory plan for a source-derived Chroma collection."""

    phase: str
    logical_collection: str
    partitions: list[SourcePartition] = field(default_factory=list)
    sources: list[SourceSpec] = field(default_factory=list)
    planned_records: int = 0
    indexed_sources: int = 0
    skipped_sources: int = 0
    hcp_sources: int = 0
    hcp_records: int = 0
    hcp_fallback_sources: int = 0
    plan_fingerprint: str = ""
    payload_fingerprint: str = ""
    execution_fingerprint: str = ""
    semantic_payload_status: str = "exact"
    record_count_status: str = "exact"
    errors: list[str] = field(default_factory=list)
    composer: Any | None = field(default=None, repr=False)

    def require_valid(self) -> None:
        if self.errors:
            preview = "\n".join(f"- {error}" for error in self.errors[:20])
            remaining = len(self.errors) - min(len(self.errors), 20)
            if remaining:
                preview += f"\n- ... and {remaining} more"
            raise RebuildError(f"{self.phase} replay plan is invalid:\n{preview}")

    def fingerprint(self) -> str:
        return self.plan_fingerprint

    def summary(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "logical_collection": self.logical_collection,
            "source_partitions": len(self.partitions),
            "source_files": len(self.sources),
            "indexed_sources": self.indexed_sources,
            "skipped_sources": self.skipped_sources,
            "records": self.planned_records,
            "record_count_status": self.record_count_status,
            "hcp_sources": self.hcp_sources,
            "hcp_records": self.hcp_records,
            "hcp_fallback_sources": self.hcp_fallback_sources,
            "semantic_payload_status": self.semantic_payload_status,
            "payload_fingerprint": self.payload_fingerprint,
            "errors": len(self.errors),
            "source_inventory_fingerprint": (
                self.plan_fingerprint if not self.errors else ""
            ),
            "fingerprint": self.plan_fingerprint if not self.errors else "",
        }


@dataclass(frozen=True)
class _SourceBuild:
    records: tuple[ReplayRecord, ...]
    skipped: bool = False
    hcp: bool = False
    hcp_fallback: bool = False
    provisional_records: int = 0
    semantic_pending: bool = False


@dataclass(frozen=True)
class _PreparedKnowledgeSource:
    source: SourceSpec
    filepath: str
    meta: dict[str, Any]
    body: str
    skipped: bool = False
    structural_index: Any | None = None
    raw_chunks: tuple[Any, ...] = ()
    hcp_fallback: bool = False


@dataclass(frozen=True)
class _ExactSourceMaterialization:
    record_count: int
    payload_fingerprint: str
    execution_fingerprint: str
    cache_fingerprints: dict[str, str]


@dataclass(frozen=True)
class _ManifestOwner:
    conversation_id: str
    chunk_id: str
    raw_path: str
    tag: str


@dataclass(frozen=True)
class _Chunk:
    path: Path
    text: str
    context: str
    user_input: str
    ai_response: str
    tags: tuple[str, ...]
    owner_id: str = ""
    chunk_id: str = ""


def _absolute(path: str | Path) -> Path:
    return Path(path).expanduser().absolute()


def _assert_root(root: str | Path, *, label: str) -> Path:
    candidate = _absolute(root)
    if candidate.is_symlink():
        raise RebuildError(f"{label} must not be a symlink: {candidate}")
    if not candidate.is_dir():
        raise RebuildError(f"{label} is not a directory: {candidate}")
    return candidate


def _contained_file(path: Path, root: Path) -> bool:
    try:
        candidate = Path(os.path.realpath(path.absolute()))
        boundary = Path(os.path.realpath(root.absolute()))
        candidate.relative_to(boundary)
        return True
    except ValueError:
        return False


def _read_text_snapshot(path: Path, root: Path, *, label: str) -> str:
    """Read one unchanged regular file without following its final symlink."""
    candidate = _absolute(path)
    if not _contained_file(candidate, root):
        raise RebuildError(f"{label} escapes {root}: {candidate}")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(candidate, flags)
    except OSError as exc:
        raise RebuildError(f"cannot securely open {label} {candidate}: {exc}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise RebuildError(f"{label} is not a regular file: {candidate}")
        chunks: list[bytes] = []
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            chunks.append(block)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    identity_before = (
        before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns
    )
    identity_after = (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
    )
    if identity_before != identity_after:
        raise RebuildError(f"{label} changed during read: {candidate}")
    try:
        return b"".join(chunks).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RebuildError(f"{label} is not UTF-8: {candidate}: {exc}") from exc


def _source_identity(path: Path) -> tuple[int, int, int, int]:
    """Return a no-follow identity for one regular source file."""
    try:
        value = path.lstat()
    except OSError as exc:
        raise RebuildError(f"cannot stat source file {path}: {exc}") from exc
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode):
        raise RebuildError(f"source is not a non-symlink regular file: {path}")
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


def _source_root_identity(path: Path) -> tuple[int, int]:
    """Bind a configured root without coupling to unrelated directory mtimes."""
    try:
        value = path.lstat()
    except OSError as exc:
        raise RebuildError(f"cannot stat source root {path}: {exc}") from exc
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISDIR(value.st_mode):
        raise RebuildError(f"source root is not a non-symlink directory: {path}")
    return value.st_dev, value.st_ino


def _assert_source_unchanged(source: SourceSpec) -> None:
    current = _source_identity(source.path)
    if current != source.identity:
        raise RebuildError(f"source changed after planning: {source.path}")


def _markdown_sources(
    root: str | Path,
    *,
    label: str,
    source_kind: str,
) -> tuple[Path, list[SourceSpec]]:
    source_root = _assert_root(root, label=label)
    sources: list[SourceSpec] = []
    paths: list[Path] = []
    for current, directories, filenames in os.walk(source_root, followlinks=False):
        directories.sort()
        filenames.sort()
        for directory in directories:
            candidate = Path(current) / directory
            if candidate.is_symlink():
                raise RebuildError(
                    f"{label} contains a symlink directory: {candidate}"
                )
        for filename in filenames:
            if filename.startswith(".") or not filename.endswith(".md"):
                continue
            paths.append(Path(current) / filename)
    for path in sorted(paths, key=lambda item: str(item)):
        sources.append(SourceSpec(
            path=_absolute(path), root=source_root,
            source_kind=source_kind, identity=_source_identity(path),
        ))
    return source_root, sources


def _snapshot_source_partition(
    root: str | Path,
    *,
    label: str,
    source_kind: str,
) -> tuple[SourcePartition, list[SourceSpec]]:
    source_root, sources = _markdown_sources(
        root, label=label, source_kind=source_kind,
    )
    return SourcePartition(
        root=source_root,
        label=label,
        source_kind=source_kind,
        root_identity=_source_root_identity(source_root),
        inventory=tuple(sources),
    ), sources


def _assert_source_inventory_unchanged(plan: SourceReplayPlan) -> None:
    """Re-inventory every configured partition, including empty roots."""
    if not plan.partitions:
        raise RebuildError(
            f"{plan.phase} source plan has no configured partition bindings"
        )
    for expected in plan.partitions:
        try:
            current, _sources = _snapshot_source_partition(
                expected.root,
                label=expected.label,
                source_kind=expected.source_kind,
            )
        except Exception as exc:
            raise RebuildError(
                f"{plan.phase} source inventory changed for "
                f"{expected.label}: {exc}"
            ) from exc
        if current.root_identity != expected.root_identity:
            raise RebuildError(
                f"{plan.phase} source inventory changed for {expected.label}: "
                f"configured root identity differs ({expected.root})"
            )
        if current.inventory == expected.inventory:
            continue
        expected_items = {
            str(source.path.relative_to(expected.root)): source.identity
            for source in expected.inventory
        }
        current_items = {
            str(source.path.relative_to(current.root)): source.identity
            for source in current.inventory
        }
        added = sorted(current_items.keys() - expected_items.keys())
        removed = sorted(expected_items.keys() - current_items.keys())
        changed = sorted(
            path for path in current_items.keys() & expected_items.keys()
            if current_items[path] != expected_items[path]
        )
        details: list[str] = []
        if added:
            details.append(f"added={added[:5]}")
        if removed:
            details.append(f"removed={removed[:5]}")
        if changed:
            details.append(f"identity_changed={changed[:5]}")
        raise RebuildError(
            f"{plan.phase} source inventory changed for {expected.label}: "
            + ", ".join(details)
        )


def _parse_cleaned_pair_text(path: Path, text: str) -> CleanedPairFile:
    yaml, body = _parse_frontmatter(text)
    try:
        pair_num = int(yaml.get("source_pair_num", "0"))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"unparseable source_pair_num: {yaml.get('source_pair_num')!r}"
        ) from exc
    if "## Exchange" not in body:
        raise ValueError("missing `## Exchange` section")
    raw_tags = str(yaml.get("tags", "") or "").strip()
    if raw_tags.startswith("[") and raw_tags.endswith("]"):
        raw_tags = raw_tags[1:-1]
    user_section = _section(body, "### User input", ["### Assistant response"])
    ai_section = _section(body, "### Assistant response", [])
    return CleanedPairFile(
        file_path=str(path),
        source_chat=_strip_yaml_quotes(yaml.get("source_chat", "")),
        source_pair_num=pair_num,
        source_platform=yaml.get("source_platform", "unknown"),
        source_timestamp=_parse_iso_timestamp(yaml.get("source_timestamp", "")),
        thread_id=yaml.get("thread_id", ""),
        prior_pair=_strip_yaml_quotes(yaml.get("prior_pair", "")),
        next_pair=_strip_yaml_quotes(yaml.get("next_pair", "")),
        processing_model=_strip_yaml_quotes(yaml.get("processing_model", "")),
        processed_at=_parse_iso_timestamp(yaml.get("processed_at", "")),
        tags=[
            item.strip().strip("'\"")
            for item in raw_tags.split(",")
            if item.strip()
        ],
        session_context=_section(
            body, "### Session context", ["### Pair context", "## Exchange"]
        ),
        pair_context=_section(body, "### Pair context", ["## Exchange"]),
        cleaned_user_input=_strip_optional_subsection(
            user_section, "Pasted segments"
        ),
        cleaned_ai_response=_strip_optional_subsection(
            ai_section, "Engagement strip log"
        ),
    )


def _load_chain_index(path: Path | None, root: Path) -> tuple[dict[str, str], dict[str, str]]:
    if path is None or not path.exists():
        return {}, {}
    data = json.loads(_read_text_snapshot(path, root, label="chain index"))
    if not isinstance(data, dict):
        raise RebuildError("chain index is not an object")
    session_to_chain = data.get("session_to_chain") or {}
    if not isinstance(session_to_chain, dict):
        raise RebuildError("chain index session_to_chain is not an object")
    chain_labels: dict[str, str] = {}
    for item in data.get("chains") or []:
        if isinstance(item, dict) and item.get("chain_id"):
            chain_labels[str(item["chain_id"])] = str(item.get("chain_label") or "")
    return (
        {str(key): str(value) for key, value in session_to_chain.items()},
        chain_labels,
    )


def _source_signature(context: str, user_input: str, ai_response: str) -> str:
    digest = hashlib.sha256()
    for value in (context.strip(), user_input.strip(), ai_response.strip()):
        digest.update(value.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _historical_records(
    archive_root: Path,
    *,
    chain_index: Path | None,
    chain_root: Path,
    plan: ConversationReplayPlan,
    materialize: bool,
) -> tuple[list[ReplayRecord], set[str], dict[str, str]]:
    # Two passes deliberately trade disk reads for bounded memory.  Retaining
    # 41k full cleaned pairs also retains every assistant response and can
    # exceed the memory available during a recovery.  Pass 1 keeps only the
    # session-wide facts needed by Pass 2's exact row construction.
    paths = sorted(archive_root.glob("*.md"), key=lambda item: item.name)
    session_numbers: dict[str, list[int]] = defaultdict(list)
    session_privacy: dict[str, set[str]] = defaultdict(set)
    stealth_sessions: set[str] = set()
    first_user_inputs: dict[str, tuple[int, str]] = {}
    valid_paths: list[Path] = []
    for path in paths:
        try:
            text = _read_text_snapshot(path, archive_root, label="cleaned pair")
            pair = _parse_cleaned_pair_text(path, text)
            if not pair.source_chat:
                raise ValueError("source_chat is empty")
            if pair.source_pair_num < 1:
                raise ValueError("source_pair_num must be positive")
            if pair.source_timestamp is None:
                raise ValueError("source_timestamp is missing or invalid")
            lowered_tags = {tag.casefold() for tag in pair.tags}
            if "stealth" in lowered_tags:
                stealth_sessions.add(pair.source_chat)
            valid_paths.append(path)
            session_numbers[pair.source_chat].append(pair.source_pair_num)
            session_privacy[pair.source_chat].add(
                "private" if "private" in lowered_tags else ""
            )
            prior_first = first_user_inputs.get(pair.source_chat)
            if prior_first is None or pair.source_pair_num < prior_first[0]:
                first_user_inputs[pair.source_chat] = (
                    pair.source_pair_num, pair.cleaned_user_input
                )
        except Exception as exc:
            plan.errors.append(f"cleaned pair {path}: {exc}")

    try:
        session_to_chain, chain_labels = _load_chain_index(
            chain_index, chain_root
        )
    except Exception as exc:
        plan.errors.append(str(exc))
        session_to_chain, chain_labels = {}, {}

    plan.historical_sessions = len(session_numbers.keys() - stealth_sessions)
    records: list[ReplayRecord] = []
    fingerprints: dict[str, str] = {}
    signatures: set[str] = set()
    invalid_sessions: set[str] = set()
    session_tags: dict[str, str] = {}
    for source_chat, values in session_numbers.items():
        if source_chat in stealth_sessions:
            continue
        numbers = sorted(values)
        if len(numbers) != len(set(numbers)):
            plan.errors.append(
                f"historical session {source_chat!r} has duplicate pair numbers: "
                f"{numbers[:20]}"
            )
            invalid_sessions.add(source_chat)
            continue
        privacy = session_privacy[source_chat]
        if source_chat not in first_user_inputs:
            plan.errors.append(f"historical session {source_chat!r} has no readable pair")
            invalid_sessions.add(source_chat)
            continue
        # Privacy is session-scoped at retrieval time. Historical filtering
        # can leave a mixture of pair tags, so normalize conservatively: one
        # Private survivor makes the entire replayed session Private.
        session_tags[source_chat] = "private" if "private" in privacy else ""

    for path in valid_paths:
        try:
            text = _read_text_snapshot(path, archive_root, label="cleaned pair")
            pair = _parse_cleaned_pair_text(path, text)
        except Exception as exc:
            plan.errors.append(f"cleaned pair changed before replay {path}: {exc}")
            continue
        source_chat = pair.source_chat
        context = _compose_context_header(pair)
        signature = _source_signature(
            context, pair.cleaned_user_input, pair.cleaned_ai_response
        )
        if source_chat in stealth_sessions:
            plan.ignored_files.append(str(path))
            signatures.add(signature)
            continue
        if source_chat in invalid_sessions:
            continue
        plan.historical_files += 1
        tag = session_tags[source_chat]
        session_id = derive_session_id(source_chat)
        conversation_id = historical_conversation_id(source_chat)
        chain_id = session_to_chain.get(session_id, "")
        chain_label = chain_labels.get(chain_id, "")
        first_user_input = first_user_inputs[source_chat][1]
        final_turn = max(session_numbers[source_chat])
        topics = _topics_from_pair(pair)
        topic_primary = topics[0] if topics else ""
        document_voice = _user_voice_only(pair)
        embedding_text = (
            build_embedding_orientation(context, document_voice)
            if document_voice else context
        )[:MAX_EMBED_CHARS]
        document = build_retrieval_document(
            context, pair.cleaned_user_input, pair.cleaned_ai_response,
        )
        row_id = f"session-{session_id}-pair-{pair.source_pair_num:03d}"
        metadata = build_chroma_metadata(
            user_input=pair.cleaned_user_input,
            ai_response=pair.cleaned_ai_response,
            conversation_id=conversation_id,
            session_id=session_id,
            pair_num=pair.source_pair_num,
            model_id=_historical_model_id(pair.source_platform),
            raw_path="",
            # The cleaned-pair archive is the durable replay artifact.  Point
            # Obsidian/chunk provenance at that exact file while retaining
            # the original imported chat path separately as ``source_path``.
            chunk_path=str(path),
            when=pair.source_timestamp,
            first_user_input=first_user_input,
            topic_primary=topic_primary,
            topics=topics,
            turn_summary=pair.pair_context or context[:200],
            thread_id=pair.thread_id,
            tag=tag,
            source_platform=f"historical-{pair.source_platform}",
            chain_id=chain_id,
            chain_label=chain_label,
        )
        metadata["source_path"] = source_chat
        metadata["total_turns"] = final_turn
        metadata["is_last_turn"] = pair.source_pair_num == final_turn
        metadata["embedding_text_sha256"] = hashlib.sha256(
            embedding_text.encode("utf-8")
        ).hexdigest()
        record = ReplayRecord(
            row_id=row_id,
            document=document,
            metadata=metadata,
            source_path=pair.file_path,
            source_kind="historical_cleaned_pair",
            embedding_text=embedding_text,
        )
        fingerprint = record.source_fingerprint()
        prior = fingerprints.get(row_id)
        if prior is not None and prior != fingerprint:
            plan.errors.append(
                f"historical row id {row_id!r} has conflicting source payloads"
            )
        fingerprints[row_id] = fingerprint
        if materialize:
            records.append(record)
        signatures.add(signature)
    return records, signatures, fingerprints


def _frontmatter_tags(text: str) -> tuple[str, ...]:
    match = re.match(r"\A---\s*\n(?P<yaml>.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return ()
    raw = match.group("yaml")
    line = re.search(r"(?m)^tags:[ \t]*(?P<value>[^\n]*)$", raw)
    if not line:
        return ()
    value = line.group("value").strip()
    if value.startswith("[") and value.endswith("]"):
        return tuple(
            item.strip().strip("'\"")
            for item in value[1:-1].split(",")
            if item.strip()
        )
    if value:
        return (value.strip("'\""),)
    tail = raw[line.end():]
    out: list[str] = []
    for item in tail.splitlines():
        match_item = re.match(r"\s+-\s+(.+?)\s*$", item)
        if not match_item:
            if item.strip():
                break
            continue
        out.append(match_item.group(1).strip("'\""))
    return tuple(out)


def _parse_chunk(path: Path, text: str) -> _Chunk:
    context_heading = re.search(r"(?m)^## Context\s*$", text)
    exchange_heading = re.search(r"(?m)^## Exchange\s*$", text)
    if not context_heading or not exchange_heading or exchange_heading.start() <= context_heading.end():
        raise ValueError("missing or out-of-order Context/Exchange headings")
    context = text[context_heading.end():exchange_heading.start()].strip()
    exchange = text[exchange_heading.end():]
    user_heading = re.search(r"(?m)^\*\*User:\*\*\s*$", exchange)
    assistant_heading = re.search(r"(?m)^\*\*Assistant:\*\*\s*$", exchange)
    if not user_heading or not assistant_heading or assistant_heading.start() <= user_heading.end():
        raise ValueError("missing or out-of-order User/Assistant headings")
    user_input = exchange[user_heading.end():assistant_heading.start()].strip()
    ai_response = exchange[assistant_heading.end():].strip()
    owner = _OWNER_RE.search(text)
    chunk = _CHUNK_RE.search(text)
    if bool(owner) != bool(chunk):
        raise ValueError("only one ownership marker is present")
    owner_id = json.loads(owner.group("value")) if owner else ""
    chunk_id = json.loads(chunk.group("value")) if chunk else ""
    return _Chunk(
        path=path,
        text=text,
        context=context,
        user_input=user_input,
        ai_response=ai_response,
        tags=_frontmatter_tags(text),
        owner_id=owner_id,
        chunk_id=chunk_id,
    )


def _load_manifest_owners(
    manifest_path: Path | None,
    *,
    manifest_root: Path,
    conversations_root: Path,
    plan: ConversationReplayPlan,
) -> dict[Path, list[_ManifestOwner]]:
    if manifest_path is None or not manifest_path.exists():
        return {}
    text = _read_text_snapshot(manifest_path, manifest_root, label="conversation manifest")
    latest_by_chunk_id: dict[str, tuple[Path, _ManifestOwner]] = {}
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError("record is not an object")
            candidate = _absolute(str(item.get("chunk_path") or ""))
            conversation_id = str(item.get("conversation_id") or "")
            chunk_id = str(item.get("chunk_id") or "")
            if not _SAFE_ID_RE.fullmatch(conversation_id) or not chunk_id:
                raise ValueError("invalid conversation_id or chunk_id")
            owner = _ManifestOwner(
                conversation_id=conversation_id,
                chunk_id=chunk_id,
                raw_path=str(item.get("raw_path") or ""),
                tag=str(item.get("tag") or ""),
            )
            if chunk_id in latest_by_chunk_id:
                plan.shadowed_manifest_entries += 1
            latest_by_chunk_id[chunk_id] = (candidate, owner)
        except Exception as exc:
            plan.errors.append(f"manifest line {line_number}: {exc}")
    owners: dict[Path, list[_ManifestOwner]] = defaultdict(list)
    for candidate, owner in latest_by_chunk_id.values():
        if not _contained_file(candidate, conversations_root):
            continue
        if candidate.is_symlink() or not candidate.is_file():
            continue
        owners[candidate].append(owner)
    return owners


def _context_identity(context: str) -> tuple[str, str, int, int | None, str]:
    local = _LOCAL_CONTEXT_RE.search(context)
    if local:
        return (
            local.group("conversation"),
            local.group("model").strip(),
            int(local.group("turn")),
            None,
            "local",
        )
    pair = _PAIR_CONTEXT_RE.search(context)
    first_paragraph = context.split("\n\n", 1)[0].strip()
    title_match = _TITLE_RE.search(first_paragraph)
    title = title_match.group("title").strip() if title_match else ""
    identity = hashlib.sha256(first_paragraph.encode("utf-8")).hexdigest()[:16]
    if pair:
        return (
            f"replay-{identity}",
            "historical-replay",
            int(pair.group("turn")),
            int(pair.group("total")),
            title,
        )
    return f"replay-{identity}", "conversation-replay", 0, None, title


def _chunk_when(chunk: _Chunk) -> datetime:
    filename = _FILENAME_TIME_RE.search(chunk.path.name)
    date_value = ""
    try:
        yaml, _body = _parse_frontmatter(chunk.text)
        date_value = str(yaml.get("date created") or "")[:10]
    except Exception:
        pass
    if filename:
        date_value = date_value or filename.group("date")
        return datetime.strptime(
            f"{date_value} {filename.group('hour')}:{filename.group('minute')}",
            "%Y-%m-%d %H:%M",
        )
    if date_value:
        return datetime.strptime(date_value, "%Y-%m-%d")
    raise ValueError("cannot determine a stable chunk timestamp")


def _envelope(path: Path, sessions_root: Path) -> dict[str, Any]:
    if not _SAFE_ID_RE.fullmatch(path.name):
        return {}
    envelope_path = sessions_root / path.name / "conversation.json"
    if not envelope_path.exists():
        return {}
    text = _read_text_snapshot(envelope_path, sessions_root, label="conversation envelope")
    value = json.loads(text)
    return value if isinstance(value, dict) else {}


def _manifest_owner_for_chunk(
    chunk: _Chunk,
    candidates: list[_ManifestOwner],
    parsed_conversation_id: str,
    plan: ConversationReplayPlan,
) -> list[_ManifestOwner]:
    if not candidates:
        return []
    if not chunk.owner_id:
        return candidates
    matched = [
        owner for owner in candidates
        if owner.conversation_id == chunk.owner_id
        and owner.chunk_id == chunk.chunk_id
    ]
    if not matched:
        raise ValueError(
            "ownership markers disagree with every latest manifest record"
        )
    return matched


def _live_records(
    conversations_root: Path,
    *,
    historical_signatures: set[str],
    manifest_owners: dict[Path, list[_ManifestOwner]],
    sessions_root: Path | None,
    plan: ConversationReplayPlan,
    materialize: bool,
) -> tuple[list[ReplayRecord], dict[str, str]]:
    pending: list[tuple[_Chunk, ReplayRecord, int | None]] = []
    stealth_conversations: set[str] = set()
    for path in sorted(conversations_root.glob("*.md"), key=lambda item: item.name):
        try:
            text = _read_text_snapshot(path, conversations_root, label="conversation chunk")
            try:
                yaml, _body = _parse_frontmatter(text)
            except ValueError:
                # The flat root also carries explicit continuity documents.
                # They were never conversation-index inputs.
                plan.ignored_files.append(str(path))
                continue
            if str(yaml.get("type") or "").strip() != "chat":
                # Restart-recovery orphan reports intentionally use
                # status=errored/recovery=orphan_pending and have no Exchange
                # body.  Only canonical type:chat chunks feed Conv RAG.
                plan.ignored_files.append(str(path))
                continue
            chunk = _parse_chunk(path, text)
            signature = _source_signature(
                chunk.context, chunk.user_input, chunk.ai_response
            )
            parsed_id, model_id, turn_index, total_hint, parsed_title = (
                _context_identity(chunk.context)
            )
            candidates = manifest_owners.get(path, [])
            owners = _manifest_owner_for_chunk(
                chunk, candidates, parsed_id, plan
            )
            owner_privacy: list[tuple[_ManifestOwner, dict[str, Any], str]] = []
            for owner in owners:
                conversation_id = owner.conversation_id
                if not _SAFE_ID_RE.fullmatch(conversation_id):
                    raise ValueError(
                        f"invalid manifest conversation_id {conversation_id!r}"
                    )
                envelope: dict[str, Any] = {}
                if sessions_root is not None:
                    envelope = _envelope(
                        sessions_root / conversation_id, sessions_root
                    )
                privacy_sources = {
                    str(envelope.get("tag") or ""),
                    owner.tag,
                    *(item.casefold() for item in chunk.tags),
                }
                invalid_tags = privacy_sources - {"", "private", "stealth"}
                if invalid_tags:
                    raise ValueError(
                        f"invalid conversation tags {sorted(invalid_tags)!r}"
                    )
                tag = (
                    "stealth" if "stealth" in privacy_sources
                    else "private" if "private" in privacy_sources
                    else ""
                )
                if tag == "stealth":
                    stealth_conversations.add(conversation_id)
                owner_privacy.append((owner, envelope, tag))
            if signature in historical_signatures:
                plan.derived_historical_files += 1
                continue
            if not owners:
                # A canonical-looking file is not sufficient authority for
                # deletion/privacy metadata. Only latest manifest-owned rows
                # are replayed; unmanifested legacy/test residue is reported
                # as ignored rather than guessed into the new corpus.
                plan.ignored_files.append(str(path))
                continue
            for owner, envelope, tag in owner_privacy:
                conversation_id = owner.conversation_id
                row_id = owner.chunk_id
                owner_turn_index = turn_index
                session_match = _SESSION_ID_RE.fullmatch(row_id)
                if session_match:
                    session_id = session_match.group("session")
                    owner_turn_index = owner_turn_index or int(
                        session_match.group("turn")
                    )
                else:
                    session_id = hashlib.sha256(
                        conversation_id.encode("utf-8")
                    ).hexdigest()[:16]
                if owner_turn_index < 1:
                    filename_pair = _FILENAME_PAIR_RE.search(path.name)
                    owner_turn_index = (
                        int(filename_pair.group("turn")) if filename_pair else 1
                    )
                raw_path = owner.raw_path
                if raw_path:
                    raw_candidate = _absolute(raw_path)
                    raw_root = conversations_root / "raw"
                    if not _contained_file(raw_candidate, raw_root):
                        raise ValueError(
                            f"manifest raw_path escapes conversation raw root: {raw_path}"
                        )
                when = _chunk_when(chunk)
                topics: list[str] = []
                topic_primary = ""
                title = str(
                    envelope.get("display_name")
                    or parsed_title
                    or chunk.user_input[:80]
                ).strip()
                thread_id = f"thread_{conversation_id[:8]}_001"
                metadata = build_chroma_metadata(
                    user_input=chunk.user_input,
                    ai_response=chunk.ai_response,
                    conversation_id=conversation_id,
                    session_id=session_id,
                    pair_num=owner_turn_index,
                    model_id=model_id,
                    raw_path=raw_path,
                    chunk_path=str(path),
                    when=when,
                    first_user_input=title,
                    topic_primary=topic_primary,
                    topics=topics,
                    turn_summary=chunk.context,
                    thread_id=thread_id,
                    tag=tag,
                    source_platform=(
                        "local"
                        if model_id != "historical-replay"
                        else "historical-replay"
                    ),
                )
                metadata["conversation_title"] = (
                    title or f"Conversation {conversation_id}"
                )
                embedding_text = build_embedding_orientation(
                    chunk.context, chunk.user_input,
                )[:MAX_EMBED_CHARS]
                document = build_retrieval_document(
                    chunk.context, chunk.user_input, chunk.ai_response,
                )
                metadata["embedding_text_sha256"] = hashlib.sha256(
                    embedding_text.encode("utf-8")
                ).hexdigest()
                record = ReplayRecord(
                    row_id=row_id,
                    document=document,
                    metadata=metadata,
                    source_path=str(path),
                    source_kind="live_chunk",
                    embedding_text=embedding_text,
                )
                pending.append((chunk, record, total_hint))
        except Exception as exc:
            plan.ignored_files.append(str(path))
            plan.errors.append(f"conversation chunk {path}: {exc}")

    grouped: dict[str, list[tuple[_Chunk, ReplayRecord, int | None]]] = defaultdict(list)
    for item in pending:
        grouped[str(item[1].metadata["conversation_id"])].append(item)
    finalized_records: list[ReplayRecord] = []
    for conversation_id, items in grouped.items():
        if conversation_id in stealth_conversations:
            for _chunk, record, _hint in items:
                if record.source_path not in plan.ignored_files:
                    plan.ignored_files.append(record.source_path)
            continue
        final_turn = max(
            max(int(item[1].metadata["turn_index"]), int(item[2] or 0))
            for item in items
        )
        for _chunk, record, _hint in items:
            metadata = dict(record.metadata)
            metadata["total_turns"] = final_turn
            metadata["is_last_turn"] = int(metadata["turn_index"]) == final_turn
            finalized = ReplayRecord(
                row_id=record.row_id,
                document=record.document,
                metadata=metadata,
                source_path=record.source_path,
                source_kind=record.source_kind,
                embedding_text=record.embedding_text,
            )
            finalized_records.append(finalized)

    # Early live writers used only six random hex characters in session ids.
    # The real corpus contains a collision. Preserve every distinct source by
    # deterministically re-keying all conflicting rows; identical payloads
    # still coalesce as the same logical record.
    by_base_id: dict[str, list[ReplayRecord]] = defaultdict(list)
    for record in finalized_records:
        by_base_id[record.row_id].append(record)
    normalized: list[ReplayRecord] = []
    for base_id, candidates in by_base_id.items():
        by_payload: dict[str, ReplayRecord] = {}
        for candidate in candidates:
            by_payload.setdefault(candidate.source_fingerprint(), candidate)
        unique = list(by_payload.values())
        if len(unique) == 1:
            normalized.append(unique[0])
            continue
        for candidate in unique:
            identity = hashlib.sha256(
                f"{base_id}\0{candidate.source_path}".encode("utf-8")
            ).hexdigest()
            metadata = dict(candidate.metadata)
            metadata["replay_original_chunk_id"] = base_id
            normalized.append(ReplayRecord(
                row_id=f"replay-live-collision-{identity}",
                document=candidate.document,
                metadata=metadata,
                source_path=candidate.source_path,
                source_kind=candidate.source_kind,
                embedding_text=candidate.embedding_text,
            ))

    fingerprints: dict[str, str] = {
        record.row_id: record.source_fingerprint() for record in normalized
    }
    records = normalized if materialize else []
    plan.live_files = len(fingerprints)
    return records, fingerprints


def _deduplicate(records: Iterable[ReplayRecord], plan: ConversationReplayPlan) -> list[ReplayRecord]:
    by_id: dict[str, ReplayRecord] = {}
    for record in records:
        prior = by_id.get(record.row_id)
        if prior is None:
            by_id[record.row_id] = record
            continue
        if prior.source_fingerprint() != record.source_fingerprint():
            plan.errors.append(
                f"row id {record.row_id!r} maps to conflicting sources "
                f"{prior.source_path!r} and {record.source_path!r}"
            )
    return sorted(by_id.values(), key=lambda item: item.row_id)


def build_conversation_replay_plan(
    *,
    historical_archive: str | Path,
    conversations_root: str | Path,
    manifest_path: str | Path | None,
    chain_index_path: str | Path | None,
    sessions_root: str | Path | None,
    materialize: bool = True,
) -> ConversationReplayPlan:
    """Build and validate the full source inventory without opening Chroma."""
    plan = ConversationReplayPlan()
    try:
        archive = _assert_root(historical_archive, label="historical archive")
        conversations = _assert_root(conversations_root, label="conversations root")
        sessions = (
            _assert_root(sessions_root, label="sessions root")
            if sessions_root is not None and _absolute(sessions_root).exists()
            else None
        )
        manifest = _absolute(manifest_path) if manifest_path else None
        chain_index = _absolute(chain_index_path) if chain_index_path else None
        manifest_root = manifest.parent if manifest else conversations
        chain_root = chain_index.parent if chain_index else archive
        historical, signatures, historical_fingerprints = _historical_records(
            archive,
            chain_index=chain_index,
            chain_root=chain_root,
            plan=plan,
            materialize=materialize,
        )
        owners = _load_manifest_owners(
            manifest,
            manifest_root=manifest_root,
            conversations_root=conversations,
            plan=plan,
        )
        live, live_fingerprints = _live_records(
            conversations,
            historical_signatures=signatures,
            manifest_owners=owners,
            sessions_root=sessions,
            plan=plan,
            materialize=materialize,
        )
        combined_fingerprints = dict(historical_fingerprints)
        for row_id, fingerprint in live_fingerprints.items():
            prior = combined_fingerprints.get(row_id)
            if prior is not None and prior != fingerprint:
                plan.errors.append(
                    f"row id {row_id!r} conflicts between historical and live sources"
                )
            combined_fingerprints[row_id] = fingerprint
        plan.planned_records = len(combined_fingerprints)
        digest = hashlib.sha256()
        for row_id in sorted(combined_fingerprints):
            digest.update(row_id.encode("utf-8"))
            digest.update(b"\0")
            digest.update(combined_fingerprints[row_id].encode("ascii"))
            digest.update(b"\n")
        plan.plan_fingerprint = digest.hexdigest()
        if materialize:
            plan.records = _deduplicate([*historical, *live], plan)
    except Exception as exc:
        plan.errors.append(str(exc))
    return plan


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    with open(temporary, "x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _profile() -> dict[str, Any]:
    from orchestrator import embedding
    return {
        "provider": embedding.EMBEDDING_PROVIDER,
        "model": embedding.EMBEDDING_MODEL,
        "dimension": embedding.EMBEDDING_DIM,
        "physical_collection": embedding.resolve_collection("conversations"),
    }


def _validate_target(target: Path, *, resume: bool) -> None:
    active = _absolute(rp.chromadb_dir())
    candidate = _absolute(target)
    active_real = Path(os.path.realpath(active))
    candidate_real = Path(os.path.realpath(candidate))
    overlaps_active = candidate_real == active_real
    if not overlaps_active:
        try:
            candidate_real.relative_to(active_real)
            overlaps_active = True
        except ValueError:
            pass
    if not overlaps_active:
        try:
            active_real.relative_to(candidate_real)
            overlaps_active = True
        except ValueError:
            pass
    if overlaps_active:
        raise RebuildError(
            f"refusing Chroma target that overlaps the active store: {candidate}"
        )
    if candidate.is_symlink():
        raise RebuildError(f"target Chroma path must not be a symlink: {candidate}")
    if candidate.exists() and not candidate.is_dir():
        raise RebuildError(f"target Chroma path is not a directory: {candidate}")
    if candidate.exists() and any(candidate.iterdir()) and not resume:
        raise RebuildError(
            f"target Chroma path is non-empty; pass --resume only for this plan: {candidate}"
        )


def execute_conversation_replay(
    plan: ConversationReplayPlan,
    *,
    target_chromadb_path: str | Path,
    batch_size: int = 32,
    resume: bool = False,
    client_factory: Callable[[str], Any] | None = None,
    collection_factory: Callable[[Any, dict[str, Any]], Any] | None = None,
    embedder: Callable[[list[str]], list[list[float]]] | None = None,
) -> dict[str, Any]:
    """Embed/upsert a validated plan into an explicit inactive Chroma root."""
    plan.require_valid()
    if batch_size < 1:
        raise RebuildError("batch_size must be positive")
    target = _absolute(target_chromadb_path)
    _validate_target(target, resume=resume)
    profile = _profile()
    checkpoint = target / "conversation-replay-checkpoint.json"
    report_path = target / "conversation-replay-report.json"
    start_index = 0
    if checkpoint.exists():
        if not resume:
            raise RebuildError(f"checkpoint exists but --resume was not supplied: {checkpoint}")
        state = json.loads(checkpoint.read_text(encoding="utf-8"))
        if state.get("plan_fingerprint") != plan.fingerprint():
            raise RebuildError("checkpoint plan fingerprint does not match current sources")
        if state.get("profile") != profile:
            raise RebuildError("checkpoint embedding profile does not match current config")
        start_index = int(state.get("next_index") or 0)
        if start_index < 0 or start_index > len(plan.records):
            raise RebuildError("checkpoint next_index is outside the replay plan")
    target.mkdir(parents=True, exist_ok=True)

    if client_factory is None:
        import chromadb
        client_factory = lambda path: chromadb.PersistentClient(path=path)
    client = client_factory(str(target))
    if collection_factory is None:
        from orchestrator.embedding import get_or_create_collection
        collection_factory = lambda current_client, current_profile: (
            get_or_create_collection(
                current_client,
                "conversations",
                metadata={
                    "hnsw:space": "cosine",
                    "ora:embedding_profile": (
                        f"{current_profile['provider']}:{current_profile['model']}"
                    ),
                    "ora:embedding_dimension": current_profile["dimension"],
                },
            )
        )
    collection = collection_factory(client, profile)

    records = plan.records
    for index in range(0, start_index, 1000):
        _validate_stored_payloads(
            collection,
            records[index:min(index + 1000, start_index)],
            context="checkpoint-resumed conversation prefix",
        )
    for index in range(start_index, len(records), batch_size):
        batch = records[index:index + batch_size]
        existing = _existing_payloads(collection, batch)
        missing: list[ReplayRecord] = []
        for record in batch:
            prior = existing.get(record.row_id)
            if prior is None:
                missing.append(record)
                continue
            if prior != record.payload_fingerprint():
                raise RebuildError(
                    "existing target payload differs from source plan for "
                    f"{record.row_id!r}"
                )
            if not resume:
                raise RebuildError(
                    f"target unexpectedly already contains {record.row_id!r}"
                )
        if missing:
            if any(not record.embedding_text for record in missing):
                raise RebuildError(
                    "conversation replay record lacks explicit embedding orientation"
                )
            if embedder is None:
                from orchestrator.embedding import embed_texts
                active_embedder = embed_texts
            else:
                active_embedder = embedder
            vectors = active_embedder([
                record.embedding_text for record in missing
            ])
            if len(vectors) != len(missing):
                raise RebuildError(
                    "conversation embedder returned the wrong vector count"
                )
            dimension = int(profile["dimension"])
            if any(len(vector) != dimension for vector in vectors):
                raise RebuildError(
                    "conversation embedder returned the wrong vector dimension"
                )
            collection.upsert(
                ids=[record.row_id for record in missing],
                documents=[record.document for record in missing],
                metadatas=[record.metadata for record in missing],
                embeddings=vectors,
            )
        _atomic_json(checkpoint, {
            "schema_version": 1,
            "plan_fingerprint": plan.fingerprint(),
            "profile": profile,
            "next_index": index + len(batch),
            "records": len(records),
        })

    count = int(collection.count())
    if count != len(records):
        raise RebuildError(
            f"target count mismatch: expected {len(records)}, found {count}"
        )
    for index in range(0, len(records), 1000):
        _validate_stored_payloads(
            collection,
            records[index:index + 1000],
            context="final conversation validation",
        )
    report = {
        "status": "complete",
        "target_chromadb_path": str(target),
        "profile": profile,
        "plan": plan.summary(),
        "target_count": count,
    }
    _atomic_json(report_path, report)
    return report


# ---------------------------------------------------------------------------
# Validated conversation promotion / rollback
# ---------------------------------------------------------------------------


_PROMOTION_TAGS = ("", "private")
_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")


def _strict_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RebuildError(f"{label} is missing or unsafe: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RebuildError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise RebuildError(f"{label} must be a JSON object: {path}")
    return value


def _replay_evidence(inactive: Path, active: Path) -> dict[str, Any]:
    if (
        inactive.is_symlink() or not inactive.is_dir()
        or active.is_symlink() or not active.is_dir()
    ):
        raise RebuildError("active/inactive Chroma root is missing or unsafe")
    inactive_real, active_real = map(
        Path, (os.path.realpath(inactive), os.path.realpath(active)),
    )
    if (
        inactive_real == active_real
        or inactive_real in active_real.parents
        or active_real in inactive_real.parents
    ):
        raise RebuildError("active and inactive Chroma roots must be disjoint")
    report = _strict_json(
        inactive / "conversation-replay-report.json", "conversation replay report",
    )
    checkpoint = _strict_json(
        inactive / "conversation-replay-checkpoint.json", "conversation replay checkpoint",
    )
    profile, plan = report.get("profile"), report.get("plan")
    if (
        report.get("status") != "complete"
        or not isinstance(profile, dict) or checkpoint.get("profile") != profile
        or not isinstance(plan, dict)
        or Path(os.path.realpath(str(report.get("target_chromadb_path") or "")))
        != inactive_real
    ):
        raise RebuildError("conversation replay evidence is inconsistent")
    try:
        counts = (
            int(report["target_count"]), int(plan["records"]),
            int(checkpoint["records"]), int(checkpoint["next_index"]),
        )
        normalized = {
            "provider": profile["provider"], "model": profile["model"],
            "dimension": int(profile["dimension"]),
            "physical_collection": profile["physical_collection"],
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise RebuildError("conversation replay evidence is incomplete") from exc
    fingerprint = plan.get("fingerprint")
    if (
        len(set(counts)) != 1 or counts[0] < 1
        or checkpoint.get("plan_fingerprint") != fingerprint
        or not isinstance(fingerprint, str) or not _SHA256_RE.fullmatch(fingerprint)
        or any(not isinstance(normalized[key], str) or not normalized[key]
               for key in ("provider", "model", "physical_collection"))
        or normalized["dimension"] < 1
    ):
        raise RebuildError("conversation replay evidence does not agree")
    return {"profile": normalized, "count": counts[0], "fingerprint": fingerprint}


def _config_state(
    path: Path, expected: str,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    from orchestrator import retrieval_config

    config = _strict_json(path, "Chroma config")
    collections, histories = config.get("collections"), config.get("collection_history")
    if not isinstance(collections, dict) or collections.get("conversations") != expected:
        found = collections.get("conversations") if isinstance(collections, dict) else None
        raise RebuildError(f"conversation mapping guard expected {expected!r}, found {found!r}")
    if histories is None:
        histories = {}
    if not isinstance(config.get("embedder"), dict) or not isinstance(histories, dict):
        raise RebuildError("Chroma config embedder/history is invalid")
    active = retrieval_config.active_embedding_profile(config)
    profile = {
        "provider": active.get("provider"), "model": active.get("model"),
        "dimension": int(active.get("dimensions") or 0), "profile_id": active.get("id"),
    }
    if (
        not profile["provider"] or not profile["model"] or profile["dimension"] < 1
        or profile["profile_id"] != f"{profile['provider']}:{profile['model']}"
    ):
        raise RebuildError("Chroma config embedding profile is inconsistent")
    history = histories.get("conversations") or []
    history = [history] if isinstance(history, str) else history
    if not isinstance(history, list) or any(
        not isinstance(name, str) or not name for name in history
    ):
        raise RebuildError("conversation collection history is invalid")
    return config, profile, list(dict.fromkeys(history))


def _profile_key(profile: dict[str, Any]) -> tuple[str, str, int]:
    return profile["provider"], profile["model"], int(profile["dimension"])


def _flip_mapping(path: Path, config: dict[str, Any], expected: str, target: str) -> list[str]:
    if config["collections"].get("conversations") != expected:
        raise RebuildError("conversation mapping changed before atomic flip")
    histories = config.get("collection_history") or {}
    history = histories.get("conversations") or []
    history = [history] if isinstance(history, str) else history
    config["collections"] = {**config["collections"], "conversations": target}
    new_history = [expected, *(name for name in history if name not in {expected, target})]
    config["collection_history"] = {**histories, "conversations": new_history}
    rp.atomic_write_text(
        path, json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        mode=stat.S_IMODE(path.lstat().st_mode),
    )
    return new_history


def _ora_server_pids(ora_home: str | Path, ps_output: str | None = None) -> list[int]:
    target = str(Path(os.path.realpath(ora_home)) / "server" / "app.py")
    if ps_output is None:
        try:
            process = subprocess.run(
                ["ps", "-axww", "-o", "pid=,command="], check=False,
                capture_output=True, text=True, timeout=5,
            )
        except Exception as exc:
            raise RebuildError("could not verify that Ora is stopped") from exc
        if process.returncode:
            raise RebuildError("could not verify that Ora is stopped")
        ps_output = process.stdout
    python = re.compile(r"\A[Pp]ython(?:[0-9]+(?:\.[0-9]+)*)?(?:\s+-\S+)*\Z")
    pids: list[int] = []
    for line in ps_output.splitlines():
        match = re.match(r"\s*(\d+)\s+(.+)\Z", line)
        if not match:
            continue
        command = match.group(2)
        position = command.find(target)
        if position < 0:
            continue
        before = command[:position].rstrip().rsplit("/", 1)[-1]
        after = command[position + len(target):]
        if python.fullmatch(before) and (not after or after.startswith(" ")):
            pids.append(int(match.group(1)))
    return pids


def _require_stopped(home: Path, probe: Callable[[str | Path], list[int]]) -> None:
    pids = probe(home)
    if pids:
        raise RebuildError(
            f"Ora is active for ORA_HOME {home} (PID(s): {', '.join(map(str, pids))})"
        )


def _collection_names(client: Any) -> set[str]:
    return {
        name for item in client.list_collections()
        if (name := (item if isinstance(item, str) else getattr(item, "name", "")))
    }


def _collection_profile(collection: Any, profile: dict[str, Any]) -> dict[str, Any]:
    metadata = getattr(collection, "metadata", None)
    try:
        dimension = int(metadata.get("ora:embedding_dimension"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise RebuildError("conversation collection profile metadata is invalid") from exc
    if (
        metadata.get("ora:logical_collection") != "conversations"
        or metadata.get("ora:embedding_profile")
        != f"{profile['provider']}:{profile['model']}"
        or dimension != int(profile["dimension"])
    ):
        raise RebuildError("conversation collection embedding profile does not match")
    return metadata


def _collection_ids(collection: Any) -> list[str]:
    result = collection.get(include=[])
    ids = result.get("ids") if isinstance(result, dict) else None
    ids = ids.tolist() if hasattr(ids, "tolist") else ids
    if (
        not isinstance(ids, list) or any(not isinstance(value, str) for value in ids)
        or len(ids) != len(set(ids)) or int(collection.count()) != len(ids)
    ):
        raise RebuildError("conversation collection count/id coverage is invalid")
    return sorted(ids)


def _float32_ordered_key(value: float) -> int:
    """Map a finite float32 value to its monotonic IEEE-754 integer key."""
    try:
        bits = struct.unpack(">I", struct.pack(">f", value))[0]
    except (OverflowError, struct.error) as exc:
        raise RebuildError("conversation embedding is outside float32 range") from exc
    magnitude = bits & 0x7FFFFFFF
    if magnitude == 0:
        return 0x80000000
    if bits & 0x80000000:
        return 0x80000000 - magnitude
    return 0x80000000 + magnitude


def _compare_copied_embeddings(
    source: Any,
    target: Any,
    profile: dict[str, Any],
    batch_size: int,
) -> dict[str, int | float]:
    """Validate one Chroma copy without requiring impossible bitwise identity.

    A cosine collection normalizes supplied vectors when it persists its HNSW
    index. Reading a vector and upserting it into another cosine collection can
    therefore move a component by one float32 ULP even though no new embedding
    was computed. Everything except that single-copy serialization boundary
    remains exact; two ULPs or any malformed vector fail closed.
    """
    if batch_size < 1:
        raise RebuildError("embedding comparison requires a positive batch")
    source_ids, target_ids = _collection_ids(source), _collection_ids(target)
    if source_ids != target_ids:
        raise RebuildError("copied conversation embedding ids differ")
    dimension = int(profile["dimension"])
    drifted_rows = 0
    drifted_components = 0
    maximum_ulps = 0
    maximum_absolute_delta = 0.0
    for start in range(0, len(source_ids), batch_size):
        requested = source_ids[start:start + batch_size]
        batches: list[dict[str, list[float]]] = []
        for collection in (source, target):
            result = collection.get(ids=requested, include=["embeddings"])
            ids = result.get("ids") if isinstance(result, dict) else None
            embeddings = result.get("embeddings") if isinstance(result, dict) else None
            ids = ids.tolist() if hasattr(ids, "tolist") else ids
            embeddings = (
                embeddings.tolist() if hasattr(embeddings, "tolist") else embeddings
            )
            if (
                not isinstance(ids, list) or not isinstance(embeddings, list)
                or len(ids) != len(requested) or len(embeddings) != len(requested)
            ):
                raise RebuildError("copied conversation embeddings are misaligned")
            rows = dict(zip(ids, embeddings))
            if len(rows) != len(requested) or set(rows) != set(requested):
                raise RebuildError("copied conversation embedding ids are incorrect")
            normalized: dict[str, list[float]] = {}
            for row_id in requested:
                vector = rows[row_id]
                vector = vector.tolist() if hasattr(vector, "tolist") else vector
                if not isinstance(vector, list) or len(vector) != dimension:
                    raise RebuildError("copied conversation embedding dimension differs")
                try:
                    converted = [float(value) for value in vector]
                except (TypeError, ValueError) as exc:
                    raise RebuildError(
                        "copied conversation embedding is non-numeric"
                    ) from exc
                if not all(math.isfinite(value) for value in converted):
                    raise RebuildError("copied conversation embedding is non-finite")
                normalized[row_id] = converted
            batches.append(normalized)
        source_rows, target_rows = batches
        for row_id in requested:
            row_drifted = False
            for source_value, target_value in zip(
                source_rows[row_id], target_rows[row_id],
            ):
                distance = abs(
                    _float32_ordered_key(source_value)
                    - _float32_ordered_key(target_value)
                )
                if distance > 1:
                    raise RebuildError(
                        "copied conversation embedding exceeds one float32 ULP"
                    )
                if distance:
                    row_drifted = True
                    drifted_components += 1
                    maximum_ulps = max(maximum_ulps, distance)
                    maximum_absolute_delta = max(
                        maximum_absolute_delta,
                        abs(source_value - target_value),
                    )
            if row_drifted:
                drifted_rows += 1
    return {
        "rows": len(source_ids),
        "components": len(source_ids) * dimension,
        "drifted_rows": drifted_rows,
        "drifted_components": drifted_components,
        "max_float32_ulp": maximum_ulps,
        "max_absolute_delta": maximum_absolute_delta,
    }


def _audit(
    collection: Any, profile: dict[str, Any], batch_size: int, copy_to: Any | None = None,
) -> tuple[dict[str, Any], dict[str, tuple[str, list[float]]]]:
    _collection_profile(collection, profile)
    all_ids = _collection_ids(collection)
    digests = {
        key: hashlib.sha256()
        for key in ("ids", "documents", "metadatas", "embeddings")
    }
    privacy, samples = {"": 0, "private": 0, "stealth": 0}, {}
    for start in range(0, len(all_ids), batch_size):
        requested = all_ids[start:start + batch_size]
        result = collection.get(
            ids=requested, include=["documents", "metadatas", "embeddings"],
        )
        values: dict[str, list[Any]] = {}
        for key in ("ids", "documents", "metadatas", "embeddings"):
            value = result.get(key) if isinstance(result, dict) else None
            value = value.tolist() if hasattr(value, "tolist") else value
            if not isinstance(value, list) or len(value) != len(requested):
                raise RebuildError("conversation collection returned a misaligned batch")
            values[key] = value
        rows = dict(zip(values["ids"], zip(
            values["documents"], values["metadatas"], values["embeddings"],
        )))
        if len(rows) != len(requested) or set(rows) != set(requested):
            raise RebuildError("conversation collection returned incorrect batch ids")
        documents, metadatas, embeddings = [], [], []
        for row_id in requested:
            document, metadata, vector = rows[row_id]
            vector = vector.tolist() if hasattr(vector, "tolist") else vector
            try:
                vector = [float(value) for value in vector]
            except (TypeError, ValueError) as exc:
                raise RebuildError(f"invalid embedding for {row_id!r}") from exc
            if (
                not isinstance(document, str) or not isinstance(metadata, dict)
                or len(vector) != int(profile["dimension"])
                or not all(math.isfinite(value) for value in vector)
            ):
                raise RebuildError(f"invalid conversation payload/vector for {row_id!r}")
            tag, orientation_hash = metadata.get("tag"), metadata.get(
                "embedding_text_sha256"
            )
            if tag not in _PROMOTION_TAGS:
                raise RebuildError(f"invalid privacy tag for {row_id!r}")
            if not isinstance(orientation_hash, str) or not _SHA256_RE.fullmatch(
                orientation_hash
            ):
                raise RebuildError(f"missing orientation hash for {row_id!r}")
            if not all(part in document for part in (
                "## Context", "## Exchange", "**User:**", "**Assistant:**",
            )):
                raise RebuildError(f"full conversation exchange is absent for {row_id!r}")
            payloads = {
                "ids": row_id, "documents": [row_id, document],
                "metadatas": [row_id, metadata],
                "embeddings": [row_id, [value.hex() for value in vector]],
            }
            for key, payload in payloads.items():
                digests[key].update(json.dumps(
                    payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                ).encode("utf-8") + b"\n")
            privacy[tag] += 1
            samples.setdefault(tag, (row_id, vector))
            documents.append(document); metadatas.append(metadata); embeddings.append(vector)
        if copy_to is not None:
            copy_to.upsert(
                ids=requested, documents=documents,
                metadatas=metadatas, embeddings=embeddings,
            )
    return ({
        "count": len(all_ids), "id_sha256": digests["ids"].hexdigest(),
        "document_sha256": digests["documents"].hexdigest(),
        "metadata_sha256": digests["metadatas"].hexdigest(),
        "embedding_sha256": digests["embeddings"].hexdigest(),
        "dimension": int(profile["dimension"]),
        "profile": f"{profile['provider']}:{profile['model']}",
        "privacy_counts": privacy,
    }, samples)


def _privacy_smoke(
    collection: Any, samples: dict[str, tuple[str, list[float]]],
) -> dict[str, int]:
    try:
        query_vector = next(iter(samples.values()))[1]
    except StopIteration as exc:
        raise RebuildError("conversation replay has no audited query vector") from exc
    checks = (
        ("standard", {"$and": [
            {"tag": {"$ne": "private"}}, {"tag": {"$ne": "stealth"}},
        ]}, {""}),
        ("private", {"tag": {"$ne": "stealth"}}, {"", "private"}),
        ("stealth", None, set(_PROMOTION_TAGS)),
    )
    counts: dict[str, int] = {}
    for label, where, allowed in checks:
        kwargs = {
            "query_embeddings": [query_vector], "n_results": 5,
            "include": ["documents", "metadatas"],
        }
        if where is not None:
            kwargs["where"] = where
        result = collection.query(**kwargs)
        try:
            ids, docs, metas = result["ids"][0], result["documents"][0], result["metadatas"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise RebuildError(f"{label} query smoke returned invalid rows") from exc
        if (
            not all(isinstance(values, list) for values in (ids, docs, metas))
            or not (len(ids) == len(docs) == len(metas))
            or any(not isinstance(row_id, str) for row_id in ids)
            or len(ids) != len(set(ids))
        ):
            raise RebuildError(f"{label} query smoke returned invalid rows")
        if any(
            not isinstance(meta, dict) or meta.get("tag") not in allowed
            for meta in metas
        ):
            raise RebuildError(f"{label} query smoke violated its privacy filter")
        if ids:
            read = collection.get(ids=ids, include=["documents", "metadatas"])
            read_values = []
            for key in ("ids", "documents", "metadatas"):
                value = read.get(key) if isinstance(read, dict) else None
                value = value.tolist() if hasattr(value, "tolist") else value
                read_values.append(value)
            read_ids, read_docs, read_metas = read_values
            if (
                not all(isinstance(values, list) for values in read_values)
                or not (len(read_ids) == len(read_docs) == len(read_metas) == len(ids))
                or any(not isinstance(row_id, str) for row_id in read_ids)
                or len(read_ids) != len(set(read_ids))
                or set(read_ids) != set(ids)
            ):
                raise RebuildError(f"{label} query/read smoke payload mismatch")
            queried = dict(zip(ids, zip(docs, metas)))
            stored = dict(zip(read_ids, zip(read_docs, read_metas)))
            if stored != queried:
                raise RebuildError(f"{label} query/read smoke payload mismatch")
        counts[label] = len(ids)
    return counts


def _embedding_function(_profile: dict[str, Any]) -> Any:
    from orchestrator.embedding import get_embedding_function
    return get_embedding_function()


def _chroma_client(path: str) -> Any:
    import chromadb
    return chromadb.PersistentClient(path=path)


def promote_conversation_replay(
    *,
    inactive_chromadb_path: str | Path,
    target_physical_collection: str,
    expected_current_physical: str,
    batch_size: int = 128,
    lock_timeout: float = rp.DEFAULT_LOCK_TIMEOUT,
    active_chromadb_path: str | Path | None = None,
    config_path: str | Path | None = None,
    ora_home: str | Path | None = None,
    client_factory: Callable[[str], Any] | None = None,
    embedding_function_factory: Callable[[dict[str, Any]], Any] | None = None,
    ora_active_probe: Callable[[str | Path], list[int]] | None = None,
) -> dict[str, Any]:
    if (
        batch_size < 1 or not target_physical_collection or not expected_current_physical
        or target_physical_collection == expected_current_physical
    ):
        raise RebuildError("promotion requires a positive batch and distinct physical names")
    inactive, active = _absolute(inactive_chromadb_path), _absolute(
        active_chromadb_path or rp.chromadb_dir()
    )
    home = _absolute(ora_home or rp.WORKSPACE)
    if config_path is None:
        from orchestrator import retrieval_config
        config_path = retrieval_config.CHROMADB_CONFIG_PATH
    config_path = _absolute(config_path)
    evidence = _replay_evidence(inactive, active)
    replay_profile, source_name = evidence["profile"], evidence["profile"]["physical_collection"]
    client_for, ef_for = client_factory or _chroma_client, (
        embedding_function_factory or _embedding_function
    )
    probe = ora_active_probe or _ora_server_pids
    try:
        with rp.locked_file(config_path, timeout=lock_timeout):
            _require_stopped(home, probe)
            _state, profile, history = _config_state(config_path, expected_current_physical)
            if _profile_key(profile) != _profile_key(replay_profile):
                raise RebuildError("replay and active embedding profiles differ")
            if target_physical_collection in history:
                raise RebuildError("promotion target is already in collection history")
            source_client, active_client = client_for(str(inactive)), client_for(str(active))
            source_names, active_names = (
                _collection_names(source_client), _collection_names(active_client),
            )
            if (
                source_name not in source_names
                or expected_current_physical not in active_names
                or target_physical_collection in active_names
            ):
                raise RebuildError("source/current missing or promotion target is not fresh")
            embedding_function = ef_for(profile)
            source = source_client.get_collection(
                name=source_name, embedding_function=embedding_function,
            )
            target = active_client.create_collection(
                name=target_physical_collection,
                metadata=dict(_collection_profile(source, replay_profile)),
                embedding_function=embedding_function,
            )
            try:
                source_audit, _ = _audit(
                    source, replay_profile, batch_size, copy_to=target,
                )
                target_audit, samples = _audit(target, replay_profile, batch_size)
                source_exact = {
                    key: value for key, value in source_audit.items()
                    if key != "embedding_sha256"
                }
                target_exact = {
                    key: value for key, value in target_audit.items()
                    if key != "embedding_sha256"
                }
                if (
                    source_audit["count"] != evidence["count"]
                    or target_exact != source_exact
                ):
                    raise RebuildError("promoted collection count/hash/profile/privacy differs")
                copy_validation = _compare_copied_embeddings(
                    source, target, replay_profile, batch_size,
                )
                smoke = _privacy_smoke(target, samples)
                _require_stopped(home, probe)
                latest, latest_profile, _ = _config_state(
                    config_path, expected_current_physical,
                )
                if _profile_key(latest_profile) != _profile_key(profile):
                    raise RebuildError("embedding profile changed during promotion")
                history = _flip_mapping(
                    config_path, latest, expected_current_physical,
                    target_physical_collection,
                )
            except BaseException:
                try:
                    mapped = _strict_json(
                        config_path, "Chroma config",
                    ).get("collections", {}).get("conversations")
                except Exception:
                    mapped = None
                if mapped == expected_current_physical:
                    try:
                        active_client.delete_collection(name=target_physical_collection)
                    except Exception as cleanup_error:
                        raise RebuildError(
                            "promotion failed and its fresh target could not be removed"
                        ) from cleanup_error
                raise
    except TimeoutError as exc:
        raise RebuildError("timed out acquiring the Chroma cutover lock") from exc
    return {
        "status": "promoted", "active_chromadb_path": str(active),
        "source_physical_collection": source_name,
        "previous_physical_collection": expected_current_physical,
        "active_physical_collection": target_physical_collection,
        "replay_fingerprint": evidence["fingerprint"], "validation": source_audit,
        "copy_validation": copy_validation,
        "query_smoke": smoke, "collection_history": history,
        "rollback": {
            "expected_current_physical": target_physical_collection,
            "restore_physical_collection": expected_current_physical,
        },
    }


def rollback_conversation_mapping(
    *,
    restore_physical_collection: str,
    expected_current_physical: str,
    lock_timeout: float = rp.DEFAULT_LOCK_TIMEOUT,
    active_chromadb_path: str | Path | None = None,
    config_path: str | Path | None = None,
    ora_home: str | Path | None = None,
    client_factory: Callable[[str], Any] | None = None,
    embedding_function_factory: Callable[[dict[str, Any]], Any] | None = None,
    ora_active_probe: Callable[[str | Path], list[int]] | None = None,
) -> dict[str, Any]:
    if (
        not restore_physical_collection or not expected_current_physical
        or restore_physical_collection == expected_current_physical
    ):
        raise RebuildError("rollback requires distinct non-empty physical names")
    active, home = _absolute(active_chromadb_path or rp.chromadb_dir()), _absolute(
        ora_home or rp.WORKSPACE
    )
    if active.is_symlink() or not active.is_dir():
        raise RebuildError(f"active Chroma root is missing or unsafe: {active}")
    if config_path is None:
        from orchestrator import retrieval_config
        config_path = retrieval_config.CHROMADB_CONFIG_PATH
    config_path = _absolute(config_path)
    client_for, ef_for = client_factory or _chroma_client, (
        embedding_function_factory or _embedding_function
    )
    probe = ora_active_probe or _ora_server_pids
    try:
        with rp.locked_file(config_path, timeout=lock_timeout):
            _require_stopped(home, probe)
            _state, profile, history = _config_state(config_path, expected_current_physical)
            client = client_for(str(active))
            names = _collection_names(client)
            if (
                restore_physical_collection not in history
                or expected_current_physical not in names
                or restore_physical_collection not in names
            ):
                raise RebuildError("rollback collection is not retained or present")
            restore = client.get_collection(
                name=restore_physical_collection, embedding_function=ef_for(profile),
            )
            _collection_profile(restore, profile)
            restored_count = len(_collection_ids(restore))
            if not restored_count:
                raise RebuildError("rollback conversation collection is empty")
            _require_stopped(home, probe)
            latest, latest_profile, latest_history = _config_state(
                config_path, expected_current_physical,
            )
            if (
                _profile_key(latest_profile) != _profile_key(profile)
                or restore_physical_collection not in latest_history
            ):
                raise RebuildError("rollback guard changed during validation")
            history = _flip_mapping(
                config_path, latest, expected_current_physical, restore_physical_collection,
            )
    except TimeoutError as exc:
        raise RebuildError("timed out acquiring the Chroma cutover lock") from exc
    return {
        "status": "rolled_back", "active_chromadb_path": str(active),
        "previous_physical_collection": expected_current_physical,
        "active_physical_collection": restore_physical_collection,
        "target_count": restored_count, "collection_history": history,
    }


# ---------------------------------------------------------------------------
# Source-derived knowledge and dedicated MSI news collections
# ---------------------------------------------------------------------------


def _prepare_knowledge_source(source: SourceSpec) -> _PreparedKnowledgeSource:
    """Prepare deterministic structure without opening an embedder.

    For a long-form source this deliberately stops at canonical raw HCP
    chunks.  Their semantic scores, context depths, storage payloads, and
    therefore possibly their final storage-part count remain pending until
    execution materializes cosine scores through the active embedding
    profile.
    """
    from orchestrator.tools import index_msi_news
    from orchestrator.tools import knowledge_index

    _assert_source_unchanged(source)
    content = _read_text_snapshot(
        source.path, source.root, label=source.source_kind,
    )
    if len(content.strip()) < 50:
        return _PreparedKnowledgeSource(
            source=source, filepath=str(source.path), meta={}, body="",
            skipped=True,
        )

    meta, body = knowledge_index._parse_frontmatter(content)
    if source.source_kind == "knowledge_msi_news":
        filtered = index_msi_news.msi_body_filter(body)
        if filtered.strip():
            body = filtered
        meta = {**meta, **index_msi_news.MSI_META_OVERRIDES}

    filepath = str(source.path)
    if len(body) > knowledge_index.CHUNK_THRESHOLD_CHARS:
        try:
            from orchestrator.tools import hcp
            structural_index = hcp.build_structural_index(body)
            # A constant scorer is used only to ask canonical HCP for its raw
            # chunk boundaries.  None of these provisional prefixes can flow
            # into an execution payload.
            raw_chunks = hcp.chunk_with_context(
                body, structural_index,
                max_chunk_tokens=knowledge_index.HCP_MAX_CHUNK_TOKENS,
                similarity_fn=lambda _text: 0.0,
            )
        except Exception:
            # Parity with knowledge_index._index_chunked: an HCP preparation
            # failure falls back to the legacy single-record representation.
            structural_index = None
            raw_chunks = []
            hcp_fallback = True
        else:
            hcp_fallback = False
        if len(raw_chunks) >= 2:
            return _PreparedKnowledgeSource(
                source=source,
                filepath=filepath,
                meta=meta,
                body=body,
                structural_index=structural_index,
                raw_chunks=tuple(raw_chunks),
            )
        return _PreparedKnowledgeSource(
            source=source,
            filepath=filepath,
            meta=meta,
            body=body,
            hcp_fallback=hcp_fallback,
        )
    return _PreparedKnowledgeSource(
        source=source, filepath=filepath, meta=meta, body=body,
    )


def _knowledge_source_records(
    source: SourceSpec,
    *,
    similarity_scores: list[float] | None = None,
    prepared: _PreparedKnowledgeSource | None = None,
) -> _SourceBuild:
    """Compose canonical records, requiring exact scores for HCP payloads."""
    from orchestrator.tools import knowledge_index

    prepared = prepared or _prepare_knowledge_source(source)
    if prepared.skipped:
        return _SourceBuild(records=(), skipped=True)
    filepath = prepared.filepath
    meta = prepared.meta
    body = prepared.body
    doc_id = os.path.abspath(filepath)
    records: list[ReplayRecord] = []
    if prepared.raw_chunks:
        if similarity_scores is None:
            return _SourceBuild(
                records=(), hcp=True,
                provisional_records=len(prepared.raw_chunks),
                semantic_pending=True,
            )
        if len(similarity_scores) != len(prepared.raw_chunks):
            raise RebuildError(
                f"HCP score count mismatch for {source.path}: expected "
                f"{len(prepared.raw_chunks)}, found {len(similarity_scores)}"
            )
        from orchestrator.tools import hcp
        from orchestrator.tools.hcp import format_chunk_for_extraction
        score_iter = iter(similarity_scores)
        chunks = hcp.chunk_with_context(
            body,
            prepared.structural_index,
            max_chunk_tokens=knowledge_index.HCP_MAX_CHUNK_TOKENS,
            similarity_fn=lambda _text: next(score_iter),
        )
        if len(chunks) != len(prepared.raw_chunks):
            raise RebuildError(
                f"canonical HCP chunk count changed for {source.path}"
            )
        try:
            next(score_iter)
        except StopIteration:
            pass
        else:  # pragma: no cover - count check above is the primary guard
            raise RebuildError(f"unused HCP scores remain for {source.path}")
        if len(chunks) >= 2:
            total = len(chunks)
            for chunk_number, chunk in enumerate(chunks, 1):
                formatted = format_chunk_for_extraction(chunk)
                parts = knowledge_index._split_for_storage(
                    formatted, knowledge_index.MAX_INDEX_CHARS,
                )
                base_id = knowledge_index._chunk_record_id(
                    doc_id, chunk_number,
                )
                for part_number, part_text in enumerate(parts, 1):
                    row_id = (
                        base_id
                        if len(parts) == 1
                        else f"{base_id}-part-{part_number}"
                    )
                    metadata = knowledge_index._compose_chroma_metadata(
                        filepath, meta,
                    )
                    metadata["chunk_index"] = chunk_number
                    metadata["total_chunks"] = total
                    records.append(ReplayRecord(
                        row_id=row_id,
                        document=part_text,
                        metadata=metadata,
                        source_path=filepath,
                        source_kind=source.source_kind,
                        embedding_text=knowledge_index._build_embed_text(
                            meta, part_text, filepath,
                        ),
                    ))
            return _SourceBuild(
                records=tuple(records), hcp=True,
            )

    metadata = knowledge_index._compose_chroma_metadata(filepath, meta)
    records.append(ReplayRecord(
        row_id=doc_id,
        document=body[:knowledge_index.MAX_INDEX_CHARS],
        metadata=metadata,
        source_path=filepath,
        source_kind=source.source_kind,
        embedding_text=knowledge_index._build_embed_text(
            meta, body, filepath,
        ),
    ))
    return _SourceBuild(
        records=tuple(records), hcp=False,
        hcp_fallback=prepared.hcp_fallback,
    )


def _load_msi_composer(path: str | Path) -> Any:
    """Load the approved MSI news composer from its exact local file."""
    composer_path = _absolute(path)
    if composer_path.is_symlink() or not composer_path.is_file():
        raise RebuildError(
            f"MSI news composer is not a regular non-symlink file: {composer_path}"
        )
    module_name = (
        "ora_msi_news_index_rebuild_"
        + hashlib.sha256(str(composer_path).encode("utf-8")).hexdigest()[:12]
    )
    spec = importlib.util.spec_from_file_location(module_name, composer_path)
    if spec is None or spec.loader is None:
        raise RebuildError(f"cannot load MSI news composer: {composer_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    required = (
        "_parse_frontmatter",
        "_compose_chroma_metadata",
        "_build_embed_text",
        "_filename_slug",
    )
    missing = [name for name in required if not callable(getattr(module, name, None))]
    if missing:
        raise RebuildError(
            f"MSI news composer lacks required functions: {', '.join(missing)}"
        )
    return module


def _msi_article_source_records(
    source: SourceSpec,
    composer: Any,
) -> _SourceBuild:
    _assert_source_unchanged(source)
    content = _read_text_snapshot(
        source.path, source.root, label="MSI published article",
    )
    if len(content.strip()) < 50:
        return _SourceBuild(records=(), skipped=True)
    meta, body = composer._parse_frontmatter(content)
    document = composer._build_embed_text(meta, body)
    if not str(document or "").strip():
        return _SourceBuild(records=(), skipped=True)
    filepath = str(source.path)
    return _SourceBuild(records=(ReplayRecord(
        row_id=str(composer._filename_slug(filepath)),
        document=str(document),
        metadata=composer._compose_chroma_metadata(filepath, meta),
        source_path=filepath,
        source_kind=source.source_kind,
    ),))


def _records_for_source(
    plan: SourceReplayPlan,
    source: SourceSpec,
) -> _SourceBuild:
    if plan.phase == "knowledge":
        return _knowledge_source_records(source)
    if plan.phase == "msi-news-articles":
        if plan.composer is None:
            raise RebuildError("MSI source plan has no loaded composer")
        return _msi_article_source_records(source, plan.composer)
    raise RebuildError(f"unsupported source replay phase: {plan.phase}")


def _finish_source_plan(plan: SourceReplayPlan) -> SourceReplayPlan:
    digest = hashlib.sha256()
    digest.update(plan.phase.encode("utf-8"))
    digest.update(b"\0")
    digest.update(plan.logical_collection.encode("utf-8"))
    digest.update(b"\n")
    for partition in plan.partitions:
        digest.update(partition.source_kind.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(partition.root).encode("utf-8"))
        digest.update(b"\0")
        digest.update(repr(partition.root_identity).encode("ascii"))
        digest.update(b"\n")
        for source in partition.inventory:
            digest.update(str(source.path.relative_to(partition.root)).encode("utf-8"))
            digest.update(b"\0")
            digest.update(repr(source.identity).encode("ascii"))
            digest.update(b"\n")
    row_fingerprints: dict[str, str] = {}
    provisional_records = 0
    semantic_pending = False
    for source in plan.sources:
        digest.update(str(source.path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(repr(source.identity).encode("ascii"))
        digest.update(b"\n")
        try:
            built = _records_for_source(plan, source)
        except Exception as exc:
            plan.errors.append(f"{source.source_kind} {source.path}: {exc}")
            continue
        if built.skipped:
            plan.skipped_sources += 1
            continue
        plan.indexed_sources += 1
        if built.hcp:
            plan.hcp_sources += 1
            plan.hcp_records += len(built.records) or built.provisional_records
        provisional_records += built.provisional_records
        semantic_pending = semantic_pending or built.semantic_pending
        if built.hcp_fallback:
            plan.hcp_fallback_sources += 1
        for record in built.records:
            fingerprint = record.source_fingerprint()
            prior = row_fingerprints.get(record.row_id)
            if prior is not None:
                if prior != fingerprint:
                    plan.errors.append(
                        f"row id {record.row_id!r} has conflicting source payloads"
                    )
                else:
                    plan.errors.append(
                        f"row id {record.row_id!r} is duplicated by source inventory"
                    )
                continue
            row_fingerprints[record.row_id] = fingerprint
            digest.update(record.row_id.encode("utf-8"))
            digest.update(b"\0")
            digest.update(fingerprint.encode("ascii"))
            digest.update(b"\n")
    plan.planned_records = len(row_fingerprints) + provisional_records
    plan.plan_fingerprint = digest.hexdigest()
    if semantic_pending:
        plan.semantic_payload_status = "pending_exact_hcp_materialization"
        plan.record_count_status = "provisional_pending_exact_hcp_materialization"
        plan.payload_fingerprint = ""
        plan.execution_fingerprint = ""
    else:
        payload_digest = hashlib.sha256()
        for row_id in sorted(row_fingerprints):
            payload_digest.update(row_id.encode("utf-8"))
            payload_digest.update(b"\0")
            payload_digest.update(row_fingerprints[row_id].encode("ascii"))
            payload_digest.update(b"\n")
        plan.payload_fingerprint = payload_digest.hexdigest()
        plan.execution_fingerprint = plan.payload_fingerprint
    return plan


def build_knowledge_replay_plan(
    *,
    engrams_root: str | Path,
    resources_root: str | Path,
    mental_models_root: str | Path,
    msi_news_root: str | Path,
) -> SourceReplayPlan:
    """Inventory all approved knowledge partitions without opening Chroma."""
    plan = SourceReplayPlan(phase="knowledge", logical_collection="knowledge")
    configured = (
        (engrams_root, "vault Engrams", "knowledge_engram"),
        (resources_root, "vault Resources", "knowledge_resource"),
        (mental_models_root, "Ora mental models", "knowledge_mental_model"),
        (msi_news_root, "vault MSI News", "knowledge_msi_news"),
    )
    seen_paths: set[Path] = set()
    for root, label, source_kind in configured:
        try:
            partition, sources = _snapshot_source_partition(
                root, label=label, source_kind=source_kind,
            )
            plan.partitions.append(partition)
            for source in sources:
                if source.path in seen_paths:
                    plan.errors.append(
                        f"knowledge source appears in more than one partition: "
                        f"{source.path}"
                    )
                    continue
                seen_paths.add(source.path)
                plan.sources.append(source)
        except Exception as exc:
            plan.errors.append(str(exc))
    plan.sources.sort(key=lambda item: (item.source_kind, str(item.path)))
    return _finish_source_plan(plan)


def build_msi_articles_replay_plan(
    *,
    articles_root: str | Path,
    composer_path: str | Path,
    composer: Any | None = None,
) -> SourceReplayPlan:
    """Inventory MSI's canonical published articles, excluding columns."""
    plan = SourceReplayPlan(
        phase="msi-news-articles",
        logical_collection="msi_news_articles",
    )
    try:
        partition, plan.sources = _snapshot_source_partition(
            articles_root,
            label="MSI published articles",
            source_kind="msi_published_article",
        )
        plan.partitions.append(partition)
        if partition.root.name != "articles":
            raise RebuildError(
                "dedicated MSI replay root must be the published `articles` "
                f"directory, not {partition.root}"
            )
        plan.composer = composer or _load_msi_composer(composer_path)
    except Exception as exc:
        plan.errors.append(str(exc))
    return _finish_source_plan(plan)


def _iter_source_plan_records(plan: SourceReplayPlan) -> Iterator[ReplayRecord]:
    for source in plan.sources:
        built = _records_for_source(plan, source)
        yield from built.records


def _source_profile(logical_collection: str) -> dict[str, Any]:
    from orchestrator import embedding
    return {
        "provider": embedding.EMBEDDING_PROVIDER,
        "model": embedding.EMBEDDING_MODEL,
        "dimension": embedding.EMBEDDING_DIM,
        "physical_collection": embedding.resolve_collection(logical_collection),
    }


_MATERIALIZATION_SCHEMA_VERSION = 1
_HCP_EMBED_CHARS = 4000


def _canonical_json_fingerprint(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _checksummed_json(value: dict[str, Any]) -> dict[str, Any]:
    payload = dict(value)
    payload["cache_fingerprint"] = _canonical_json_fingerprint(payload)
    return payload


def _read_checksummed_json(path: Path, root: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(_read_text_snapshot(path, root, label=label))
    except Exception as exc:
        raise RebuildError(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RebuildError(f"{label} is not a JSON object: {path}")
    fingerprint = value.get("cache_fingerprint")
    unsigned = dict(value)
    unsigned.pop("cache_fingerprint", None)
    expected = _canonical_json_fingerprint(unsigned)
    if not isinstance(fingerprint, str) or fingerprint != expected:
        raise RebuildError(f"{label} checksum is invalid: {path}")
    return value


def _record_materialization_digests(
    records: Iterable[ReplayRecord],
) -> tuple[int, str, str, dict[str, tuple[str, str]]]:
    rows: dict[str, tuple[str, str]] = {}
    for record in records:
        fingerprints = (
            record.payload_fingerprint(), record.source_fingerprint(),
        )
        prior = rows.get(record.row_id)
        if prior is not None:
            qualifier = "conflicting" if prior != fingerprints else "duplicate"
            raise RebuildError(
                f"{qualifier} exact materialization id {record.row_id!r}"
            )
        rows[record.row_id] = fingerprints
    count, payload, execution = _materialization_digests_from_rows(rows)
    return count, payload, execution, rows


def _materialization_digests_from_rows(
    rows: dict[str, tuple[str, str]],
) -> tuple[int, str, str]:
    payload_digest = hashlib.sha256()
    execution_digest = hashlib.sha256()
    for row_id in sorted(rows):
        payload, execution = rows[row_id]
        for digest, fingerprint in (
            (payload_digest, payload), (execution_digest, execution),
        ):
            digest.update(row_id.encode("utf-8"))
            digest.update(b"\0")
            digest.update(fingerprint.encode("ascii"))
            digest.update(b"\n")
    return len(rows), payload_digest.hexdigest(), execution_digest.hexdigest()


def _hcp_cache_path(root: Path, source: SourceSpec) -> Path:
    key = hashlib.sha256(
        f"{source.source_kind}\0{source.path}".encode("utf-8")
    ).hexdigest()
    return root / f"{key}.json"


def _hcp_cache_binding(
    prepared: _PreparedKnowledgeSource,
    profile: dict[str, Any],
) -> dict[str, Any]:
    from orchestrator.tools import hcp, knowledge_index

    thesis = str(prepared.structural_index.document_thesis or "")
    return {
        "source_path": str(prepared.source.path),
        "source_root": str(prepared.source.root),
        "source_kind": prepared.source.source_kind,
        "source_identity": list(prepared.source.identity),
        "embedding_profile": profile,
        "semantic_algorithm": "hcp-cosine-mapped-v1",
        "semantic_input_chunk_chars": _HCP_EMBED_CHARS,
        "thesis_hash": hashlib.sha256(thesis.encode("utf-8")).hexdigest(),
        "raw_chunk_hashes": [
            hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()
            for chunk in prepared.raw_chunks
        ],
        "raw_chunk_semantic_input_hashes": [
            hashlib.sha256(
                chunk.content[:_HCP_EMBED_CHARS].encode("utf-8")
            ).hexdigest()
            for chunk in prepared.raw_chunks
        ],
        "hcp_parameters": {
            "max_chunk_tokens": knowledge_index.HCP_MAX_CHUNK_TOKENS,
            "similarity_full": hcp.SIMILARITY_FULL,
            "similarity_mid": hcp.SIMILARITY_MID,
        },
    }


def _validate_semantic_vectors(
    vectors: Any,
    *,
    labels: list[str],
    dimension: int,
) -> list[list[float]]:
    if not isinstance(vectors, (list, tuple)) or len(vectors) != len(labels):
        found = len(vectors) if isinstance(vectors, (list, tuple)) else "invalid"
        raise RebuildError(
            f"HCP embedder returned {found} vectors for {len(labels)} inputs"
        )
    out: list[list[float]] = []
    for label, vector in zip(labels, vectors):
        if not isinstance(vector, (list, tuple)) or len(vector) != dimension:
            found = len(vector) if isinstance(vector, (list, tuple)) else "invalid"
            raise RebuildError(
                f"HCP embedding dimension mismatch for {label}: expected "
                f"{dimension}, found {found}"
            )
        try:
            converted = [float(value) for value in vector]
        except (TypeError, ValueError, OverflowError) as exc:
            raise RebuildError(
                f"HCP embedding contains a non-numeric value for {label}"
            ) from exc
        if not all(math.isfinite(value) for value in converted):
            raise RebuildError(
                f"HCP embedding contains a non-finite value for {label}"
            )
        out.append(converted)
    return out


def _embed_exact_hcp_scores(
    prepared: _PreparedKnowledgeSource,
    *,
    profile: dict[str, Any],
    embedder: Callable[[list[str]], Any],
    batch_size: int,
) -> list[float]:
    from orchestrator.tools import hcp

    thesis = str(prepared.structural_index.document_thesis or "")
    if not thesis.strip():
        raise RebuildError(
            f"canonical HCP thesis is empty; exact cosine materialization is "
            f"impossible for {prepared.source.path}"
        )
    inputs = [thesis] + [
        chunk.content[:_HCP_EMBED_CHARS] for chunk in prepared.raw_chunks
    ]
    labels = [f"{prepared.source.path} thesis"] + [
        f"{prepared.source.path} raw chunk {index}"
        for index in range(1, len(prepared.raw_chunks) + 1)
    ]
    vectors: list[list[float]] = []
    for start in range(0, len(inputs), batch_size):
        current_inputs = inputs[start:start + batch_size]
        current_labels = labels[start:start + batch_size]
        try:
            embedded = embedder(current_inputs)
        except Exception as exc:
            raise RebuildError(
                f"exact HCP embedding failed for {prepared.source.path}: {exc}"
            ) from exc
        vectors.extend(_validate_semantic_vectors(
            embedded,
            labels=current_labels,
            dimension=int(profile["dimension"]),
        ))
    thesis_vector = vectors[0]
    return [
        max(0.0, min(1.0, (hcp._cosine(thesis_vector, vector) + 1.0) / 2.0))
        for vector in vectors[1:]
    ]


def _load_or_create_hcp_cache(
    prepared: _PreparedKnowledgeSource,
    *,
    cache_root: Path,
    profile: dict[str, Any],
    embedder: Callable[[list[str]], Any] | None,
    batch_size: int,
    require_existing: bool,
    required_fingerprint: str = "",
) -> tuple[list[float], str, _SourceBuild]:
    cache_path = _hcp_cache_path(cache_root, prepared.source)
    binding = _hcp_cache_binding(prepared, profile)
    if cache_path.exists():
        cache = _read_checksummed_json(
            cache_path, cache_root, label="HCP semantic materialization cache",
        )
        if cache.get("schema_version") != _MATERIALIZATION_SCHEMA_VERSION:
            raise RebuildError(f"unsupported HCP cache schema: {cache_path}")
        if cache.get("binding") != binding:
            raise RebuildError(
                f"HCP cache does not match source/profile materialization: "
                f"{prepared.source.path}"
            )
        cache_fingerprint = str(cache["cache_fingerprint"])
        if required_fingerprint and cache_fingerprint != required_fingerprint:
            raise RebuildError(
                f"HCP cache fingerprint differs from exact manifest: "
                f"{prepared.source.path}"
            )
        raw_scores = cache.get("scores")
        if not isinstance(raw_scores, list) or len(raw_scores) != len(prepared.raw_chunks):
            raise RebuildError(f"HCP cache score count is invalid: {cache_path}")
        try:
            scores = [float(value) for value in raw_scores]
        except (TypeError, ValueError) as exc:
            raise RebuildError(f"HCP cache scores are invalid: {cache_path}") from exc
        if not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in scores):
            raise RebuildError(f"HCP cache score range is invalid: {cache_path}")
        built = _knowledge_source_records(
            prepared.source, similarity_scores=scores, prepared=prepared,
        )
        count, payload, execution, _rows = _record_materialization_digests(
            built.records,
        )
        if (
            cache.get("record_count") != count
            or cache.get("payload_fingerprint") != payload
            or cache.get("execution_fingerprint") != execution
        ):
            raise RebuildError(
                f"HCP cache materialization differs from canonical replay: "
                f"{prepared.source.path}"
            )
        return scores, cache_fingerprint, built
    if require_existing:
        raise RebuildError(
            f"exact materialization manifest references a missing HCP cache: "
            f"{cache_path}"
        )
    if embedder is None:
        raise RebuildError(
            f"no active embedder available to materialize {prepared.source.path}"
        )
    scores = _embed_exact_hcp_scores(
        prepared, profile=profile, embedder=embedder, batch_size=batch_size,
    )
    built = _knowledge_source_records(
        prepared.source, similarity_scores=scores, prepared=prepared,
    )
    count, payload, execution, _rows = _record_materialization_digests(
        built.records,
    )
    from orchestrator.tools import hcp
    cache = _checksummed_json({
        "schema_version": _MATERIALIZATION_SCHEMA_VERSION,
        "binding": binding,
        "scores": scores,
        "context_levels": [hcp._levels_for_similarity(score) for score in scores],
        "record_count": count,
        "payload_fingerprint": payload,
        "execution_fingerprint": execution,
    })
    _atomic_json(cache_path, cache)
    return scores, str(cache["cache_fingerprint"]), built


def _materialization_manifest_path(target: Path, phase: str) -> Path:
    return target / f"{phase}-source-materialization.json"


def _materialize_exact_source_plan(
    plan: SourceReplayPlan,
    *,
    target: Path,
    profile: dict[str, Any],
    embedder: Callable[[list[str]], Any] | None,
    batch_size: int,
) -> _ExactSourceMaterialization:
    """Finish semantic payloads and fingerprints before Chroma is opened."""
    target.mkdir(parents=True, exist_ok=True)
    manifest_path = _materialization_manifest_path(target, plan.phase)
    existing_manifest: dict[str, Any] | None = None
    expected_caches: dict[str, str] = {}
    if manifest_path.exists():
        existing_manifest = _read_checksummed_json(
            manifest_path, target, label=f"{plan.phase} exact materialization",
        )
        if (
            existing_manifest.get("schema_version")
            != _MATERIALIZATION_SCHEMA_VERSION
            or existing_manifest.get("phase") != plan.phase
            or existing_manifest.get("logical_collection")
            != plan.logical_collection
            or existing_manifest.get("source_inventory_fingerprint")
            != plan.plan_fingerprint
            or existing_manifest.get("profile") != profile
        ):
            raise RebuildError(
                f"existing {plan.phase} materialization does not match "
                "the current source inventory/profile"
            )
        raw_caches = existing_manifest.get("hcp_caches") or {}
        if not isinstance(raw_caches, dict):
            raise RebuildError("exact materialization HCP cache map is invalid")
        expected_caches = {str(key): str(value) for key, value in raw_caches.items()}

    cache_root = target / ".ora-source-materialization" / plan.phase
    exact_rows: dict[str, tuple[str, str]] = {}
    cache_fingerprints: dict[str, str] = {}
    exact_hcp_records = 0
    for source in plan.sources:
        if plan.phase == "knowledge":
            prepared = _prepare_knowledge_source(source)
            if prepared.raw_chunks:
                source_key = str(source.path)
                _scores, fingerprint, built = _load_or_create_hcp_cache(
                    prepared,
                    cache_root=cache_root,
                    profile=profile,
                    embedder=embedder,
                    batch_size=batch_size,
                    require_existing=existing_manifest is not None,
                    required_fingerprint=expected_caches.get(source_key, ""),
                )
                if existing_manifest is not None and source_key not in expected_caches:
                    raise RebuildError(
                        f"exact manifest omits HCP source {source.path}"
                    )
                cache_fingerprints[source_key] = fingerprint
                exact_hcp_records += len(built.records)
            else:
                built = _knowledge_source_records(source, prepared=prepared)
        else:
            built = _records_for_source(plan, source)
        for record in built.records:
            fingerprints = (
                record.payload_fingerprint(), record.source_fingerprint(),
            )
            prior = exact_rows.get(record.row_id)
            if prior is not None:
                qualifier = "conflicting" if prior != fingerprints else "duplicate"
                raise RebuildError(
                    f"{qualifier} exact materialization id {record.row_id!r}"
                )
            exact_rows[record.row_id] = fingerprints

    if existing_manifest is not None and cache_fingerprints != expected_caches:
        raise RebuildError("exact materialization HCP cache inventory differs")
    count, payload, execution = _materialization_digests_from_rows(exact_rows)
    if existing_manifest is not None:
        if (
            existing_manifest.get("record_count") != count
            or existing_manifest.get("payload_fingerprint") != payload
            or existing_manifest.get("execution_fingerprint") != execution
        ):
            raise RebuildError(
                f"existing {plan.phase} exact materialization differs from sources"
            )
    else:
        manifest = _checksummed_json({
            "schema_version": _MATERIALIZATION_SCHEMA_VERSION,
            "phase": plan.phase,
            "logical_collection": plan.logical_collection,
            "source_inventory_fingerprint": plan.plan_fingerprint,
            "profile": profile,
            "record_count": count,
            "payload_fingerprint": payload,
            "execution_fingerprint": execution,
            "hcp_caches": cache_fingerprints,
        })
        _atomic_json(manifest_path, manifest)

    plan.planned_records = count
    plan.payload_fingerprint = payload
    plan.execution_fingerprint = execution
    plan.semantic_payload_status = "exact_materialized"
    plan.record_count_status = "exact"
    if plan.phase == "knowledge":
        plan.hcp_records = exact_hcp_records
    return _ExactSourceMaterialization(
        record_count=count,
        payload_fingerprint=payload,
        execution_fingerprint=execution,
        cache_fingerprints=cache_fingerprints,
    )


def _iter_materialized_source_records(
    plan: SourceReplayPlan,
    *,
    target: Path,
    profile: dict[str, Any],
    materialization: _ExactSourceMaterialization,
) -> Iterator[ReplayRecord]:
    """Replay exact payloads using cached scores; never call an embedder."""
    cache_root = target / ".ora-source-materialization" / plan.phase
    for source in plan.sources:
        if plan.phase == "knowledge":
            prepared = _prepare_knowledge_source(source)
            if prepared.raw_chunks:
                _scores, _fingerprint, built = _load_or_create_hcp_cache(
                    prepared,
                    cache_root=cache_root,
                    profile=profile,
                    embedder=None,
                    batch_size=1,
                    require_existing=True,
                    required_fingerprint=materialization.cache_fingerprints.get(
                        str(source.path), ""
                    ),
                )
            else:
                built = _knowledge_source_records(source, prepared=prepared)
        else:
            built = _records_for_source(plan, source)
        yield from built.records


def _existing_payloads(collection: Any, records: list[ReplayRecord]) -> dict[str, str]:
    result = collection.get(
        ids=[record.row_id for record in records],
        include=["documents", "metadatas"],
    )
    ids = list(result.get("ids") or [])
    documents = list(result.get("documents") or [])
    metadatas = list(result.get("metadatas") or [])
    if not (len(ids) == len(documents) == len(metadatas)):
        raise RebuildError("target returned misaligned existing payload rows")
    fingerprints: dict[str, str] = {}
    for row_id, document, metadata in zip(ids, documents, metadatas):
        fingerprints[str(row_id)] = ReplayRecord(
            row_id=str(row_id),
            document=str(document or ""),
            metadata=metadata if isinstance(metadata, dict) else {},
            source_path="",
            source_kind="target_existing",
        ).payload_fingerprint()
    return fingerprints


def _validate_stored_payloads(
    collection: Any,
    records: list[ReplayRecord],
    *,
    context: str,
) -> None:
    """Require every planned row to exist with its exact stored payload."""
    if not records:
        return
    found = _existing_payloads(collection, records)
    for record in records:
        prior = found.get(record.row_id)
        if prior is None:
            raise RebuildError(
                f"{context} is missing planned id {record.row_id!r}"
            )
        if prior != record.payload_fingerprint():
            raise RebuildError(
                f"{context} payload differs from source plan for "
                f"{record.row_id!r}"
            )


def _validate_embeddings(
    embeddings: Any,
    *,
    records: list[ReplayRecord],
    dimension: int,
) -> list[list[float]]:
    if not isinstance(embeddings, (list, tuple)):
        raise RebuildError("embedder did not return a vector list")
    if len(embeddings) != len(records):
        raise RebuildError(
            f"embedder returned {len(embeddings)} vectors for "
            f"{len(records)} records"
        )
    out: list[list[float]] = []
    for record, vector in zip(records, embeddings):
        if not isinstance(vector, (list, tuple)) or len(vector) != dimension:
            length = len(vector) if isinstance(vector, (list, tuple)) else "invalid"
            raise RebuildError(
                f"embedding dimension mismatch for {record.row_id!r}: "
                f"expected {dimension}, found {length}"
            )
        try:
            converted = [float(value) for value in vector]
        except (TypeError, ValueError) as exc:
            raise RebuildError(
                f"embedding contains a non-numeric value for {record.row_id!r}"
            ) from exc
        if not all(math.isfinite(value) for value in converted):
            raise RebuildError(
                f"embedding contains a non-finite value for {record.row_id!r}"
            )
        out.append(converted)
    return out


def execute_source_replay(
    plan: SourceReplayPlan,
    *,
    target_chromadb_path: str | Path,
    batch_size: int = 32,
    embedding_workers: int = 1,
    resume: bool = False,
    client_factory: Callable[[str], Any] | None = None,
    collection_factory: Callable[[Any, dict[str, Any]], Any] | None = None,
    embedder: Callable[[list[str]], Any] | None = None,
) -> dict[str, Any]:
    """Batch-embed and explicitly upsert one validated source plan.

    Embedding calls may run concurrently, but target reads, ordered upserts,
    checkpoint advancement, and final validation always stay on this thread.
    """
    plan.require_valid()
    if batch_size < 1:
        raise RebuildError("batch_size must be positive")
    if embedding_workers < 1:
        raise RebuildError("embedding_workers must be positive")
    target = _absolute(target_chromadb_path)
    _validate_target(target, resume=resume)
    profile = _source_profile(plan.logical_collection)
    if profile["dimension"] != 4096:
        raise RebuildError(
            "source rebuild requires the active 4096-dimensional profile; "
            f"configured dimension is {profile['dimension']}"
        )
    if embedder is None:
        from orchestrator.embedding import embed_texts
        embedder = embed_texts

    checkpoint = target / f"{plan.phase}-replay-checkpoint.json"
    materialization_path = _materialization_manifest_path(target, plan.phase)
    if checkpoint.exists() and not materialization_path.exists():
        raise RebuildError(
            f"checkpoint exists without its exact materialization manifest: "
            f"{checkpoint}"
        )

    _assert_source_inventory_unchanged(plan)

    # Exact semantic HCP payloads are materialized and atomically cached
    # before Chroma is even opened.  Every later pass regenerates from those
    # cached cosine scores, never from a lexical approximation or a new score
    # call whose threshold result could drift mid-replay.
    materialization = _materialize_exact_source_plan(
        plan,
        target=target,
        profile=profile,
        embedder=embedder,
        batch_size=batch_size,
    )
    report_path = target / f"{plan.phase}-replay-report.json"
    start_index = 0
    if checkpoint.exists():
        if not resume:
            raise RebuildError(
                f"checkpoint exists but --resume was not supplied: {checkpoint}"
            )
        state = json.loads(_read_text_snapshot(
            checkpoint, target, label=f"{plan.phase} replay checkpoint",
        ))
        if state.get("plan_fingerprint") != materialization.execution_fingerprint:
            raise RebuildError(
                "checkpoint exact materialization fingerprint does not match "
                "current sources"
            )
        if state.get("profile") != profile:
            raise RebuildError("checkpoint embedding profile does not match current config")
        start_index = int(state.get("next_index") or 0)
        if start_index < 0 or start_index > plan.planned_records:
            raise RebuildError("checkpoint next_index is outside the replay plan")
    target.mkdir(parents=True, exist_ok=True)

    if client_factory is None:
        import chromadb
        client_factory = lambda path: chromadb.PersistentClient(path=path)
    _assert_source_inventory_unchanged(plan)
    client = client_factory(str(target))
    if collection_factory is None:
        from orchestrator.embedding import get_or_create_collection
        collection_factory = lambda current_client, current_profile: (
            get_or_create_collection(
                current_client,
                plan.logical_collection,
                metadata={
                    "hnsw:space": "cosine",
                    "ora:embedding_profile": (
                        f"{current_profile['provider']}:"
                        f"{current_profile['model']}"
                    ),
                    "ora:embedding_dimension": current_profile["dimension"],
                },
            )
        )
    collection = collection_factory(client, profile)
    ordinal = 0
    batch: list[ReplayRecord] = []
    checkpoint_batch: list[ReplayRecord] = []
    embedded_records = 0
    resumed_records = start_index

    def prepare_batch(
        current: list[ReplayRecord],
    ) -> list[ReplayRecord]:
        nonlocal resumed_records
        existing = _existing_payloads(collection, current)
        missing: list[ReplayRecord] = []
        for record in current:
            prior = existing.get(record.row_id)
            if prior is None:
                missing.append(record)
                continue
            if not resume:
                raise RebuildError(
                    f"target unexpectedly already contains {record.row_id!r}"
                )
            if prior != record.payload_fingerprint():
                raise RebuildError(
                    f"existing target payload differs from source plan for "
                    f"{record.row_id!r}"
                )
            resumed_records += 1
        return missing

    def commit_batch(
        missing: list[ReplayRecord],
        next_index: int,
        raw_vectors: Any | None,
    ) -> None:
        nonlocal embedded_records
        if missing:
            vectors = _validate_embeddings(
                raw_vectors,
                records=missing,
                dimension=profile["dimension"],
            )
            collection.upsert(
                ids=[record.row_id for record in missing],
                embeddings=vectors,
                documents=[record.document for record in missing],
                metadatas=[record.metadata for record in missing],
            )
            embedded_records += len(missing)
        _atomic_json(checkpoint, {
            "schema_version": 1,
            "phase": plan.phase,
            "logical_collection": plan.logical_collection,
            "plan_fingerprint": materialization.execution_fingerprint,
            "payload_fingerprint": materialization.payload_fingerprint,
            "profile": profile,
            "next_index": next_index,
            "records": plan.planned_records,
        })

    def replay_batches() -> Iterator[tuple[list[ReplayRecord], int]]:
        nonlocal ordinal, checkpoint_batch
        for record in _iter_materialized_source_records(
            plan, target=target, profile=profile,
            materialization=materialization,
        ):
            if ordinal < start_index:
                checkpoint_batch.append(record)
                ordinal += 1
                if len(checkpoint_batch) >= 1000:
                    _validate_stored_payloads(
                        collection,
                        checkpoint_batch,
                        context=f"checkpoint-resumed {plan.phase} prefix",
                    )
                    checkpoint_batch = []
                continue
            if checkpoint_batch:
                _validate_stored_payloads(
                    collection,
                    checkpoint_batch,
                    context=f"checkpoint-resumed {plan.phase} prefix",
                )
                checkpoint_batch = []
            batch.append(record)
            ordinal += 1
            if len(batch) >= batch_size:
                yield list(batch), ordinal
                batch.clear()
        if checkpoint_batch:
            _validate_stored_payloads(
                collection,
                checkpoint_batch,
                context=f"checkpoint-resumed {plan.phase} prefix",
            )
            checkpoint_batch = []
        if batch:
            yield list(batch), ordinal
            batch.clear()

    if embedding_workers == 1:
        for current, next_index in replay_batches():
            missing = prepare_batch(current)
            raw_vectors = None
            if missing:
                raw_vectors = embedder([
                    record.embedding_text or record.document
                    for record in missing
                ])
            commit_batch(missing, next_index, raw_vectors)
    else:
        pending: deque[
            tuple[
                list[ReplayRecord],
                int,
                Future[Any] | None,
            ]
        ] = deque()
        executor = ThreadPoolExecutor(
            max_workers=embedding_workers,
            thread_name_prefix=f"ora-{plan.phase}-embed",
        )

        def finish_oldest() -> None:
            missing, next_index, future = pending.popleft()
            raw_vectors = future.result() if future is not None else None
            commit_batch(missing, next_index, raw_vectors)

        try:
            for current, next_index in replay_batches():
                missing = prepare_batch(current)
                future = None
                if missing:
                    inputs = [
                        record.embedding_text or record.document
                        for record in missing
                    ]
                    future = executor.submit(embedder, inputs)
                pending.append((missing, next_index, future))
                if len(pending) >= embedding_workers:
                    finish_oldest()
            while pending:
                finish_oldest()
        except BaseException:
            for _missing, _next_index, future in pending:
                if future is not None:
                    future.cancel()
            executor.shutdown(wait=True, cancel_futures=True)
            raise
        else:
            executor.shutdown(wait=True)
    if ordinal != plan.planned_records:
        raise RebuildError(
            f"source plan changed during execution: planned "
            f"{plan.planned_records}, generated {ordinal}"
        )

    count = int(collection.count())
    if count != plan.planned_records:
        raise RebuildError(
            f"target count mismatch: expected {plan.planned_records}, found {count}"
        )
    verify_batch: list[ReplayRecord] = []
    for record in _iter_materialized_source_records(
        plan, target=target, profile=profile,
        materialization=materialization,
    ):
        verify_batch.append(record)
        if len(verify_batch) >= 1000:
            _validate_stored_payloads(
                collection,
                verify_batch,
                context=f"final {plan.phase} validation",
            )
            verify_batch = []
    if verify_batch:
        _validate_stored_payloads(
            collection,
            verify_batch,
            context=f"final {plan.phase} validation",
        )

    report = {
        "status": "complete",
        "target_chromadb_path": str(target),
        "profile": profile,
        "plan": plan.summary(),
        "target_count": count,
        "embedded_records": embedded_records,
        "resumed_records": resumed_records,
    }
    _assert_source_inventory_unchanged(plan)
    _atomic_json(report_path, report)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="phase", required=True)

    promote = subparsers.add_parser("promote-conversations")
    promote.add_argument("--inactive-chromadb-path", required=True)
    promote.add_argument("--target-physical-collection", required=True)
    promote.add_argument("--expected-current-physical", required=True)
    promote.add_argument("--batch-size", type=int, default=128)

    rollback = subparsers.add_parser("rollback-conversations")
    rollback.add_argument("--restore-physical-collection", required=True)
    rollback.add_argument("--expected-current-physical", required=True)

    conversations = subparsers.add_parser("conversations")
    conversations.add_argument(
        "--historical-archive", default=str(rp.historical_archive_dir())
    )
    conversations.add_argument(
        "--conversations-root", default=str(rp.conversations_dir())
    )
    conversations.add_argument(
        "--manifest", default=str(Path(rp.DATA_DIR_STR) / "conversation-manifest.jsonl")
    )
    conversations.add_argument(
        "--chain-index", default=str(Path(rp.DATA_DIR_STR) / "chain-index.json")
    )
    conversations.add_argument(
        "--sessions-root", default=str(Path(rp.WORKSPACE) / "sessions")
    )
    conversations.add_argument("--target-chromadb-path", required=True)
    conversations.add_argument("--batch-size", type=int, default=32)
    conversations.add_argument("--resume", action="store_true")
    conversations.add_argument("--dry-run", action="store_true")

    knowledge = subparsers.add_parser("knowledge")
    knowledge.add_argument(
        "--engrams-root", default=str(rp.vault_dir() / "Engrams")
    )
    knowledge.add_argument(
        "--resources-root", default=str(rp.vault_dir() / "Resources")
    )
    knowledge.add_argument(
        "--mental-models-root",
        # lenses/ replaced knowledge/mental-models; the old default no longer
        # exists, so the knowledge phase aborted on its source-plan check
        # before doing anything.
        default=str(Path(rp.WORKSPACE) / "lenses"),
    )
    knowledge.add_argument(
        "--msi-news-root", default=str(rp.vault_dir() / "MSI News")
    )
    knowledge.add_argument("--target-chromadb-path", required=True)
    knowledge.add_argument("--batch-size", type=int, default=32)
    knowledge.add_argument("--embedding-workers", type=int, default=1)
    knowledge.add_argument("--resume", action="store_true")
    knowledge.add_argument("--dry-run", action="store_true")

    msi = subparsers.add_parser("msi-news-articles")
    msi.add_argument(
        "--articles-root",
        default=str(
            Path.home()
            / "sites" / "mainstreetindependent" / "src" / "content" / "articles"
        ),
    )
    msi.add_argument(
        "--composer",
        default=str(
            Path.home()
            / "sites" / "mainstreetindependent"
            / "ora-project" / "tools" / "news_index.py"
        ),
    )
    msi.add_argument("--target-chromadb-path", required=True)
    msi.add_argument("--batch-size", type=int, default=32)
    msi.add_argument("--embedding-workers", type=int, default=1)
    msi.add_argument("--resume", action="store_true")
    msi.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.phase == "promote-conversations":
        report = promote_conversation_replay(
            inactive_chromadb_path=args.inactive_chromadb_path,
            target_physical_collection=args.target_physical_collection,
            expected_current_physical=args.expected_current_physical,
            batch_size=args.batch_size,
        )
    elif args.phase == "rollback-conversations":
        report = rollback_conversation_mapping(
            restore_physical_collection=args.restore_physical_collection,
            expected_current_physical=args.expected_current_physical,
        )
    elif args.phase == "conversations":
        plan = build_conversation_replay_plan(
            historical_archive=args.historical_archive,
            conversations_root=args.conversations_root,
            manifest_path=args.manifest,
            chain_index_path=args.chain_index,
            sessions_root=args.sessions_root,
            materialize=not args.dry_run,
        )
        plan.require_valid()
        if args.dry_run:
            print(json.dumps({
                "status": "dry_run", "plan": plan.summary(),
            }, indent=2))
            return 0
        report = execute_conversation_replay(
            plan,
            target_chromadb_path=args.target_chromadb_path,
            batch_size=args.batch_size,
            resume=args.resume,
        )
    elif args.phase == "knowledge":
        _validate_target(
            _absolute(args.target_chromadb_path), resume=args.resume,
        )
        plan = build_knowledge_replay_plan(
            engrams_root=args.engrams_root,
            resources_root=args.resources_root,
            mental_models_root=args.mental_models_root,
            msi_news_root=args.msi_news_root,
        )
        plan.require_valid()
        if args.dry_run:
            print(json.dumps({
                "status": "dry_run", "plan": plan.summary(),
            }, indent=2))
            return 0
        report = execute_source_replay(
            plan,
            target_chromadb_path=args.target_chromadb_path,
            batch_size=args.batch_size,
            embedding_workers=args.embedding_workers,
            resume=args.resume,
        )
    elif args.phase == "msi-news-articles":
        _validate_target(
            _absolute(args.target_chromadb_path), resume=args.resume,
        )
        plan = build_msi_articles_replay_plan(
            articles_root=args.articles_root,
            composer_path=args.composer,
        )
        plan.require_valid()
        if args.dry_run:
            print(json.dumps({
                "status": "dry_run", "plan": plan.summary(),
            }, indent=2))
            return 0
        report = execute_source_replay(
            plan,
            target_chromadb_path=args.target_chromadb_path,
            batch_size=args.batch_size,
            embedding_workers=args.embedding_workers,
            resume=args.resume,
        )
    else:  # pragma: no cover - argparse guards
        raise RebuildError(f"unsupported rebuild phase: {args.phase}")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
