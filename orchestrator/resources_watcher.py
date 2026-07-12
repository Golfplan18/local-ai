"""Runtime watcher for the external Ora Resources inbound folder.

The source-of-truth binary stays in ``export.RESOURCES_DIR`` (normally
``~/Documents/Ora Resources``).  Supported documents are converted into a
flat Markdown reading copy under ``runtime_paths.VAULT / "Resources"`` and
then indexed through ``knowledge_index.index_single_file(force=True)`` so the
normal Hierarchical Context Protocol applies to long documents.

Why polling is justified
------------------------
Finder and Obsidian can create, rename, or copy files without calling an Ora
API.  There is therefore no in-process event at which this work can run.  A
bounded filesystem poll is the runtime execution point closest to the
external write; no daily/weekly deferred cleanup is used.  The oversight
daemon gives this watcher a dedicated lane because PDF/Office conversion and
embedding can be slow and must never delay the fast watcher heartbeats.

Safety and recovery
-------------------
Sources are opened with no-follow semantics, must be regular files whose
realpaths remain inside their configured root, and are snapshotted before a
converter sees them.  Reading copies and conformance moves use atomic,
no-overwrite creation.  An atomic manifest keyed by source path plus content
hash records every transition, making retries idempotent.  Conversion/index
failures are loud and preserve the original.  A missing original never grants
authority to delete its reading copy; it only produces a mismatch report.

Vault conformance is deliberately conservative.  Non-Markdown assets are
moved out to the external Resources folder only after two consecutive,
complete sweeps find them unreferenced.  Archive, metadata/config directories,
Obsidian canvas/base/space files, Session sidecars, and every asset referenced
from a Markdown note (including PDFs) are excluded.  If any note cannot be
read securely, no orphan counter advances during that sweep.

All interval/size values below are provisional runtime tunables pending field
calibration.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

try:
    import export as _export
    import runtime_paths as _rp
except ImportError:  # pragma: no cover - package-qualified import context
    from orchestrator import export as _export
    from orchestrator import runtime_paths as _rp


SUPPORTED_EXTENSIONS = frozenset({
    ".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm", ".rtf",
    ".txt", ".md",
})
SOURCE_FORMATS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".xlsx": "xlsx",
    ".html": "html",
    ".htm": "html",
    ".rtf": "rtf",
    ".txt": "txt",
    ".md": "md",
}
ELIGIBLE_MEDIA_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".tif",
    ".tiff", ".heic", ".avif", ".mp3", ".m4a", ".wav", ".aac",
    ".flac", ".ogg", ".opus", ".mp4", ".mov", ".m4v", ".avi", ".mkv",
    ".webm",
})

# Provisional: protects the daemon from accidentally reading a disk image or
# other misnamed giant file into memory.  Increase explicitly when needed.
MAX_SOURCE_BYTES = int(os.environ.get(
    "ORA_RESOURCES_MAX_SOURCE_BYTES", str(512 * 1024 * 1024),
))
FILE_SETTLE_SECONDS = max(0.0, float(os.environ.get(
    "ORA_RESOURCES_SETTLE_SEC", "2",
)))
ORPHAN_SWEEPS_REQUIRED = max(2, int(os.environ.get(
    "ORA_RESOURCES_ORPHAN_SWEEPS", "2",
)))

OVERSIGHT_DATA_DIR = os.path.join(_rp.DATA_DIR_STR, "oversight")
WORKSPACE = _rp.WORKSPACE
HEARTBEAT_FILE = os.path.join(
    OVERSIGHT_DATA_DIR, "resources-watcher-heartbeat.json",
)
DEFAULT_STATE_DIR = Path(_rp.RUNTIME_DATA_DIR) / "resources-watcher"

EXCLUDED_DIR_NAMES = frozenset({
    "Archive", ".git", ".obsidian", ".ora", ".space", "Sessions",
    "Session sidecars", "Old AI Working Files",
})
EXCLUDED_FILE_SUFFIXES = (
    ".space", ".base", ".canvas", ".session", ".session.json",
    ".session.yaml", ".session.yml",
)

_WIKILINK_RE = re.compile(r"!?\[\[([^\]\n]+)\]\]")
_MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date_values() -> tuple[str, str]:
    # Vault-facing dates follow the user's local calendar; audit timestamps
    # remain UTC via _now_iso().
    now = datetime.now()
    canonical = now.strftime("%Y-%m-%d")
    return canonical, canonical


def _write_heartbeat() -> None:
    os.makedirs(OVERSIGHT_DATA_DIR, exist_ok=True)
    _rp.atomic_write_text(
        HEARTBEAT_FILE,
        json.dumps({"watcher": "resources_watcher", "beat_at": _now_iso()}),
    )


def _validated_root(path: str | Path, *, create: bool) -> Path:
    """Return an absolute regular directory while refusing a root symlink."""
    root = Path(path).expanduser().absolute()
    if create:
        root.mkdir(parents=True, exist_ok=True)
    if not root.exists():
        raise FileNotFoundError(f"resources root does not exist: {root}")
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"resources root must be a non-symlink directory: {root}")
    return root


def _inside(path: str | Path, root: str | Path) -> bool:
    return _rp.within_base(Path(path).resolve(strict=False), Path(root).resolve())


def _state_paths(state_dir: str | Path | None) -> tuple[Path, Path]:
    state = _validated_root(state_dir or DEFAULT_STATE_DIR, create=True)
    return state / "manifest.json", state / "audit.jsonl"


def _empty_manifest() -> dict[str, Any]:
    return {
        "version": 1,
        "sweep_sequence": 0,
        "entries": {},
        "orphan_candidates": {},
        "updated_at": _now_iso(),
    }


def _load_manifest(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError(f"manifest is a symlink: {path}")
    if not path.exists():
        return _empty_manifest()
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError(f"unsupported resources watcher manifest: {path}")
    if not isinstance(value.get("entries"), dict):
        raise ValueError(f"invalid resources watcher entries: {path}")
    if not isinstance(value.get("orphan_candidates"), dict):
        raise ValueError(f"invalid orphan candidate state: {path}")
    value.setdefault("sweep_sequence", 0)
    return value


def _save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = _now_iso()
    _rp.atomic_write_text(
        path,
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def _emit_audit(audit_path: Path, event_type: str, **fields: Any) -> None:
    record = {"event_type": event_type, "timestamp": _now_iso(), **fields}
    line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    _rp.append_bytes_no_follow(audit_path, line.encode("utf-8"))
    try:
        try:
            from oversight_events import emit
        except ImportError:  # pragma: no cover
            from orchestrator.oversight_events import emit
        # The normal oversight event log is the source for the generated Daily
        # Note's Ora activity digest.  No approval queue or policy action is
        # introduced; unknown watcher event types remain audit-only.
        emit(record)
    except Exception as exc:
        print(f"[resources_watcher] audit bus failed for {event_type}: {exc}")


def _log_failure(
    summary: dict[str, Any], audit_path: Path, event_type: str, message: str,
    **fields: Any,
) -> None:
    summary["errors"].append(message)
    print(f"[resources_watcher] ERROR: {message}")
    _emit_audit(audit_path, event_type, error=message, **fields)


def _manifest_key(source_path: str, content_hash: str) -> str:
    identity = f"{os.path.normcase(source_path)}\0{content_hash}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _secure_snapshot(
    source: Path, root: Path, state_dir: Path,
) -> tuple[Path, str, os.stat_result]:
    """Copy a stable, no-follow source fd to an owned conversion snapshot."""
    lexical = source.absolute()
    before_lstat = os.lstat(lexical)
    if stat.S_ISLNK(before_lstat.st_mode):
        raise ValueError("source is a symlink")
    if not stat.S_ISREG(before_lstat.st_mode):
        raise ValueError("source is not a regular file")
    resolved = lexical.resolve(strict=True)
    if not _inside(resolved, root):
        raise ValueError("source realpath escapes the inbound root")
    if before_lstat.st_size > MAX_SOURCE_BYTES:
        raise ValueError(
            f"source exceeds provisional {MAX_SOURCE_BYTES}-byte limit",
        )

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(lexical, flags)
    temporary_fd = -1
    temporary_name = ""
    digest = hashlib.sha256()
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError("opened source is not a regular file")
        if (opened.st_dev, opened.st_ino) != (
            before_lstat.st_dev, before_lstat.st_ino,
        ):
            raise ValueError("source changed while it was being opened")
        temporary_fd, temporary_name = tempfile.mkstemp(
            prefix="source-", suffix=source.suffix.lower(), dir=str(state_dir),
        )
        copied = 0
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            copied += len(block)
            if copied > MAX_SOURCE_BYTES:
                raise ValueError(
                    f"source exceeds provisional {MAX_SOURCE_BYTES}-byte limit",
                )
            digest.update(block)
            view = memoryview(block)
            while view:
                written = os.write(temporary_fd, view)
                view = view[written:]
        os.fsync(temporary_fd)
        after = os.fstat(fd)
        if (after.st_size, after.st_mtime_ns) != (
            opened.st_size, opened.st_mtime_ns,
        ):
            raise ValueError("source changed during snapshot")
    except Exception:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
        raise
    finally:
        os.close(fd)
        if temporary_fd >= 0:
            os.close(temporary_fd)
    return Path(temporary_name), digest.hexdigest(), before_lstat


def _convert_snapshot(snapshot: Path) -> str:
    try:
        from orchestrator.tools.format_convert import convert_to_markdown
    except ImportError:  # pragma: no cover
        from tools.format_convert import convert_to_markdown
    result = convert_to_markdown(str(snapshot))
    if not result or not result.strip():
        raise ValueError(
            "conversion returned no readable text (possibly a scanned document)",
        )
    return result.strip()


def _safe_stem(value: str) -> str:
    clean = _CONTROL_RE.sub(" ", value).replace("/", " ").replace("\\", " ")
    clean = re.sub(r"\s+", " ", clean).strip(" .")
    return (clean or "Resource")[:120].rstrip(" .") or "Resource"


def _candidate_reading_path(
    resources_dir: Path, source: Path, source_format: str, content_hash: str,
) -> Path:
    stem = _safe_stem(source.stem)
    first = resources_dir / f"{stem}.md"
    if not first.exists() and not first.is_symlink():
        return first
    base = f"{stem} — {source_format}-{content_hash[:8]}"
    candidate = resources_dir / f"{base}.md"
    number = 2
    while candidate.exists() or candidate.is_symlink():
        candidate = resources_dir / f"{base}-{number}.md"
        number += 1
    return candidate


def _reading_copy_text(
    target: Path,
    source: Path,
    source_format: str,
    converted: str,
    *,
    processed_date: str,
    yaml_date: str,
) -> str:
    # JSON strings are valid YAML scalars and safely quote colons, quotes, and
    # non-ASCII source names without hand-rolled escaping.
    return (
        "---\n"
        "nexus:\n"
        "type: resource\n"
        "tags:\n"
        f"source_file: {json.dumps(source.name, ensure_ascii=False)}\n"
        f"source_format: {source_format}\n"
        f"source_path: {json.dumps(str(source), ensure_ascii=False)}\n"
        f"processed_date: {processed_date}\n"
        f"date created: {yaml_date}\n"
        f"date modified: {yaml_date}\n"
        "---\n\n"
        f"# {target.stem}\n\n"
        f"{converted.rstrip()}\n"
    )


def _atomic_create_text(path: Path, text: str) -> None:
    """Atomically create ``path`` and fail if anything already owns it."""
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise ValueError(f"reading-copy parent is unsafe: {path.parent}")
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent),
    )
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            fd = -1
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        # Hard-linking the complete temp inode is atomic and, unlike replace,
        # refuses an existing destination.  The temp and target share a parent,
        # so they are necessarily on the same filesystem.
        os.link(temporary, path, follow_symlinks=False)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError("not a regular file")
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            digest.update(block)
    finally:
        os.close(fd)
    return digest.hexdigest()


def _valid_managed_copy(
    path: Path, resources_dir: Path, expected_hash: str | None = None,
) -> bool:
    try:
        mode = os.lstat(path).st_mode
    except OSError:
        return False
    structurally_valid = (
        stat.S_ISREG(mode)
        and not stat.S_ISLNK(mode)
        and path.parent == resources_dir
        and _inside(path, resources_dir)
    )
    if not structurally_valid:
        return False
    if expected_hash is not None:
        if not expected_hash:
            return False
        try:
            return _file_hash(path) == expected_hash
        except OSError:
            return False
    return True


def _index_reading_copy(
    path: Path,
    chromadb_path: str | os.PathLike[str] | None = None,
) -> dict[str, int]:
    try:
        from orchestrator.tools.knowledge_index import index_single_file
    except ImportError:  # pragma: no cover
        from tools.knowledge_index import index_single_file
    resolved_chromadb_path = (
        chromadb_path if chromadb_path is not None else _rp.chromadb_dir()
    )
    result = index_single_file(
        str(path), force=True, chromadb_path=resolved_chromadb_path,
    )
    if not isinstance(result, dict) or result.get("errors") or not result.get("indexed"):
        raise RuntimeError(f"knowledge index did not index reading copy: {result!r}")
    return result


def _settled(path: Path, settle_seconds: float, *, now: float | None = None) -> bool:
    if settle_seconds <= 0:
        return True
    observed = time.time() if now is None else now
    return observed - os.lstat(path).st_mtime >= settle_seconds


def _walk_inbound(
    root: Path, settle_seconds: float = FILE_SETTLE_SECONDS,
) -> tuple[list[Path], list[tuple[Path, str]], list[Path]]:
    supported: list[Path] = []
    rejected: list[tuple[Path, str]] = []
    settling: list[Path] = []
    for current, dirs, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        safe_dirs: list[str] = []
        for name in dirs:
            candidate = current_path / name
            if name.startswith("."):
                continue
            try:
                mode = os.lstat(candidate).st_mode
                if stat.S_ISLNK(mode):
                    rejected.append((candidate, "directory is a symlink"))
                elif not stat.S_ISDIR(mode):
                    rejected.append((candidate, "directory entry is special"))
                elif not _inside(candidate, root):
                    rejected.append((candidate, "directory escapes inbound root"))
                else:
                    safe_dirs.append(name)
            except OSError as exc:
                rejected.append((candidate, f"cannot inspect directory: {exc}"))
        dirs[:] = safe_dirs
        for name in files:
            candidate = current_path / name
            try:
                mode = os.lstat(candidate).st_mode
            except OSError as exc:
                rejected.append((candidate, f"cannot inspect source: {exc}"))
                continue
            if stat.S_ISLNK(mode):
                rejected.append((candidate, "source is a symlink"))
            elif not stat.S_ISREG(mode):
                rejected.append((candidate, "source is not a regular file"))
            elif candidate.suffix.lower() in SUPPORTED_EXTENSIONS:
                if _settled(candidate, settle_seconds):
                    supported.append(candidate)
                else:
                    settling.append(candidate)
            elif candidate.suffix.lower() in ELIGIBLE_MEDIA_EXTENSIONS:
                # External media is already in its canonical preserved home;
                # the watcher converts documents only.
                continue
            elif not candidate.name.startswith("."):
                rejected.append((
                    candidate,
                    f"unsupported inbound format: {candidate.suffix.lower() or '(none)'}",
                ))
    return sorted(supported), rejected, sorted(settling)


def _process_source(
    source: Path,
    inbound_root: Path,
    resources_dir: Path,
    state_dir: Path,
    manifest_path: Path,
    audit_path: Path,
    manifest: dict[str, Any],
    summary: dict[str, Any],
    chromadb_path: str | os.PathLike[str] | None = None,
) -> str | None:
    snapshot: Path | None = None
    try:
        snapshot, content_hash, _source_stat = _secure_snapshot(
            source, inbound_root, state_dir,
        )
        canonical_source = str(source.resolve(strict=True))
        key = _manifest_key(canonical_source, content_hash)
        entries = manifest["entries"]
        entry = entries.get(key)
        if entry and entry.get("status") == "complete":
            reading = Path(str(entry.get("reading_copy", "")))
            if _valid_managed_copy(
                reading, resources_dir, str(entry.get("reading_copy_hash", "")),
            ):
                summary["unchanged"] += 1
                return canonical_source
            entry["status"] = "reading_copy_missing"
            entry["error"] = "managed reading copy is missing or unsafe"
            _save_manifest(manifest_path, manifest)
            _log_failure(
                summary, audit_path, "ResourceReadingCopyMismatch",
                f"reading copy missing/unsafe for {canonical_source}: {reading}",
                source_path=canonical_source, reading_copy=str(reading),
            )

        # An indexing failure happens after the reading copy is durably
        # written.  If that exact persisted copy still exists, retry indexing
        # it directly.  Re-rendering is both unnecessary and unsafe: a retry
        # after midnight would change the YAML dates/hash and allocate a second
        # collision-safe filename for the same source content.
        if entry and entry.get("status") in {"written", "failed"}:
            reading = Path(str(entry.get("reading_copy", "")))
            expected_hash = str(entry.get("reading_copy_hash", ""))
            if _valid_managed_copy(reading, resources_dir, expected_hash):
                entry["attempts"] = int(entry.get("attempts", 0)) + 1
                entry["last_attempt_at"] = _now_iso()
                entry["status"] = "indexing"
                entry.pop("error", None)
                _save_manifest(manifest_path, manifest)
                index_stats = _index_reading_copy(reading, chromadb_path)
                entry["status"] = "complete"
                entry["indexed_at"] = _now_iso()
                entry["index_stats"] = index_stats
                _save_manifest(manifest_path, manifest)
                summary["processed"] += 1
                _emit_audit(
                    audit_path,
                    "ResourceIngested",
                    source_path=canonical_source,
                    source_format=str(entry.get("source_format", "")),
                    reading_copy=str(reading),
                    content_hash=content_hash,
                )
                return canonical_source

        if entry is None:
            processed_date, yaml_date = _date_values()
            entry = {
                "source_path": canonical_source,
                "source_file": source.name,
                "source_format": SOURCE_FORMATS[source.suffix.lower()],
                "content_hash": content_hash,
                "status": "discovered",
                "discovered_at": _now_iso(),
                "attempts": 0,
                # Persist the user-facing render date independently of retry
                # time so a cross-date resume regenerates identical bytes.
                "processed_date": processed_date,
                "yaml_date": yaml_date,
            }
            entries[key] = entry
            _save_manifest(manifest_path, manifest)
        elif not entry.get("processed_date") or not entry.get("yaml_date"):
            processed_date, yaml_date = _date_values()
            entry["processed_date"] = processed_date
            entry["yaml_date"] = yaml_date
            _save_manifest(manifest_path, manifest)

        entry["attempts"] = int(entry.get("attempts", 0)) + 1
        entry["last_attempt_at"] = _now_iso()
        entry["status"] = "converting"
        entry.pop("error", None)
        _save_manifest(manifest_path, manifest)

        converted = _convert_snapshot(snapshot)
        source_format = SOURCE_FORMATS[source.suffix.lower()]
        planned = Path(str(entry.get("reading_copy", ""))) if entry.get("reading_copy") else None
        if (
            planned is None
            or planned.parent != resources_dir
            or not _inside(planned, resources_dir)
        ):
            planned = _candidate_reading_path(
                resources_dir, source, source_format, content_hash,
            )
            entry["reading_copy"] = str(planned)
        entry["status"] = "converted"
        _save_manifest(manifest_path, manifest)

        text = _reading_copy_text(
            planned,
            Path(canonical_source),
            source_format,
            converted,
            processed_date=str(entry["processed_date"]),
            yaml_date=str(entry["yaml_date"]),
        )
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        existing_matches = _valid_managed_copy(
            planned, resources_dir, text_hash,
        )
        if not existing_matches:
            # A non-matching existing file is never assumed to be watcher-owned,
            # even if a pre-write crash left this path in the manifest.
            if planned.exists() or planned.is_symlink():
                planned = _candidate_reading_path(
                    resources_dir, source, source_format, content_hash,
                )
                entry["reading_copy"] = str(planned)
                _save_manifest(manifest_path, manifest)
                text = _reading_copy_text(
                    planned,
                    Path(canonical_source),
                    source_format,
                    converted,
                    processed_date=str(entry["processed_date"]),
                    yaml_date=str(entry["yaml_date"]),
                )
                text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            entry["status"] = "rendered"
            entry["reading_copy_hash"] = text_hash
            entry["rendered_at"] = _now_iso()
            _save_manifest(manifest_path, manifest)
            try:
                _atomic_create_text(planned, text)
            except FileExistsError:
                # A user or another process claimed the planned path.  Never
                # overwrite it; select a fresh collision-safe name and persist
                # that plan before retrying the create.
                planned = _candidate_reading_path(
                    resources_dir, source, source_format, content_hash,
                )
                entry["reading_copy"] = str(planned)
                _save_manifest(manifest_path, manifest)
                text = _reading_copy_text(
                    planned,
                    Path(canonical_source),
                    source_format,
                    converted,
                    processed_date=str(entry["processed_date"]),
                    yaml_date=str(entry["yaml_date"]),
                )
                text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                entry["status"] = "rendered"
                entry["reading_copy_hash"] = text_hash
                entry["rendered_at"] = _now_iso()
                _save_manifest(manifest_path, manifest)
                _atomic_create_text(planned, text)

        entry["status"] = "written"
        entry["written_at"] = _now_iso()
        entry["reading_copy_hash"] = text_hash
        _save_manifest(manifest_path, manifest)

        index_stats = _index_reading_copy(planned, chromadb_path)
        entry["status"] = "complete"
        entry["indexed_at"] = _now_iso()
        entry["index_stats"] = index_stats
        entry.pop("error", None)
        _save_manifest(manifest_path, manifest)
        summary["processed"] += 1
        _emit_audit(
            audit_path,
            "ResourceIngested",
            source_path=canonical_source,
            source_format=source_format,
            reading_copy=str(planned),
            content_hash=content_hash,
        )
        return canonical_source
    except Exception as exc:
        canonical_source = str(source.absolute())
        message = f"failed to process {canonical_source}: {exc}"
        # If snapshot/hash succeeded, retain the failed transition for a
        # resumable retry.  Conversion failures happen before a new reading
        # copy is created; indexing failures retain the already-written copy.
        try:
            if "key" in locals() and key in manifest["entries"]:
                failed = manifest["entries"][key]
                failed["status"] = "failed"
                failed["error"] = str(exc)
                failed["failed_at"] = _now_iso()
                _save_manifest(manifest_path, manifest)
        except Exception as manifest_exc:
            message += f"; manifest update also failed: {manifest_exc}"
        _log_failure(
            summary, audit_path, "ResourceIngestFailed", message,
            source_path=canonical_source,
        )
        return canonical_source if source.exists() else None
    finally:
        if snapshot is not None:
            try:
                snapshot.unlink()
            except OSError:
                pass


def _excluded_dir(name: str) -> bool:
    return name.startswith(".") or name in EXCLUDED_DIR_NAMES


def _excluded_file(path: Path) -> bool:
    lower = path.name.lower()
    return (
        lower.startswith(".")
        or any(lower.endswith(suffix) for suffix in EXCLUDED_FILE_SUFFIXES)
    )


def _link_target(raw: str) -> str | None:
    value = unquote(raw.strip()).strip("<>")
    # Obsidian aliases and block/heading fragments are not filesystem parts.
    value = value.split("|", 1)[0].split("#", 1)[0].strip()
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        return None
    return parsed.path.replace("\\", "/")


def _references_in_note(
    note: Path, vault_root: Path,
) -> tuple[set[str], set[str]]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(note, flags)
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError("note is not a regular file")
        with os.fdopen(fd, "r", encoding="utf-8", errors="strict") as stream:
            fd = -1
            text = stream.read()
    finally:
        if fd >= 0:
            os.close(fd)

    absolute: set[str] = set()
    basenames: set[str] = set()
    raw_targets = [m.group(1) for m in _WIKILINK_RE.finditer(text)]
    raw_targets.extend(m.group(1) for m in _MARKDOWN_LINK_RE.finditer(text))
    for raw in raw_targets:
        target = _link_target(raw)
        if not target or Path(target).suffix.lower() in {"", ".md"}:
            continue
        basenames.add(os.path.normcase(Path(target).name))
        candidate = Path(target)
        if candidate.is_absolute():
            resolved = candidate.resolve(strict=False)
        else:
            resolved = (note.parent / candidate).resolve(strict=False)
        if _inside(resolved, vault_root):
            absolute.add(os.path.normcase(str(resolved)))
        # Vault-root-relative links are also common in Obsidian.
        root_relative = (vault_root / target.lstrip("/")).resolve(strict=False)
        if _inside(root_relative, vault_root):
            absolute.add(os.path.normcase(str(root_relative)))
    return absolute, basenames


def _scan_vault_assets(
    vault_root: Path,
) -> tuple[list[Path], set[str], set[str], list[str]]:
    assets: list[Path] = []
    referenced_paths: set[str] = set()
    referenced_names: set[str] = set()
    errors: list[str] = []
    notes: list[Path] = []

    for current, dirs, files in os.walk(vault_root, followlinks=False):
        current_path = Path(current)
        safe_dirs: list[str] = []
        for name in dirs:
            candidate = current_path / name
            if _excluded_dir(name):
                continue
            try:
                mode = os.lstat(candidate).st_mode
                if stat.S_ISLNK(mode):
                    errors.append(f"vault directory is a symlink: {candidate}")
                elif not stat.S_ISDIR(mode) or not _inside(candidate, vault_root):
                    errors.append(f"vault directory is unsafe: {candidate}")
                else:
                    safe_dirs.append(name)
            except OSError as exc:
                errors.append(f"cannot inspect vault directory {candidate}: {exc}")
        dirs[:] = safe_dirs

        for name in files:
            path = current_path / name
            if _excluded_file(path):
                continue
            try:
                mode = os.lstat(path).st_mode
            except OSError as exc:
                errors.append(f"cannot inspect vault file {path}: {exc}")
                continue
            if stat.S_ISLNK(mode):
                errors.append(f"vault file is a symlink: {path}")
                continue
            if not stat.S_ISREG(mode) or not _inside(path, vault_root):
                errors.append(f"vault file is special or escaped: {path}")
                continue
            if path.suffix.lower() == ".md":
                notes.append(path)
            else:
                assets.append(path)

    for note in notes:
        try:
            paths, names = _references_in_note(note, vault_root)
            referenced_paths.update(paths)
            referenced_names.update(names)
        except Exception as exc:
            errors.append(f"cannot securely read note {note}: {exc}")
    return sorted(assets), referenced_paths, referenced_names, errors


def _orphan_destination(inbound_root: Path, source: Path, content_hash: str) -> Path:
    first = inbound_root / source.name
    if not first.exists() and not first.is_symlink():
        return first
    stem = _safe_stem(source.stem)
    suffix = source.suffix
    base = f"{stem} — orphan-{content_hash[:8]}"
    candidate = inbound_root / f"{base}{suffix}"
    number = 2
    while candidate.exists() or candidate.is_symlink():
        candidate = inbound_root / f"{base}-{number}{suffix}"
        number += 1
    return candidate


def _move_orphan_no_overwrite(
    source: Path, vault_root: Path, inbound_root: Path, state_dir: Path,
) -> tuple[Path, str]:
    snapshot, content_hash, before = _secure_snapshot(source, vault_root, state_dir)
    destination = _orphan_destination(inbound_root, source, content_hash)
    destination_created = False
    try:
        fd = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0),
            0o600,
        )
        destination_created = True
        try:
            with snapshot.open("rb") as stream:
                while True:
                    block = stream.read(1024 * 1024)
                    if not block:
                        break
                    view = memoryview(block)
                    while view:
                        written = os.write(fd, view)
                        view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        current = os.lstat(source)
        if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
        ):
            destination.unlink()
            raise ValueError("orphan source changed during move")
        source.unlink()
        return destination, content_hash
    except Exception:
        # A failed copy never authorizes deleting the source.  Remove only the
        # destination this invocation created.
        if destination_created and destination.exists() and source.exists():
            try:
                destination.unlink()
            except OSError:
                pass
        raise
    finally:
        try:
            snapshot.unlink()
        except OSError:
            pass


def _media_observation_identity(path: Path) -> dict[str, int]:
    """Stable identity for consecutive orphan-media observations.

    The conformance census must remain read-only, so it does not snapshot/hash
    every media file merely to count observations.  Device, inode, size, and
    nanosecond mtime provide the approved stable identity: replacing or
    rewriting bytes at the same path resets the count.  The eventual move still
    takes a secure no-follow snapshot and computes a content hash before acting.
    """
    observed = os.lstat(path)
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
        raise ValueError("media observation is not a regular no-follow file")
    return {
        "device": int(observed.st_dev),
        "inode": int(observed.st_ino),
        "size": int(observed.st_size),
        "mtime_ns": int(observed.st_mtime_ns),
    }


def _run_conformance(
    vault_root: Path,
    inbound_root: Path,
    state_dir: Path,
    manifest_path: Path,
    audit_path: Path,
    manifest: dict[str, Any],
    summary: dict[str, Any],
    settle_seconds: float = FILE_SETTLE_SECONDS,
) -> None:
    assets, referenced_paths, referenced_names, scan_errors = _scan_vault_assets(
        vault_root,
    )
    if scan_errors:
        for error in scan_errors:
            _log_failure(
                summary, audit_path, "ResourceConformanceScanFailed", error,
            )
        summary["conformance_complete"] = False
        return

    manifest["sweep_sequence"] = int(manifest.get("sweep_sequence", 0)) + 1
    sequence = manifest["sweep_sequence"]
    candidates = manifest["orphan_candidates"]
    current_keys: set[str] = set()

    for asset in assets:
        suffix = asset.suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS and suffix not in ELIGIBLE_MEDIA_EXTENSIONS:
            # JSON, archived-markdown sidecars, databases, and other unknown
            # files are outside this watcher's authority.  They are reported
            # nowhere and left exactly where the user put them.
            continue
        if not _settled(asset, settle_seconds):
            summary["settling"] += 1
            continue
        resolved_key = os.path.normcase(str(asset.resolve(strict=True)))
        if (
            resolved_key in referenced_paths
            or os.path.normcase(asset.name) in referenced_names
        ):
            candidates.pop(resolved_key, None)
            summary["referenced_assets"] += 1
            continue
        is_document = suffix in SUPPORTED_EXTENSIONS
        if is_document:
            count = ORPHAN_SWEEPS_REQUIRED
        else:
            current_keys.add(resolved_key)
            prior = candidates.get(resolved_key, {})
            prior_sequence = int(prior.get("last_seen_sequence", -1))
            try:
                identity = _media_observation_identity(asset)
            except Exception as exc:
                _log_failure(
                    summary,
                    audit_path,
                    "ResourceConformanceScanFailed",
                    f"cannot identify orphan-media observation {asset}: {exc}",
                    source_path=str(asset),
                )
                continue
            count = int(prior.get("consecutive_sweeps", 0)) + 1 if (
                prior_sequence == sequence - 1
                and prior.get("identity") == identity
            ) else 1
            candidates[resolved_key] = {
                "path": str(asset),
                "identity": identity,
                "consecutive_sweeps": count,
                "last_seen_sequence": sequence,
                "last_seen_at": _now_iso(),
            }
            summary["orphan_candidates"] += 1
        if count < ORPHAN_SWEEPS_REQUIRED:
            continue
        try:
            destination, content_hash = _move_orphan_no_overwrite(
                asset, vault_root, inbound_root, state_dir,
            )
            candidates.pop(resolved_key, None)
            summary["orphans_moved"] += 1
            _emit_audit(
                audit_path,
                "ResourceOrphanMoved",
                source_path=str(asset),
                destination_path=str(destination),
                content_hash=content_hash,
                consecutive_sweeps=count,
                asset_class="document" if is_document else "media",
            )
        except Exception as exc:
            _log_failure(
                summary,
                audit_path,
                "ResourceOrphanMoveFailed",
                f"failed to move orphan {asset}: {exc}",
                source_path=str(asset),
            )

    # A candidate absent from this complete sweep was moved/deleted/referenced;
    # retaining its count would make a later reappearance non-consecutive.
    for key in list(candidates):
        if key not in current_keys:
            candidates.pop(key, None)
    _save_manifest(manifest_path, manifest)


def _report_missing_sources(
    manifest: dict[str, Any],
    manifest_path: Path,
    audit_path: Path,
    seen_sources: set[str],
    summary: dict[str, Any],
) -> None:
    changed = False
    for entry in manifest["entries"].values():
        source = str(entry.get("source_path", ""))
        if not source or source in seen_sources:
            continue
        try:
            exists = Path(source).exists() or Path(source).is_symlink()
        except OSError:
            exists = False
        if exists:
            continue
        summary["source_mismatches"] += 1
        reading_copy = str(entry.get("reading_copy", ""))
        print(
            "[resources_watcher] MISMATCH: original missing; preserving "
            f"reading copy: {source} -> {reading_copy or '(none)'}",
        )
        if not entry.get("source_missing_reported_at"):
            entry["source_missing_reported_at"] = _now_iso()
            changed = True
            _emit_audit(
                audit_path,
                "ResourceSourceMissing",
                source_path=source,
                reading_copy=reading_copy,
                action="reported_only",
            )
    if changed:
        _save_manifest(manifest_path, manifest)


def sweep(
    *,
    inbound_root: str | Path | None = None,
    vault_root: str | Path | None = None,
    state_dir: str | Path | None = None,
    chromadb_path: str | os.PathLike[str] | None = None,
    settle_seconds: float = FILE_SETTLE_SECONDS,
) -> dict[str, Any]:
    """Run one conformance + inbound pass and return a structured summary."""
    summary: dict[str, Any] = {
        "processed": 0,
        "unchanged": 0,
        "rejected": 0,
        "referenced_assets": 0,
        "orphan_candidates": 0,
        "orphans_moved": 0,
        "source_mismatches": 0,
        "settling": 0,
        "skipped": None,
        "conformance_complete": True,
        "errors": [],
    }
    try:
        vault_candidate = Path(
            vault_root if vault_root is not None else _rp.vault_dir()
        ).expanduser().absolute()
        if not vault_candidate.exists():
            summary["skipped"] = "vault_unavailable"
            return summary
        vault = _validated_root(vault_candidate, create=False)
        inbound = _validated_root(
            inbound_root if inbound_root is not None
            else _export.current_resources_dir(),
            create=True,
        )
        if _inside(inbound, vault) or _inside(vault, inbound):
            raise ValueError("inbound and vault roots must not overlap")
        resources = _validated_root(vault / "Resources", create=True)
        manifest_path, audit_path = _state_paths(state_dir)
        state = manifest_path.parent
        with _rp.locked_file(manifest_path):
            manifest = _load_manifest(manifest_path)
            # Move confirmed vault orphans first so supported assets can be
            # converted during this same runtime pass.
            _run_conformance(
                vault, inbound, state, manifest_path, audit_path, manifest, summary,
                settle_seconds,
            )
            sources, rejected, settling = _walk_inbound(inbound, settle_seconds)
            summary["settling"] += len(settling)
            for path, reason in rejected:
                summary["rejected"] += 1
                _log_failure(
                    summary,
                    audit_path,
                    "ResourceInboundRejected",
                    f"rejected inbound entry {path}: {reason}",
                    source_path=str(path),
                )
            seen_sources: set[str] = set()
            for source in sources:
                seen = _process_source(
                    source,
                    inbound,
                    resources,
                    state,
                    manifest_path,
                    audit_path,
                    manifest,
                    summary,
                    chromadb_path,
                )
                if seen:
                    seen_sources.add(seen)
            _report_missing_sources(
                manifest, manifest_path, audit_path, seen_sources, summary,
            )
            _save_manifest(manifest_path, manifest)
    except Exception as exc:
        message = f"watcher sweep failed open: {exc}"
        summary["errors"].append(message)
        print(f"[resources_watcher] ERROR: {message}")
    finally:
        try:
            _write_heartbeat()
        except Exception as exc:
            summary["errors"].append(f"heartbeat failed: {exc}")
            print(f"[resources_watcher] ERROR: heartbeat failed: {exc}")
    return summary


def preview(
    *,
    inbound_root: str | Path | None = None,
    vault_root: str | Path | None = None,
    state_dir: str | Path | None = None,
    settle_seconds: float = FILE_SETTLE_SECONDS,
) -> dict[str, Any]:
    """Read-only one-shot preview for live conformance review.

    No roots, manifests, reading copies, audit records, heartbeats, or orphan
    files are created or changed.  ``would_move`` means this complete scan
    would satisfy the two-consecutive-sweep threshold given the current
    manifest. Documents are eligible immediately; media requires the approved
    two consecutive complete sweeps.
    """
    result: dict[str, Any] = {
        "dry_run": True,
        "supported_inbound": [],
        "rejected_inbound": [],
        "settling_inbound": [],
        "referenced_assets": [],
        "media_first_seen": [],
        "would_move_media": [],
        "would_move_documents": [],
        "settling_assets": [],
        "skipped": None,
        "errors": [],
    }
    try:
        vault_candidate = Path(
            vault_root if vault_root is not None else _rp.vault_dir()
        ).expanduser().absolute()
        if not vault_candidate.exists():
            result["skipped"] = "vault_unavailable"
            return result
        vault = _validated_root(vault_candidate, create=False)
        inbound = _validated_root(
            inbound_root if inbound_root is not None
            else _export.current_resources_dir(),
            create=False,
        )
        if _inside(inbound, vault) or _inside(vault, inbound):
            raise ValueError("inbound and vault roots must not overlap")
        sources, rejected, settling = _walk_inbound(inbound, settle_seconds)
        result["supported_inbound"] = [str(path) for path in sources]
        result["settling_inbound"] = [str(path) for path in settling]
        result["rejected_inbound"] = [
            {"path": str(path), "reason": reason} for path, reason in rejected
        ]
        assets, ref_paths, ref_names, scan_errors = _scan_vault_assets(vault)
        result["errors"].extend(scan_errors)
        if scan_errors:
            return result

        manifest = _empty_manifest()
        if state_dir is not None:
            manifest_path = Path(state_dir).expanduser().absolute() / "manifest.json"
        else:
            manifest_path = DEFAULT_STATE_DIR / "manifest.json"
        if manifest_path.exists() and not manifest_path.is_symlink():
            manifest = _load_manifest(manifest_path)
        prior_candidates = manifest.get("orphan_candidates", {})
        prior_sequence = int(manifest.get("sweep_sequence", 0))
        for asset in assets:
            suffix = asset.suffix.lower()
            if suffix not in SUPPORTED_EXTENSIONS and suffix not in ELIGIBLE_MEDIA_EXTENSIONS:
                continue
            if not _settled(asset, settle_seconds):
                result["settling_assets"].append(str(asset))
                continue
            key = os.path.normcase(str(asset.resolve(strict=True)))
            if key in ref_paths or os.path.normcase(asset.name) in ref_names:
                result["referenced_assets"].append(str(asset))
                continue
            if suffix in SUPPORTED_EXTENSIONS:
                result["would_move_documents"].append(str(asset))
                continue
            prior = prior_candidates.get(key, {})
            try:
                identity = _media_observation_identity(asset)
            except Exception as exc:
                result["errors"].append(
                    f"cannot identify orphan-media observation {asset}: {exc}",
                )
                continue
            consecutive = 1
            if (
                int(prior.get("last_seen_sequence", -1)) == prior_sequence
                and prior.get("identity") == identity
            ):
                consecutive = int(prior.get("consecutive_sweeps", 0)) + 1
            destination = (
                result["would_move_media"]
                if consecutive >= ORPHAN_SWEEPS_REQUIRED
                else result["media_first_seen"]
            )
            destination.append(str(asset))
    except Exception as exc:
        result["errors"].append(f"preview failed open: {exc}")
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="read-only inbound/conformance preview; write nothing",
    )
    parser.add_argument(
        "--settle-seconds", type=float, default=FILE_SETTLE_SECONDS,
        help="provisional file-settle debounce (default: 2; use 0 explicitly for fixtures)",
    )
    parser.add_argument("--inbound-root")
    parser.add_argument("--vault-root")
    parser.add_argument("--state-dir")
    parser.add_argument(
        "--chromadb-path",
        help="override Chroma root for an applied sweep (ignored by --dry-run)",
    )
    args = parser.parse_args()
    call = preview if args.dry_run else sweep
    kwargs = {
        "inbound_root": args.inbound_root,
        "vault_root": args.vault_root,
        "state_dir": args.state_dir,
        "settle_seconds": max(0.0, args.settle_seconds),
    }
    if not args.dry_run:
        kwargs["chromadb_path"] = args.chromadb_path
    result = call(**kwargs)
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(1 if result["errors"] else 0)
