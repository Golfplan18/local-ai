"""Retention sweeper — bounded housekeeping for Ora's append-only artifacts.

Ora accumulates several unbounded sinks: per-turn pipeline traces, the
root server.log (appended by the Ora.app launcher's detached server
process), dated logs under ~/ora/logs/, and append-only JSONL changelogs
under ~/ora/data/. Nothing rotated any of them before this module; the
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

Runs from the oversight daemon (ORA_RETENTION_SWEEPER_SEC, default 6 h)
and standalone:

    /opt/homebrew/bin/python3 ~/ora/orchestrator/retention_sweeper.py [--dry-run]
"""
from __future__ import annotations

import gzip
import json
import os
import shutil
import time
from datetime import datetime, timezone

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
SESSIONS_DIR = os.path.join(ORA_DIR, "sessions")
SESSIONS_ARCHIVE_DIR = os.path.join(SESSIONS_DIR, "archived")
OVERSIGHT_DATA_DIR = os.path.join(DATA_DIR, "oversight")
HEARTBEAT_FILE = os.path.join(OVERSIGHT_DATA_DIR, "retention-sweeper-heartbeat.json")

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
    os.makedirs(OVERSIGHT_DATA_DIR, exist_ok=True)
    with open(HEARTBEAT_FILE, "w") as f:
        json.dump({"watcher": "retention_sweeper", "beat_at": _now_iso()}, f)


def _gzip_file(src: str, dest_gz: str):
    os.makedirs(os.path.dirname(dest_gz), exist_ok=True)
    with open(src, "rb") as f_in, gzip.open(dest_gz, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)


def _sweep_traces(cutoff_days: int, now: float, dry_run: bool, summary: dict):
    if cutoff_days <= 0 or not os.path.isdir(TRACES_DIR):
        return
    cutoff = now - cutoff_days * 86400
    for conv in sorted(os.listdir(TRACES_DIR)):
        conv_dir = os.path.join(TRACES_DIR, conv)
        if not os.path.isdir(conv_dir):
            continue
        for turn in sorted(os.listdir(conv_dir)):
            turn_dir = os.path.join(conv_dir, turn)
            if not os.path.isdir(turn_dir):
                continue
            try:
                if os.path.getmtime(turn_dir) < cutoff:
                    if not dry_run:
                        shutil.rmtree(turn_dir, ignore_errors=True)
                    summary["traces_removed"] += 1
            except OSError:
                continue
        try:
            if not dry_run and not os.listdir(conv_dir):
                os.rmdir(conv_dir)
        except OSError:
            pass


def _sweep_logs(cutoff_days: int, archive_days: int, now: float,
                dry_run: bool, summary: dict):
    if cutoff_days > 0 and os.path.isdir(LOGS_DIR):
        cutoff = now - cutoff_days * 86400
        for name in sorted(os.listdir(LOGS_DIR)):
            if not name.endswith(".log"):
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
            stem = os.path.basename(path).rsplit(".", 1)[0]
            tmp = path + ".rotating"
            os.replace(path, tmp)
            _gzip_file(tmp, os.path.join(DATA_ARCHIVE_DIR, f"{stem}-{_stamp()}.jsonl.gz"))
            os.unlink(tmp)
        summary["jsonl_rotated"].append(os.path.basename(path))
        summary["bytes_freed"] += size


def _sweep_sessions(cutoff_days: int, now: float, dry_run: bool, summary: dict):
    if cutoff_days <= 0 or not os.path.isdir(SESSIONS_DIR):
        return
    cutoff = now - cutoff_days * 86400
    os.makedirs(SESSIONS_ARCHIVE_DIR, exist_ok=True)
    for name in sorted(os.listdir(SESSIONS_DIR)):
        if name == "archived":
            continue
        path = os.path.join(SESSIONS_DIR, name)
        if not os.path.isdir(path):
            continue
        try:
            if os.path.getmtime(path) < cutoff:
                if not dry_run:
                    shutil.move(path, os.path.join(SESSIONS_ARCHIVE_DIR, name))
                summary["sessions_archived"] += 1
        except OSError:
            continue


def sweep(dry_run: bool = False, now: float | None = None) -> dict:
    """Run every retention target once. Returns a summary dict."""
    now = time.time() if now is None else now
    summary: dict = {
        "traces_removed": 0,
        "logs_archived": 0,
        "archives_deleted": 0,
        "server_log_rotated": False,
        "jsonl_rotated": [],
        "sessions_archived": 0,
        "bytes_freed": 0,
        "dry_run": dry_run,
    }
    _sweep_traces(_env_int("ORA_RETENTION_TRACES_DAYS", 30), now, dry_run, summary)
    _sweep_logs(_env_int("ORA_RETENTION_LOGS_DAYS", 30),
                _env_int("ORA_RETENTION_ARCHIVE_DAYS", 180), now, dry_run, summary)
    _sweep_server_log(_env_int("ORA_RETENTION_SERVERLOG_MB", 50), dry_run, summary)
    _sweep_jsonl(_env_int("ORA_RETENTION_JSONL_MB", 10), dry_run, summary)
    _sweep_sessions(_env_int("ORA_RETENTION_SESSIONS_DAYS", 0), now, dry_run, summary)
    if not dry_run:
        _write_heartbeat()
    return summary


if __name__ == "__main__":
    import sys
    result = sweep(dry_run="--dry-run" in sys.argv)
    print(json.dumps(result, indent=2))
