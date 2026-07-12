"""Tests for retention_sweeper — bounded housekeeping for append-only sinks.

Every test redirects the module's path constants into a tempdir so no
test touches the live ~/ora tree.

Run::

    /opt/homebrew/bin/python3 -m unittest orchestrator.tests.test_retention_sweeper -v
"""
from __future__ import annotations

import contextlib
import gzip
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import retention_sweeper  # noqa: E402
from oversight_sandbox import redirect_oversight_logs  # noqa: E402

DAY = 86400


class RetentionSweeperBase(unittest.TestCase):
    def setUp(self):
        redirect_oversight_logs(self)
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.traces = root / "data" / "pipeline-traces"
        self.logs = root / "logs"
        self.log_archive = self.logs / "archive"
        self.data_archive = root / "data" / "archive"
        self.server_log = root / "server.log"
        self.launchd_stdout = self.logs / "ora-server.stdout.log"
        self.launchd_stderr = self.logs / "ora-server.stderr.log"
        self.sessions = root / "sessions"
        self.sessions_archive = self.sessions / "archived"
        self.oversight = root / "data" / "oversight"
        self.jsonl = root / "data" / "model-catalog-changes.jsonl"
        for d in (self.traces, self.logs, self.sessions, self.oversight):
            d.mkdir(parents=True)

        self.patches = [
            mock.patch.object(retention_sweeper, "TRACES_DIR", str(self.traces)),
            mock.patch.object(retention_sweeper, "LOGS_DIR", str(self.logs)),
            mock.patch.object(retention_sweeper, "LOG_ARCHIVE_DIR", str(self.log_archive)),
            mock.patch.object(retention_sweeper, "DATA_ARCHIVE_DIR", str(self.data_archive)),
            mock.patch.object(retention_sweeper, "SERVER_LOG", str(self.server_log)),
            mock.patch.object(
                retention_sweeper,
                "LAUNCHD_SERVER_LOGS",
                (str(self.launchd_stdout), str(self.launchd_stderr)),
            ),
            mock.patch.object(retention_sweeper, "SESSIONS_DIR", str(self.sessions)),
            mock.patch.object(retention_sweeper, "SESSIONS_ARCHIVE_DIR", str(self.sessions_archive)),
            mock.patch.object(retention_sweeper, "OVERSIGHT_DATA_DIR", str(self.oversight)),
            mock.patch.object(retention_sweeper, "HEARTBEAT_FILE",
                              str(self.oversight / "retention-sweeper-heartbeat.json")),
            mock.patch.object(retention_sweeper, "ROTATABLE_JSONL", [str(self.jsonl)]),
            mock.patch.object(
                retention_sweeper._rp, "DATA_DIR_STR", str(root / "data"),
            ),
        ]
        for p in self.patches:
            p.start()
        self.addCleanup(self.tmp.cleanup)
        for p in self.patches:
            self.addCleanup(p.stop)

    @staticmethod
    def _age(path, days):
        old = time.time() - days * DAY
        os.utime(path, (old, old))


class TraceSweepTests(RetentionSweeperBase):
    def test_old_turn_dirs_removed_recent_kept(self):
        conv = self.traces / "conv-1"
        old_turn = conv / "2026-04-01T00-00-00"
        new_turn = conv / "2026-06-10T00-00-00"
        old_turn.mkdir(parents=True)
        new_turn.mkdir(parents=True)
        (old_turn / "trace.json").write_text("{}")
        self._age(old_turn, 45)

        summary = retention_sweeper.sweep()
        self.assertEqual(summary["traces_removed"], 1)
        self.assertFalse(old_turn.exists())
        self.assertTrue(new_turn.exists())

    def test_empty_conversation_dir_removed(self):
        conv = self.traces / "conv-empty"
        turn = conv / "t1"
        turn.mkdir(parents=True)
        self._age(turn, 45)

        retention_sweeper.sweep()
        self.assertFalse(conv.exists())

    def test_disabled_via_env_zero(self):
        conv = self.traces / "conv-1"
        turn = conv / "t1"
        turn.mkdir(parents=True)
        self._age(turn, 400)
        with mock.patch.dict(os.environ, {"ORA_RETENTION_TRACES_DAYS": "0"}):
            summary = retention_sweeper.sweep()
        self.assertEqual(summary["traces_removed"], 0)
        self.assertTrue(turn.exists())

    def test_symlinked_turn_is_not_followed(self):
        conv = self.traces / "conv-1"
        outside = Path(self.tmp.name) / "outside-turn"
        conv.mkdir()
        outside.mkdir()
        (outside / "trace.json").write_text("secret")
        self._age(outside, 400)
        (conv / "old-turn").symlink_to(outside, target_is_directory=True)

        summary = retention_sweeper.sweep()

        self.assertEqual(summary["traces_removed"], 0)
        self.assertEqual((outside / "trace.json").read_text(), "secret")

    def test_trace_sweep_uses_conversation_lifecycle_lock(self):
        conv = self.traces / "conv-lock"
        turn = conv / "old-turn"
        turn.mkdir(parents=True)
        self._age(turn, 45)
        seen = []
        real_lock = retention_sweeper._rp.conversation_lifecycle_lock

        @contextlib.contextmanager
        def record_lock(conversation_id, *args, **kwargs):
            seen.append(conversation_id)
            with real_lock(conversation_id, *args, **kwargs):
                yield

        with mock.patch.object(
            retention_sweeper._rp, "conversation_lifecycle_lock",
            side_effect=record_lock,
        ):
            retention_sweeper.sweep()

        self.assertIn("conv-lock", seen)


class LogSweepTests(RetentionSweeperBase):
    def test_old_log_gzipped_recent_untouched(self):
        old = self.logs / "maintenance-2026-04-14.log"
        new = self.logs / "chat.log"
        old.write_text("old log body\n")
        new.write_text("fresh\n")
        self._age(old, 60)

        summary = retention_sweeper.sweep()
        self.assertEqual(summary["logs_archived"], 1)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())
        gz = self.log_archive / "maintenance-2026-04-14.log.gz"
        self.assertTrue(gz.exists())
        with gzip.open(gz, "rt") as f:
            self.assertEqual(f.read(), "old log body\n")

    def test_ancient_archives_deleted(self):
        self.log_archive.mkdir(parents=True)
        ancient = self.log_archive / "server-20251201-000000.log.gz"
        with gzip.open(ancient, "wt") as f:
            f.write("x")
        self._age(ancient, 200)

        summary = retention_sweeper.sweep()
        self.assertEqual(summary["archives_deleted"], 1)
        self.assertFalse(ancient.exists())

    def test_expired_tool_event_archive_uses_shared_sidecar_lock(self):
        self.data_archive.mkdir(parents=True)
        ancient = self.data_archive / "tool-events-ancient.jsonl.gz"
        with gzip.open(ancient, "wt") as stream:
            stream.write('{"event": "old"}\n')
        self._age(ancient, 200)

        real_locked_file = retention_sweeper._rp.locked_file
        locked_paths: list[Path] = []

        def record_lock(path, *args, **kwargs):
            locked_paths.append(Path(path))
            return real_locked_file(path, *args, **kwargs)

        with mock.patch.object(
            retention_sweeper._rp, "locked_file", side_effect=record_lock,
        ):
            summary = retention_sweeper.sweep()

        self.assertEqual(summary["archives_deleted"], 1)
        self.assertFalse(ancient.exists())
        self.assertIn(ancient, locked_paths)


class ServerLogTests(RetentionSweeperBase):
    def test_oversize_rotated_and_truncated(self):
        self.server_log.write_bytes(b"x" * (2 * 1024 * 1024))
        with mock.patch.dict(os.environ, {"ORA_RETENTION_SERVERLOG_MB": "1"}):
            summary = retention_sweeper.sweep()
        self.assertTrue(summary["server_log_rotated"])
        self.assertEqual(self.server_log.stat().st_size, 0)
        gz = list(self.log_archive.glob("server-*.log.gz"))
        self.assertEqual(len(gz), 1)

    def test_undersize_untouched(self):
        self.server_log.write_text("small\n")
        summary = retention_sweeper.sweep()
        self.assertFalse(summary["server_log_rotated"])
        self.assertEqual(self.server_log.read_text(), "small\n")

    def test_append_fd_survives_truncation(self):
        # The launcher holds a long-lived append-mode handle; rotation must
        # leave it writable and the next append must land in the fresh file.
        self.server_log.write_bytes(b"x" * (2 * 1024 * 1024))
        writer = open(self.server_log, "a")
        self.addCleanup(writer.close)
        with mock.patch.dict(os.environ, {"ORA_RETENTION_SERVERLOG_MB": "1"}):
            retention_sweeper.sweep()
        writer.write("post-rotation line\n")
        writer.flush()
        self.assertIn("post-rotation line", self.server_log.read_text())

    def test_active_launchd_log_is_size_rotated_and_fd_survives(self):
        self.launchd_stdout.write_bytes(b"x" * (2 * 1024 * 1024))
        writer = open(self.launchd_stdout, "a")
        self.addCleanup(writer.close)

        with mock.patch.dict(os.environ, {"ORA_RETENTION_SERVERLOG_MB": "1"}):
            summary = retention_sweeper.sweep()

        self.assertEqual(summary["launchd_logs_rotated"], ["ora-server.stdout.log"])
        self.assertEqual(self.launchd_stdout.stat().st_size, 0)
        archives = list(self.log_archive.glob("ora-server.stdout-*.log.gz"))
        self.assertEqual(len(archives), 1)
        with gzip.open(archives[0], "rb") as handle:
            self.assertEqual(len(handle.read()), 2 * 1024 * 1024)
        writer.write("post-launchd-rotation\n")
        writer.flush()
        self.assertIn("post-launchd-rotation", self.launchd_stdout.read_text())

    def test_launchd_log_size_rotation_honors_disabled_limit(self):
        self.launchd_stderr.write_bytes(b"x" * (2 * 1024 * 1024))
        with mock.patch.dict(os.environ, {"ORA_RETENTION_SERVERLOG_MB": "0"}):
            summary = retention_sweeper.sweep()
        self.assertEqual(summary["launchd_logs_rotated"], [])
        self.assertEqual(self.launchd_stderr.stat().st_size, 2 * 1024 * 1024)

    def test_quiet_launchd_log_is_not_unlinked_by_age_sweep(self):
        self.launchd_stdout.write_text("quiet but still open\n")
        old = time.time() - 45 * 86400
        os.utime(self.launchd_stdout, (old, old))

        with mock.patch.dict(
            os.environ,
            {"ORA_RETENTION_LOGS_DAYS": "30", "ORA_RETENTION_SERVERLOG_MB": "50"},
        ):
            summary = retention_sweeper.sweep(now=time.time())

        self.assertTrue(self.launchd_stdout.exists())
        self.assertEqual(self.launchd_stdout.read_text(), "quiet but still open\n")
        self.assertEqual(summary["logs_archived"], 0)


class JsonlRotationTests(RetentionSweeperBase):
    def test_oversize_jsonl_rotated_to_archive(self):
        self.jsonl.write_text('{"r": 1}\n' * 200000)
        with mock.patch.dict(os.environ, {"ORA_RETENTION_JSONL_MB": "1"}):
            summary = retention_sweeper.sweep()
        self.assertIn("model-catalog-changes.jsonl", summary["jsonl_rotated"])
        self.assertFalse(self.jsonl.exists())
        gz = list(self.data_archive.glob("model-catalog-changes-*.jsonl.gz"))
        self.assertEqual(len(gz), 1)
        # An appender opening fresh (open/append/close pattern) recreates it.
        with open(self.jsonl, "a") as f:
            f.write('{"r": "new"}\n')
        self.assertTrue(self.jsonl.exists())

    def test_undersize_jsonl_untouched(self):
        self.jsonl.write_text('{"r": 1}\n')
        summary = retention_sweeper.sweep()
        self.assertEqual(summary["jsonl_rotated"], [])
        self.assertTrue(self.jsonl.exists())

    def test_tool_event_rotation_locks_source_and_destination_archive(self):
        live = self.jsonl.parent / "tool-events.jsonl"
        live.write_text('{"r": 1}\n' * 200000)
        expected_archive = (
            self.data_archive / "tool-events-20260712-120000.jsonl.gz"
        )
        real_locked_file = retention_sweeper._rp.locked_file
        locked_paths: list[Path] = []
        lock_entries: list[tuple[Path, tuple[Path, ...]]] = []
        lock_stack: list[Path] = []

        @contextlib.contextmanager
        def record_lock(path, *args, **kwargs):
            resolved = Path(path)
            locked_paths.append(resolved)
            with real_locked_file(path, *args, **kwargs):
                lock_entries.append((resolved, tuple(lock_stack)))
                lock_stack.append(resolved)
                try:
                    yield
                finally:
                    lock_stack.pop()

        with (
            mock.patch.object(retention_sweeper, "ROTATABLE_JSONL", [str(live)]),
            mock.patch.object(retention_sweeper, "_stamp",
                              return_value="20260712-120000"),
            mock.patch.object(retention_sweeper._rp, "locked_file",
                              side_effect=record_lock),
            mock.patch.dict(os.environ, {"ORA_RETENTION_JSONL_MB": "1"}),
        ):
            summary = retention_sweeper.sweep()

        self.assertEqual(summary["jsonl_rotated"], ["tool-events.jsonl"])
        self.assertFalse(live.exists())
        self.assertTrue(expected_archive.exists())
        self.assertIn(live, locked_paths)
        self.assertIn(expected_archive, locked_paths)
        archive_parents = [
            parents for path, parents in lock_entries
            if path == expected_archive
        ]
        self.assertEqual(len(archive_parents), 1)
        self.assertIn(live, archive_parents[0])


class SessionSweepTests(RetentionSweeperBase):
    def test_disabled_by_default(self):
        s = self.sessions / "ancient-session"
        s.mkdir()
        (s / "conversation.json").write_text("{}")
        self._age(s, 365)

        summary = retention_sweeper.sweep()
        self.assertEqual(summary["sessions_archived"], 0)
        self.assertTrue(s.exists())

    def test_enabled_archives_old_sessions_only(self):
        old = self.sessions / "old-session"
        new = self.sessions / "new-session"
        old.mkdir()
        new.mkdir()
        (old / "conversation.json").write_text("{}")
        self._age(old, 120)

        with mock.patch.dict(os.environ, {"ORA_RETENTION_SESSIONS_DAYS": "90"}):
            summary = retention_sweeper.sweep()
        self.assertEqual(summary["sessions_archived"], 1)
        self.assertFalse(old.exists())
        self.assertTrue((self.sessions_archive / "old-session" / "conversation.json").exists())
        self.assertTrue(new.exists())

    def test_archived_dir_itself_skipped(self):
        self.sessions_archive.mkdir()
        self._age(self.sessions_archive, 365)
        with mock.patch.dict(os.environ, {"ORA_RETENTION_SESSIONS_DAYS": "90"}):
            summary = retention_sweeper.sweep()
        self.assertEqual(summary["sessions_archived"], 0)

    def test_symlinked_archive_root_is_rejected(self):
        old = self.sessions / "old-session"
        outside = Path(self.tmp.name) / "outside-archive"
        old.mkdir()
        outside.mkdir()
        self._age(old, 120)
        self.sessions_archive.symlink_to(outside, target_is_directory=True)

        with mock.patch.dict(os.environ, {"ORA_RETENTION_SESSIONS_DAYS": "90"}):
            summary = retention_sweeper.sweep()

        self.assertTrue(old.exists())
        self.assertEqual(list(outside.iterdir()), [])
        self.assertTrue(summary["errors"])

    def test_session_sweep_uses_conversation_lifecycle_lock(self):
        old = self.sessions / "old-session"
        old.mkdir()
        self._age(old, 120)
        seen = []
        real_lock = retention_sweeper._rp.conversation_lifecycle_lock

        @contextlib.contextmanager
        def record_lock(conversation_id, *args, **kwargs):
            seen.append(conversation_id)
            with real_lock(conversation_id, *args, **kwargs):
                yield

        with (
            mock.patch.object(
                retention_sweeper._rp, "conversation_lifecycle_lock",
                side_effect=record_lock,
            ),
            mock.patch.dict(os.environ, {"ORA_RETENTION_SESSIONS_DAYS": "90"}),
        ):
            retention_sweeper.sweep()

        self.assertIn("old-session", seen)


class SweepInfrastructureTests(RetentionSweeperBase):
    def test_heartbeat_written(self):
        retention_sweeper.sweep()
        hb = json.loads((self.oversight / "retention-sweeper-heartbeat.json").read_text())
        self.assertEqual(hb["watcher"], "retention_sweeper")
        self.assertIn("beat_at", hb)

    def test_dry_run_changes_nothing(self):
        conv = self.traces / "conv-1"
        turn = conv / "t1"
        turn.mkdir(parents=True)
        self._age(turn, 90)
        self.server_log.write_bytes(b"x" * (2 * 1024 * 1024))

        with mock.patch.dict(os.environ, {"ORA_RETENTION_SERVERLOG_MB": "1"}):
            summary = retention_sweeper.sweep(dry_run=True)
        self.assertTrue(summary["dry_run"])
        self.assertEqual(summary["traces_removed"], 1)  # counted, not deleted
        self.assertTrue(turn.exists())
        self.assertEqual(self.server_log.stat().st_size, 2 * 1024 * 1024)
        self.assertFalse((self.oversight / "retention-sweeper-heartbeat.json").exists())

    def test_oversight_jsonl_never_touched(self):
        # The purge-protected logs live under data/oversight/ — the sweeper
        # must leave them alone no matter how large they grow.
        events = self.oversight / "events.jsonl"
        events.write_text('{"e": 1}\n' * 500000)
        self._age(events, 400)
        with mock.patch.dict(os.environ, {"ORA_RETENTION_JSONL_MB": "1"}):
            retention_sweeper.sweep()
        self.assertTrue(events.exists())
        self.assertGreater(events.stat().st_size, 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
