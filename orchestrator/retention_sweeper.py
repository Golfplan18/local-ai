"""Retention sweeper — bounded housekeeping for Ora's append-only artifacts.

Ora accumulates several unbounded sinks: per-turn pipeline traces, the
root server.log (appended by the unsupervised launcher), launchd's active
stdout/stderr logs, dated logs under ~/ora/logs/, and append-only JSONL
changelogs under ~/ora/data/. Nothing rotated any of them before this module; the
2026-06-11 repo audit found 80 MB of traces and a 13 MB server.log.

Sweep targets (each governed by an env knob; 0 disables the target):

  data/pipeline-traces/<conv>/<turn>/   delete turn dirs older than
                                        ORA_RETENTION_TRACES_DAYS (30);
                                        empty conversation dirs removed
  logs/*.log                            gzip into logs/archive/ when older
                                        than ORA_RETENTION_LOGS_DAYS (30)
  logs/archive/*.gz                     delete when older than
                                        ORA_RETENTION_ARCHIVE_DAYS (180)
  server.log (repo root)                when larger than
                                        ORA_RETENTION_SERVERLOG_MB (50):
                                        gzip-copy to logs/archive/ then
                                        truncate IN PLACE — the launcher
                                        holds a long-lived O_APPEND fd, so
                                        rename would not detach the writer
                                        but truncation is append-safe
  logs/ora-server.{stdout,stderr}.log    same size limit and copy/truncate
                                        behavior for launchd's live fds
  data/model-catalog-changes.jsonl      when larger than
  data/compaction-events.jsonl          ORA_RETENTION_JSONL_MB (10):
                                        atomic-rename to a temp name, gzip
                                        into data/archive/, unlink temp;
                                        appenders open/append/close per
                                        write, so the fresh file appears
                                        on their next append
  sessions/<id>/                        OFF BY DEFAULT. When
                                        ORA_RETENTION_SESSIONS_DAYS > 0,
                                        move session dirs older than N
                                        days into sessions/archived/.
                                        Archived sessions disappear from
                                        the sidebar's conversation list —
                                        that is the documented trade-off,
                                        which is why the default is off.

Deliberately NOT swept:

  data/oversight/*.jsonl                the stealth-conversation purge
                                        (conversation_closeout Layer 7)
                                        rewrites these in place to strip
                                        purged conversation_ids; archiving
                                        entries into gzip files would put
                                        them beyond the purge's reach
  data/conversation-manifest.jsonl      same purge constraint
  data/conversation-indexing-failures.jsonl  same purge constraint

G1.10 retired the production interval invocation. Finalized trace directories
now register exact persisted expiry deadlines. This module remains an explicit
historical-log/archive campaign and diagnostic:

    /opt/homebrew/bin/python3 ~/ora/orchestrator/retention_sweeper.py [--dry-run]
"""
from __future__ import annotations

import gzip
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import runtime_paths as _rp
    import tool_events as _te
except ImportError:  # pragma: no cover
    from orchestrator import runtime_paths as _rp
    from orchestrator import tool_events as _te

# Roots flow from runtime_paths (ORA_HOME-relocatable) so the sweeper
# always rotates the files the writers actually write.
ORA_DIR = _rp.WORKSPACE
DATA_DIR = _rp.DATA_DIR_STR
TRACES_DIR = os.path.join(DATA_DIR, "pipeline-traces")
LOGS_DIR = os.path.join(ORA_DIR, "logs")
LOG_ARCHIVE_DIR = os.path.join(LOGS_DIR, "archive")
DATA_ARCHIVE_DIR = os.path.join(DATA_DIR, "archive")
SERVER_LOG = os.path.join(ORA_DIR, "server.log")
LAUNCHD_SERVER_LOGS = (
    os.path.join(LOGS_DIR, "ora-server.stdout.log"),
    os.path.join(LOGS_DIR, "ora-server.stderr.log"),
)
SESSIONS_DIR = os.path.join(ORA_DIR, "sessions")
SESSIONS_ARCHIVE_DIR = os.path.join(SESSIONS_DIR, "archived")
_HEARTBEAT_BASENAME = "retention-sweeper-heartbeat.json"


def _oversight_data_dir() -> str:
    # Resolved at CALL time (not baked at import) so it tracks the live
    # DATA_DIR / ORA_HOME regardless of import ordering — baking it froze a
    # stale tempdir when this module was first imported under a test that had
    # relocated runtime_paths.DATA_DIR_STR, splitting the writer from
    # oversight_health's live reader in a full-group run. An explicit
    # monkeypatch of the module attribute still wins (oversight_sandbox /
    # suites set a real global via mock.patch.object); __getattr__ surfaces the
    # live value otherwise. Mirrors mlx_mutex._default_heartbeat_path (PR #240).
    # Reads _rp.DATA_DIR_STR (not the import-baked module-level DATA_DIR).
    override = globals().get("OVERSIGHT_DATA_DIR")
    if override is not None:
        return override
    return os.path.join(_rp.DATA_DIR_STR, "oversight")


def _heartbeat_file() -> str:
    override = globals().get("HEARTBEAT_FILE")
    if override is not None:
        return override
    return os.path.join(_oversight_data_dir(), _HEARTBEAT_BASENAME)


def __getattr__(name: str) -> str:
    # PEP 562: keep OVERSIGHT_DATA_DIR / HEARTBEAT_FILE readable as module
    # attributes (test_portability's heartbeat writer/reader agreement, the
    # sandbox's basename probe) while resolving them live per access.
    if name == "OVERSIGHT_DATA_DIR":
        return _oversight_data_dir()
    if name == "HEARTBEAT_FILE":
        return _heartbeat_file()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

ROTATABLE_JSONL = [
    os.path.join(DATA_DIR, "model-catalog-changes.jsonl"),
    os.path.join(DATA_DIR, "compaction-events.jsonl"),
    # Execution Review Phase 1: the global (non-turn) tool-event sink —
    # resolved through tool_events.global_sink_path() (env override or
    # runtime_paths default) so rotation targets the file record() writes.
    # Turn-scoped events live in pipeline-trace turn dirs and follow trace
    # retention; this file rotates on size and its rotated archives age out
    # below (telemetry must be sweepable — never persist-forever). Stealth
    # events are suppressed at write time; the stealth purge additionally
    # rewrites the live file (conversation_closeout Layer 6a).
    _te.global_sink_path(),
]


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _write_heartbeat():
    os.makedirs(_oversight_data_dir(), exist_ok=True)
    with open(_heartbeat_file(), "w") as f:
        json.dump({"watcher": "retention_sweeper", "beat_at": _now_iso()}, f)


def _gzip_file(src: str, dest_gz: str):
    os.makedirs(os.path.dirname(dest_gz), exist_ok=True)
    with open(src, "rb") as f_in, gzip.open(dest_gz, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)


def _sweep_traces(cutoff_days: int, now: float, dry_run: bool, summary: dict):
    if cutoff_days <= 0:
        return
    configured = Path(TRACES_DIR)
    try:
        traces_root = _rp.safe_owned_subdir(
            configured.parent, configured.name, create=False,
        )
    except Exception as exc:
        summary["errors"].append(f"trace retention root: {exc}")
        return
    if not traces_root.is_dir():
        return
    cutoff = now - cutoff_days * 86400
    for conv in sorted(os.listdir(traces_root)):
        conv_dir = traces_root / conv
        if conv_dir.is_symlink() or not conv_dir.is_dir():
            continue
        try:
            with _rp.conversation_lifecycle_lock(conv):
                # Recheck after taking the same cross-process lock used by
                # Delete Forever/privacy mutation.
                if conv_dir.is_symlink() or not conv_dir.is_dir():
                    continue
                for turn in sorted(os.listdir(conv_dir)):
                    turn_dir = conv_dir / turn
                    if turn_dir.is_symlink() or not turn_dir.is_dir():
                        continue
                    try:
                        if os.stat(turn_dir, follow_symlinks=False).st_mtime < cutoff:
                            manifest_path = turn_dir / "trace-manifest.json"
                            try:
                                with open(manifest_path) as f:
                                    manifest = json.load(f)
                                if (isinstance(manifest, dict)
                                        and manifest.get("retention_state") == "pinned"):
                                    summary["traces_pinned_skipped"] += 1
                                    continue
                            except Exception:
                                pass
                            if not dry_run:
                                shutil.rmtree(turn_dir)
                            summary["traces_removed"] += 1
                    except OSError as exc:
                        summary["errors"].append(
                            f"trace retention {turn_dir}: {exc}"
                        )
                try:
                    if not dry_run and not os.listdir(conv_dir):
                        os.rmdir(conv_dir)
                except OSError:
                    pass
        except Exception as exc:
            summary["errors"].append(f"trace retention {conv}: {exc}")


def _sweep_logs(cutoff_days: int, archive_days: int, now: float,
                dry_run: bool, summary: dict):
    if cutoff_days > 0 and os.path.isdir(LOGS_DIR):
        cutoff = now - cutoff_days * 86400
        launchd_live_names = {
            os.path.basename(path) for path in LAUNCHD_SERVER_LOGS
        }
        for name in sorted(os.listdir(LOGS_DIR)):
            if not name.endswith(".log"):
                continue
            # launchd may hold these descriptors open through long quiet
            # periods. Unlinking by age would strand future writes on an
            # invisible inode; the size-based copy/truncate pass below is the
            # only safe rotation policy for them.
            if name in launchd_live_names:
                continue
            path = os.path.join(LOGS_DIR, name)
            try:
                if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                    if not dry_run:
                        _gzip_file(path, os.path.join(LOG_ARCHIVE_DIR, name + ".gz"))
                        os.unlink(path)
                    summary["logs_archived"] += 1
            except OSError:
                continue
    if archive_days > 0 and os.path.isdir(LOG_ARCHIVE_DIR):
        cutoff = now - archive_days * 86400
        for name in sorted(os.listdir(LOG_ARCHIVE_DIR)):
            if not name.endswith(".gz"):
                continue
            path = os.path.join(LOG_ARCHIVE_DIR, name)
            try:
                if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                    if not dry_run:
                        os.unlink(path)
                    summary["archives_deleted"] += 1
            except OSError:
                continue
    # Execution Review Phase 1: rotated tool-event archives age out too.
    if archive_days > 0 and os.path.isdir(DATA_ARCHIVE_DIR):
        cutoff = now - archive_days * 86400
        for name in sorted(os.listdir(DATA_ARCHIVE_DIR)):
            if not (name.startswith("tool-events") and name.endswith(".gz")):
                continue
            path = os.path.join(DATA_ARCHIVE_DIR, name)
            try:
                if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                    if not dry_run:
                        # Delete Forever rewrites these archives in place.
                        # Share its per-archive sidecar lock so expiry cannot
                        # unlink a file midway through that rewrite.
                        with _rp.locked_file(path):
                            if (not os.path.isfile(path)
                                    or os.path.getmtime(path) >= cutoff):
                                continue
                            os.unlink(path)
                    summary["archives_deleted"] += 1
            except OSError:
                continue


def _sweep_server_log(max_mb: int, dry_run: bool, summary: dict):
    if max_mb <= 0 or not os.path.isfile(SERVER_LOG):
        return
    try:
        size = os.path.getsize(SERVER_LOG)
    except OSError:
        return
    if size <= max_mb * 1024 * 1024:
        return
    if not dry_run:
        # Copy-then-truncate: the launcher's detached server process holds
        # an O_APPEND fd on this exact inode, so a rename would carry the
        # writer along with it. Truncation leaves the fd valid and the
        # next append lands at the new (zero) end of file.
        _gzip_file(SERVER_LOG, os.path.join(LOG_ARCHIVE_DIR, f"server-{_stamp()}.log.gz"))
        with open(SERVER_LOG, "w"):
            pass
    summary["server_log_rotated"] = True
    summary["bytes_freed"] += size


def _sweep_launchd_server_logs(max_mb: int, dry_run: bool, summary: dict):
    """Size-bound launchd's continuously-active stdout/stderr files.

    Age-based rotation never selects an active log because each write refreshes
    its mtime. Copy-then-truncate preserves launchd's long-lived file descriptor
    in the same way as the root ``server.log`` rotation above. This check cannot
    run synchronously at each application write: launchd owns the descriptors,
    and native/third-party stderr writes bypass Python logging entirely. Reusing
    the already-running oversight retention pass bounds those external sinks
    without introducing another scheduled process.
    """
    if max_mb <= 0:
        return
    for path in LAUNCHD_SERVER_LOGS:
        if not os.path.isfile(path):
            continue
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        if size <= max_mb * 1024 * 1024:
            continue
        name = os.path.basename(path)
        stem = name[:-4] if name.endswith(".log") else name
        if not dry_run:
            _gzip_file(
                path,
                os.path.join(LOG_ARCHIVE_DIR, f"{stem}-{_stamp()}.log.gz"),
            )
            with open(path, "w"):
                pass
        summary["launchd_logs_rotated"].append(name)
        summary["bytes_freed"] += size


def _sweep_jsonl(max_mb: int, dry_run: bool, summary: dict):
    if max_mb <= 0:
        return
    for path in ROTATABLE_JSONL:
        if not os.path.isfile(path):
            continue
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        if size <= max_mb * 1024 * 1024:
            continue
        if not dry_run:
            # Writers and Delete Forever use this same source sidecar lock.
            # Recheck after acquisition because another sweep may have won.
            with _rp.locked_file(path):
                if not os.path.isfile(path):
                    continue
                size = os.path.getsize(path)
                if size <= max_mb * 1024 * 1024:
                    continue
                stem = os.path.basename(path).rsplit(".", 1)[0]
                tmp = path + ".rotating"
                archive = os.path.join(
                    DATA_ARCHIVE_DIR, f"{stem}-{_stamp()}.jsonl.gz"
                )
                # Closeout takes the archive-path lock before reading or
                # replacing a rotated tool-event file. Hold it for creation so
                # no reader can observe a partially-written gzip stream.
                with _rp.locked_file(archive):
                    os.replace(path, tmp)
                    _gzip_file(tmp, archive)
                    os.unlink(tmp)
        summary["jsonl_rotated"].append(os.path.basename(path))
        summary["bytes_freed"] += size


def _sweep_sessions(cutoff_days: int, now: float, dry_run: bool, summary: dict):
    if cutoff_days <= 0:
        return
    try:
        sessions_root = _rp.safe_owned_subdir(
            Path(SESSIONS_DIR), create=False,
        )
        if not sessions_root.is_dir():
            return
        archive_name = Path(SESSIONS_ARCHIVE_DIR).name
        archive_root = _rp.safe_owned_subdir(
            sessions_root, archive_name, create=not dry_run,
        )
    except Exception as exc:
        summary["errors"].append(f"session retention root: {exc}")
        return
    cutoff = now - cutoff_days * 86400
    for name in sorted(os.listdir(sessions_root)):
        if name == archive_name:
            continue
        path = sessions_root / name
        if path.is_symlink() or not path.is_dir():
            continue
        try:
            with _rp.conversation_lifecycle_lock(name):
                if path.is_symlink() or not path.is_dir():
                    continue
                if os.stat(path, follow_symlinks=False).st_mtime >= cutoff:
                    continue
                destination = archive_root / name
                if destination.exists() or destination.is_symlink():
                    raise FileExistsError(
                        f"archive destination already exists: {destination}"
                    )
                if not dry_run:
                    # Same-filesystem atomic rename: never copy through or
                    # follow a swapped session/archive symlink.
                    os.replace(path, destination)
                summary["sessions_archived"] += 1
        except Exception as exc:
            summary["errors"].append(f"session retention {name}: {exc}")


def sweep(dry_run: bool = False, now: float | None = None) -> dict:
    """Run every retention target once. Returns a summary dict."""
    now = time.time() if now is None else now
    summary: dict = {
        "traces_removed": 0,
        "traces_pinned_skipped": 0,
        "logs_archived": 0,
        "archives_deleted": 0,
        "server_log_rotated": False,
        "launchd_logs_rotated": [],
        "jsonl_rotated": [],
        "sessions_archived": 0,
        "bytes_freed": 0,
        "dry_run": dry_run,
        "errors": [],
    }
    _sweep_traces(_env_int("ORA_RETENTION_TRACES_DAYS", 30), now, dry_run, summary)
    _sweep_logs(_env_int("ORA_RETENTION_LOGS_DAYS", 30),
                _env_int("ORA_RETENTION_ARCHIVE_DAYS", 180), now, dry_run, summary)
    server_log_limit = _env_int("ORA_RETENTION_SERVERLOG_MB", 50)
    _sweep_server_log(server_log_limit, dry_run, summary)
    _sweep_launchd_server_logs(server_log_limit, dry_run, summary)
    _sweep_jsonl(_env_int("ORA_RETENTION_JSONL_MB", 10), dry_run, summary)
    _sweep_sessions(_env_int("ORA_RETENTION_SESSIONS_DAYS", 0), now, dry_run, summary)
    if not dry_run:
        _write_heartbeat()
    return summary


if __name__ == "__main__":
    import sys
    result = sweep(dry_run="--dry-run" in sys.argv)
    print(json.dumps(result, indent=2))
