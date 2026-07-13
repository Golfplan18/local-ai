"""Cross-platform (macOS + Windows) portability tests for the Execution
Review Phase 1 instrumentation. These run on macOS/Linux CI and simulate
Windows via ntpath/PureWindowsPath and platform monkeypatching — no Windows
host required. Covers the judge's portability conditions."""

from __future__ import annotations

import ntpath
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path, PureWindowsPath
from unittest import mock

_ORCH = Path(__file__).resolve().parent.parent
if str(_ORCH) not in sys.path:
    sys.path.insert(0, str(_ORCH))
_TOOLS = _ORCH / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.append(str(_TOOLS))
# Repo root, so package-qualified imports (orchestrator.conversation_closeout,
# which uses intra-package relative imports) resolve regardless of cwd.
_REPO = _ORCH.parent
if str(_REPO) not in sys.path:
    sys.path.append(str(_REPO))

import runtime_paths  # noqa: E402
import tool_events  # noqa: E402


def _win_norm_key(p) -> str:
    """Simulate runtime_paths.norm_key on Windows: ntpath.normcase folds
    case + backslashes; tool_events._cmp_key then forward-slashes it."""
    return ntpath.normcase(str(p))


class TestWindowsSecretPaths(unittest.TestCase):
    """Condition 7a: Windows-style secret paths classify as secret. Uses the
    REAL resolve_path_sensitivity — backslashes are handled by _matchable."""

    def test_windows_secret_paths(self):
        for p in (r"C:\Users\alice\.ssh\id_rsa",
                  r"C:\Users\alice\.ssh2\known_hosts",
                  r"C:\Users\alice\.aws\credentials",
                  r"C:\Users\alice\creds\credentials.txt",
                  r"C:\Users\alice\app.env",
                  r"C:\Users\alice\.env",
                  r"C:\Users\alice\server.pem",
                  r"C:\Users\alice\key.ppk",
                  r"C:\Users\alice\id_ed25519",
                  r"D:\secrets\prod.pem.txt"):
            self.assertEqual(tool_events.resolve_path_sensitivity(p),
                             "secret", p)

    def test_windows_non_secret_stays_lower_tier(self):
        for p in (r"C:\Users\alice\Documents\notes.txt",
                  r"C:\Users\alice\monkey.txt",
                  r"C:\Users\alice\tokenizer.json"):
            self.assertNotEqual(tool_events.resolve_path_sensitivity(p),
                                "secret", p)

    def test_matchable_forward_slashes_and_lowercases(self):
        m = tool_events._matchable(r"X:\Users\Bob\.SSH\ID_RSA")
        self.assertIn("/.ssh/id_rsa", m)
        self.assertNotIn("\\", m)


class TestWindowsProtectedPaths(unittest.TestCase):
    """Condition 7b: Windows protected-config paths (backslash + case
    variation) gate. Simulated by injecting a Windows norm_key + prefixes."""

    def _win_prefixes(self):
        return [_win_norm_key(r"C:\Users\bob\ora\orchestrator").replace("\\", "/"),
                _win_norm_key(r"C:\Users\bob\ora\config\hooks").replace("\\", "/"),
                _win_norm_key(r"C:\Users\bob\ora\server").replace("\\", "/")]

    def test_windows_protected_config(self):
        with mock.patch.object(tool_events._rp, "norm_key", _win_norm_key), \
             mock.patch.object(tool_events, "_PROTECTED_PREFIXES",
                               self._win_prefixes()):
            for p, expected in (
                    (r"C:\Users\bob\ora\Orchestrator\boot.py", True),   # case
                    (r"C:\Users\BOB\ora\config\hooks\evil.json", True),
                    (r"C:\Users\bob\ora\Server\server.py", True),
                    (r"C:\Users\bob\ora\modes\x.md", False),
                    (r"C:\Users\bob\ora-project.json", True),           # basename
                    (r"C:\Users\bob\some\.ora\evidence.yaml", True)):
                self.assertEqual(tool_events.is_protected_config_path(p),
                                 expected, p)

    def test_purewindowspath_shape_is_understood(self):
        # sanity: PureWindowsPath round-trips the shapes we assert on.
        self.assertEqual(PureWindowsPath(r"C:\a\b").as_posix(), "C:/a/b")


class TestNoFcntlCrash(unittest.TestCase):
    """Condition 7c: no top-level fcntl import; locking works when fcntl is
    absent (Windows). Import of the modules must not require fcntl."""

    def test_modules_have_no_toplevel_fcntl(self):
        self.assertFalse(hasattr(tool_events, "fcntl"))
        import oversight_actions
        self.assertFalse(hasattr(oversight_actions, "fcntl"))

    def test_locked_file_without_fcntl_uses_msvcrt(self):
        # Simulate Windows: fcntl absent, a fake msvcrt present.
        calls = []

        class _FakeMsvcrt:
            LK_NBLCK = 1
            LK_UNLCK = 2

            def locking(self, fd, mode, nbytes):
                calls.append(mode)

        with mock.patch.object(runtime_paths, "_fcntl", None), \
             mock.patch.object(runtime_paths, "_msvcrt", _FakeMsvcrt()):
            tmp = os.path.join(tempfile.mkdtemp(), "x.json")
            with runtime_paths.locked_file(tmp):
                with open(tmp, "w") as _f:
                    _f.write("1")
        self.assertIn(1, calls)   # lock acquired
        self.assertIn(2, calls)   # lock released

    def test_locked_file_without_any_primitive_does_not_crash(self):
        with mock.patch.object(runtime_paths, "_fcntl", None), \
             mock.patch.object(runtime_paths, "_msvcrt", None):
            tmp = os.path.join(tempfile.mkdtemp(), "x.json")
            with runtime_paths.locked_file(tmp):
                with open(tmp, "w") as _f:
                    _f.write("1")
        with open(tmp) as _f:
            self.assertEqual(_f.read(), "1")


class TestWindowsShellFailsClosed(unittest.TestCase):
    """Condition 7d: on a non-POSIX shell, the profiler fails closed."""

    def test_non_posix_shell_all_commands_unknown(self):
        import bash_execute
        with mock.patch.object(bash_execute, "_posix_shell_available",
                               return_value=False):
            for cmd in ("cat file.txt", "git status", "echo hi",
                        "dir C:\\Users", "type secrets.txt"):
                r = bash_execute.resolve_shell_profile(cmd)
                self.assertTrue(r["unknown"], cmd)
                self.assertEqual(r["profile"], "non-posix-shell", cmd)

    def test_posix_shell_available_by_platform(self):
        import bash_execute
        with mock.patch.object(os, "name", "posix"):
            self.assertTrue(bash_execute._posix_shell_available())
        with mock.patch.object(os, "name", "nt"), \
             mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ORA_POSIX_SHELL", None)
            self.assertFalse(bash_execute._posix_shell_available())
        # A resolved shell path makes the capability available…
        declared_shell = r"C:\Git\bin\bash.exe"
        with mock.patch.object(os, "name", "nt"), \
             mock.patch.object(bash_execute, "_posix_shell_path",
                               return_value=declared_shell):
            self.assertTrue(bash_execute._posix_shell_available())
        # …but a flag-style or nonexistent value is NOT: the declared shell
        # must be executable, because execute_command runs commands under it.
        for bad in ("1", "not-a-real-shell-xyz", "/nonexistent/never/sh"):
            with mock.patch.object(os, "name", "nt"), \
                 mock.patch.dict(os.environ, {"ORA_POSIX_SHELL": bad}):
                self.assertFalse(bash_execute._posix_shell_available(), bad)

    def test_posix_shell_path_resolves_names_via_which(self):
        import bash_execute
        with mock.patch.object(os, "name", "nt"), \
             mock.patch.dict(os.environ, {"ORA_POSIX_SHELL": "bash"}), \
             mock.patch.object(bash_execute.shutil, "which",
                               return_value=r"C:\Git\bin\bash.exe"):
            resolved = bash_execute._posix_shell_path()
            self.assertEqual(resolved, r"C:\Git\bin\bash.exe")


class TestWindowsExecutionShell(unittest.TestCase):
    """Revision 7 [P1]: the shell that RUNS a command must be the shell the
    profiler MODELED. On Windows: no valid ORA_POSIX_SHELL → execution
    refuses (never falls back to cmd.exe); a valid one → the command runs
    under [shell, -c, ...] with shell=False, foreground and background."""

    def test_windows_without_shell_refuses_foreground(self):
        import bash_execute
        with mock.patch.object(os, "name", "nt"), \
             mock.patch.dict(os.environ, {}, clear=False), \
             mock.patch.object(bash_execute.subprocess, "run") as m_run, \
             mock.patch.object(bash_execute.subprocess, "Popen") as m_popen:
            os.environ.pop("ORA_POSIX_SHELL", None)
            r = bash_execute.execute_command("echo hi")
        m_run.assert_not_called()
        m_popen.assert_not_called()
        self.assertEqual(r["returncode"], -1)
        self.assertIn("NOT run", r["stderr"])

    def test_windows_without_shell_refuses_background(self):
        import bash_execute
        with mock.patch.object(os, "name", "nt"), \
             mock.patch.dict(os.environ, {}, clear=False), \
             mock.patch.object(bash_execute.subprocess, "Popen") as m_popen:
            os.environ.pop("ORA_POSIX_SHELL", None)
            r = bash_execute.execute_command("sleep 5 &")
        m_popen.assert_not_called()
        self.assertIsNone(r["pid"])
        self.assertIn("NOT run", r["status"])

    def test_windows_with_shell_executes_under_declared_shell(self):
        # Real end-to-end run when this host has a POSIX shell: os.name is
        # simulated as nt and the command runs via [shell, '-c', ...].
        import bash_execute
        shell = bash_execute.shutil.which("sh")
        if not shell:
            self.skipTest("no POSIX shell available for end-to-end fixture")
        with mock.patch.object(os, "name", "nt"), \
             mock.patch.dict(os.environ, {"ORA_POSIX_SHELL": shell}):
            r = bash_execute.execute_command("echo posix-shell-ok")
        self.assertEqual(r["returncode"], 0)
        self.assertIn("posix-shell-ok", r["stdout"])

    def test_windows_with_shell_never_uses_shell_true(self):
        import bash_execute
        shell = r"C:\Git\bin\bash.exe"
        fake = mock.MagicMock()
        fake.stdout, fake.stderr, fake.returncode = "", "", 0
        with mock.patch.object(os, "name", "nt"), \
             mock.patch.dict(os.environ, {"ORA_POSIX_SHELL": shell}), \
             mock.patch.object(bash_execute, "_posix_shell_path",
                               return_value=shell), \
             mock.patch.object(bash_execute.subprocess, "run",
                               return_value=fake) as m_run:
            bash_execute.execute_command("echo hi")
        args, kwargs = m_run.call_args
        self.assertEqual(args[0], [shell, "-c", "echo hi"])
        self.assertFalse(kwargs.get("shell"))

    def test_windows_background_uses_declared_shell(self):
        import bash_execute
        fake_proc = mock.MagicMock()
        fake_proc.pid = 4242
        fake_proc.poll.return_value = None
        shell = r"C:\Git\bin\bash.exe"
        before = list(bash_execute.MANAGED_PROCESSES)
        try:
            with mock.patch.object(os, "name", "nt"), \
                 mock.patch.dict(os.environ, {"ORA_POSIX_SHELL": shell}), \
                 mock.patch.object(bash_execute, "_posix_shell_path",
                                   return_value=shell), \
                 mock.patch.object(bash_execute.subprocess, "Popen",
                                   return_value=fake_proc) as m_popen:
                r = bash_execute.execute_command("sleep 5", background=True)
            args, kwargs = m_popen.call_args
            self.assertEqual(args[0], [shell, "-c", "sleep 5"])
            self.assertFalse(kwargs.get("shell"))
            self.assertEqual(r["pid"], 4242)
        finally:
            bash_execute.MANAGED_PROCESSES[:] = before

    def test_posix_execution_unchanged(self):
        # On the real (POSIX) platform the pre-existing shell=True path runs.
        if os.name == "nt":
            self.skipTest("POSIX-only execution path")
        import bash_execute
        r = bash_execute.execute_command("echo posix-default-ok")
        self.assertEqual(r["returncode"], 0)
        self.assertIn("posix-default-ok", r["stdout"])


class TestMcpConfigPortability(unittest.TestCase):
    """Revision 7 [P1]: the checked-in MCP registry carries no machine- or
    platform-specific absolute paths; placeholders resolve at launch through
    env overrides / runtime_paths."""

    def _registry(self):
        import json
        with open(_ORCH.parent / "config" / "mcp-servers.json") as f:
            return json.load(f)

    def test_no_hardcoded_user_paths_in_checked_in_config(self):
        for server in self._registry()["servers"]:
            for arg in server.get("args", []):
                self.assertFalse(arg.startswith("/Users/"), arg)
                self.assertFalse(arg.startswith("/home/"), arg)
                self.assertNotIn(":\\Users", arg)
            cmd = server.get("command", "")
            self.assertFalse(cmd.startswith("/Users/"), cmd)

    def test_vault_fs_server_uses_placeholder(self):
        vault_fs = next(s for s in self._registry()["servers"]
                        if s["name"] == "vault-fs")
        self.assertIn("${ORA_VAULT}", vault_fs["args"])

    def test_placeholder_expands_to_runtime_paths_default(self):
        import mcp_client
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ORA_VAULT", None)
            expanded = mcp_client._expand_placeholders("${ORA_VAULT}")
        self.assertEqual(expanded, runtime_paths.VAULT_STR)

    def test_placeholder_env_override_wins_windows_path(self):
        # Relocated / Windows vault: the env override at launch wins.
        import mcp_client
        win_vault = r"D:\relocated\vault"
        with mock.patch.dict(os.environ, {"ORA_VAULT": win_vault}):
            self.assertEqual(
                mcp_client._expand_placeholders(["x", "${ORA_VAULT}"]),
                ["x", win_vault])

    def test_expansion_recurses_and_leaves_unknown_verbatim(self):
        import mcp_client
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ORA_HOME", None)
            out = mcp_client._expand_placeholders(
                {"a": ["${ORA_HOME}"], "b": "${NOT_A_PLACEHOLDER}", "c": 3})
        self.assertEqual(out["a"], [runtime_paths.WORKSPACE])
        self.assertEqual(out["b"], "${NOT_A_PLACEHOLDER}")
        self.assertEqual(out["c"], 3)

    def test_registry_vault_fs_args_expand_to_real_path(self):
        import mcp_client
        vault_fs = next(s for s in self._registry()["servers"]
                        if s["name"] == "vault-fs")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ORA_VAULT", None)
            expanded = mcp_client._expand_placeholders(vault_fs["args"])
        self.assertIn(runtime_paths.VAULT_STR, expanded)


class TestMcpStdioWindowsPortability(unittest.TestCase):
    """Revision 8 [P1]: the stdio receive path must not wait on the pipe
    with select() — on Windows, select supports only sockets, so every
    stdio MCP initialization would fail. Lines are pumped by a reader
    thread onto a queue; these tests drive _recv through a REAL pipe with
    select.select simulated as pipe-incapable (raising, as on Windows)."""

    def _make_pipe_connection(self, binary_writer=False):
        import types
        import mcp_client
        r, w = os.pipe()
        # Reader mode mirrors what connect() gives the subprocess pipe:
        # UTF-8 pinned, errors="replace".
        conn = mcp_client.MCPConnection(name="test-pipe", command="unused")
        conn.process = types.SimpleNamespace(
            stdout=os.fdopen(r, "r", encoding="utf-8", errors="replace"))
        conn._start_reader()
        writer = os.fdopen(w, "wb" if binary_writer else "w")

        def _close_pipe_ends():
            # Close the writer first so the pump sees EOF and exits, THEN
            # close the reader wrapper (avoids both a ResourceWarning for
            # the unclosed wrapper and closing a stream mid-readline).
            try:
                writer.close()
            except Exception:
                pass
            if conn._reader_thread is not None:
                conn._reader_thread.join(timeout=2)
            try:
                conn.process.stdout.close()
            except Exception:
                pass

        self.addCleanup(_close_pipe_ends)
        return conn, writer

    def test_recv_works_when_select_rejects_pipes(self):
        import json
        import select
        conn, writer = self._make_pipe_connection()
        try:
            with mock.patch.object(
                    select, "select",
                    side_effect=OSError("select only supported on sockets")):
                writer.write(json.dumps(
                    {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}) + "\n")
                writer.flush()
                msg = conn._recv(timeout=5)
            self.assertIsNotNone(msg)
            self.assertEqual(msg["result"], {"ok": True})
        finally:
            writer.close()

    def test_recv_times_out_cleanly_without_data(self):
        import time
        conn, writer = self._make_pipe_connection()
        try:
            start = time.time()
            self.assertIsNone(conn._recv(timeout=0.3))
            self.assertLess(time.time() - start, 3.0)
        finally:
            writer.close()

    def test_recv_skips_notifications_and_blank_lines(self):
        import json
        conn, writer = self._make_pipe_connection()
        try:
            writer.write("\n")
            writer.write(json.dumps(
                {"jsonrpc": "2.0", "method": "notifications/progress",
                 "params": {}}) + "\n")
            writer.write("not-json\n")
            writer.write(json.dumps(
                {"jsonrpc": "2.0", "id": 2, "result": {"tools": []}}) + "\n")
            writer.flush()
            msg = conn._recv(timeout=5)
            self.assertEqual(msg["id"], 2)
        finally:
            writer.close()

    def test_recv_returns_none_on_eof(self):
        conn, writer = self._make_pipe_connection()
        writer.close()  # server closed stdout
        self.assertIsNone(conn._recv(timeout=5))

    def test_recv_after_eof_answers_immediately_every_time(self):
        # Adversarial fold: the EOF sentinel must not be one-shot — a dead
        # server must answer every subsequent call instantly (old
        # select-on-EOF behavior), not stall each caller a full timeout.
        import json
        import time
        conn, writer = self._make_pipe_connection()
        writer.write(json.dumps(
            {"jsonrpc": "2.0", "id": 7, "result": {"last": True}}) + "\n")
        writer.close()
        # Queued line from before EOF is still delivered…
        msg = conn._recv(timeout=5)
        self.assertEqual(msg["id"], 7)
        # …then every call returns None immediately, repeatedly.
        for _ in range(3):
            start = time.time()
            self.assertIsNone(conn._recv(timeout=30))
            self.assertLess(time.time() - start, 1.0)

    def test_bad_bytes_do_not_kill_receive_path(self):
        # Adversarial fold: one malformed line from a healthy server must
        # not end the reader thread — the next valid response still lands.
        import json
        conn, writer = self._make_pipe_connection(binary_writer=True)
        try:
            writer.write(b"\xff\xfe garbage \x9d\n")
            writer.write(json.dumps(
                {"jsonrpc": "2.0", "id": 3,
                 "result": {"alive": True}}).encode("utf-8") + b"\n")
            writer.flush()
            msg = conn._recv(timeout=5)
            self.assertIsNotNone(msg)
            self.assertEqual(msg["result"], {"alive": True})
        finally:
            writer.close()

    def test_popen_pins_utf8_with_replace(self):
        # Adversarial fold: bare text=True decodes with the locale ANSI
        # codepage on Windows Python <= 3.14; MCP stdio is UTF-8 by spec.
        import mcp_client
        with mock.patch.object(mcp_client.subprocess, "Popen",
                               side_effect=RuntimeError("stop")) as m:
            conn = mcp_client.MCPConnection(name="t", command="unused")
            self.assertFalse(conn.connect())
        kwargs = m.call_args.kwargs
        self.assertEqual(kwargs.get("encoding"), "utf-8")
        self.assertEqual(kwargs.get("errors"), "replace")

    def test_recv_queue_is_bounded(self):
        # Adversarial fold: an unbounded queue replaced the OS pipe's
        # backpressure with unlimited parent memory for chatty servers.
        import mcp_client
        conn = mcp_client.MCPConnection(name="t", command="unused")
        self.assertEqual(conn._recv_queue.maxsize,
                         mcp_client._RECV_QUEUE_MAXLINES)
        self.assertGreater(conn._recv_queue.maxsize, 0)

    def test_receive_path_has_no_select_dependency(self):
        # The docstrings DISCUSS select (to say why it can't be used); the
        # code must never import it — without the import it cannot call it,
        # and the functional test above proves _recv works when select
        # rejects pipes the way Windows does.
        import inspect
        import mcp_client
        self.assertNotIn("import select", inspect.getsource(mcp_client))


class TestCodeExecuteNonMac(unittest.TestCase):
    """Condition 7e: code_execute is unavailable/gated off macOS and never
    claims 'orchestrated'."""

    def test_unavailable_and_gated_off_mac(self):
        import code_execute
        for plat in ("win32", "linux"):
            with mock.patch.object(code_execute.sys, "platform", plat):
                self.assertIsNone(code_execute._sandbox_backend())
                self.assertFalse(code_execute.sandbox_available())
                axes = code_execute.code_execute_axes()
                self.assertTrue(axes.get("unknown"))
                self.assertNotEqual(axes.get("enforcement"), "orchestrated")
                out = code_execute.code_execute("print(1)")
                self.assertIn("unavailable", out)

    def test_imports_cleanly_regardless_of_platform(self):
        # No import-time platform dependency that would crash on Windows.
        import importlib
        import code_execute
        importlib.reload(code_execute)  # must not raise


class TestSandboxDeniesRelocatedRoots(unittest.TestCase):
    """Revision 7 fold: the code_execute sandbox read-denies must cover the
    env-relocatable Ora private roots (ORA_HOME / ORA_VAULT /
    ORA_CONVERSATIONS), not just $HOME — a vault moved outside the OS home
    must stay unreadable, or the tool's declared sensitivity=private /
    egress=none axes would be false."""

    def test_profile_contains_denies_for_private_roots(self):
        import code_execute
        with mock.patch.object(code_execute, "_PRIVATE_DENY_ROOTS",
                               ["/tmp/reloc-vault"]):
            prof = code_execute._sandbox_profile("/tmp/s", "/tmp/t")
        expected = os.path.realpath("/tmp/reloc-vault")
        self.assertIn(f'(deny file-read* (subpath "{expected}"))', prof)
        home = os.path.realpath(os.path.expanduser("~"))
        self.assertIn(f'(deny file-read* (subpath "{home}"))', prof)

    def test_default_deny_roots_flow_from_runtime_paths(self):
        import code_execute
        for root in (runtime_paths.WORKSPACE, runtime_paths.VAULT_STR,
                     runtime_paths.CONVERSATIONS_STR):
            self.assertIn(root, code_execute._PRIVATE_DENY_ROOTS)

    def test_live_sandbox_denies_vault_outside_home(self):
        # Regression for the demonstrated exploit: with the vault relocated
        # outside $HOME, sandboxed code could read and print it.
        import code_execute
        if not code_execute.sandbox_available():
            self.skipTest("sandbox-exec unavailable on this platform")
        with tempfile.TemporaryDirectory(dir="/tmp") as vault:
            secret = os.path.join(vault, "note.md")
            with open(secret, "w") as f:
                f.write("LEAKMARKER-private-vault-note")
            with mock.patch.object(code_execute, "_PRIVATE_DENY_ROOTS",
                                   [vault]):
                out = code_execute.code_execute(
                    f"print(open({secret!r}).read())")
        self.assertNotIn("LEAKMARKER", out)


class TestSearchFilesWithoutGrep(unittest.TestCase):
    """Condition 7f: search works without Unix grep, still withholding
    secret descendants."""

    def test_python_fallback_preserves_withholding(self):
        import search_files
        import json
        root = tempfile.mkdtemp(dir=os.path.expanduser("~/ora"))
        try:
            os.makedirs(os.path.join(root, "sub"))
            with open(os.path.join(root, "normal.txt"), "w") as _f:
                _f.write("NEEDLE ok\n")
            with open(os.path.join(root, "sub", "credentials.txt"), "w") as _f:
                _f.write("NEEDLE leaked\n")
            with open(os.path.join(root, ".env"), "w") as _f:
                _f.write("NEEDLE=envleak\n")
            # Force the Python backend (no grep dependency).
            with mock.patch.object(search_files, "_grep_available",
                                   return_value=False):
                blob = json.dumps(search_files.grep_files("NEEDLE", root))
            self.assertIn("normal.txt", blob)
            self.assertNotIn("leaked", blob)
            self.assertNotIn("envleak", blob)
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

    def test_grep_disabled_on_windows(self):
        import search_files
        with mock.patch.object(os, "name", "nt"):
            self.assertFalse(search_files._grep_available())


class TestCentralPathLayer(unittest.TestCase):
    """Condition 3: Phase-1 roots come from the single runtime_paths source."""

    def test_roots_come_from_runtime_paths(self):
        self.assertEqual(tool_events.WORKSPACE, runtime_paths.WORKSPACE)
        import dispatcher
        self.assertEqual(dispatcher.WORKSPACE, runtime_paths.WORKSPACE)
        self.assertEqual(dispatcher.VAULT, runtime_paths.VAULT_STR)

    def test_gate_queue_and_event_roots_come_from_runtime_paths(self):
        # Revision 7 [P2]: the gate's Paused-queue writes (oversight_queue /
        # oversight_actions) and its failure-telemetry event log must follow
        # an ORA_HOME relocation like tool events and approvals do.
        import oversight_actions
        import oversight_events
        import oversight_queue
        oversight_root = os.path.join(runtime_paths.DATA_DIR_STR, "oversight")
        self.assertEqual(oversight_actions.WORKSPACE, runtime_paths.WORKSPACE)
        self.assertEqual(oversight_actions.OVERSIGHT_DATA_DIR, oversight_root)
        self.assertEqual(
            oversight_actions.HUMAN_QUEUE_PATH,
            os.path.join(oversight_root, "human-queue.jsonl"))
        self.assertEqual(oversight_queue.WORKSPACE, runtime_paths.WORKSPACE)
        self.assertEqual(
            oversight_queue.REEVAL_QUEUE_PATH,
            os.path.join(oversight_root, "reeval-queue.jsonl"))
        self.assertEqual(
            oversight_events.EVENT_LOG_PATH,
            os.path.join(oversight_root, "events.jsonl"))

    def test_gate_log_peer_writers_agree(self):
        # Revision 7 fold: every producer/consumer of the gate-coupled
        # JSONL files must agree on location under relocation — the
        # fan-out writer vs the event bus, the re-eval writer vs the
        # Operating aggregator, and the rotation list vs the live sink.
        import oversight_actions
        import oversight_events
        import oversight_queue
        import oversight_relationships
        import redefinition_handler
        import retention_sweeper
        self.assertEqual(oversight_relationships.EVENTS_LOG_PATH,
                         oversight_events.EVENT_LOG_PATH)
        self.assertEqual(oversight_relationships.ACTIONS_LOG_PATH,
                         oversight_actions.ACTIONS_LOG_PATH)
        self.assertEqual(redefinition_handler.REEVAL_QUEUE_PATH,
                         oversight_queue.REEVAL_QUEUE_PATH)
        self.assertIn(tool_events.global_sink_path(),
                      retention_sweeper.ROTATABLE_JSONL)

    def test_mcp_registry_and_scratch_come_from_runtime_paths(self):
        import code_execute
        import mcp_client
        self.assertEqual(mcp_client.WORKSPACE, runtime_paths.WORKSPACE)
        self.assertEqual(
            mcp_client.MCP_REGISTRY,
            os.path.join(runtime_paths.WORKSPACE, "config",
                         "mcp-servers.json"))
        self.assertEqual(
            code_execute.SCRATCH_DIR,
            os.path.join(runtime_paths.SCRATCH_DIR_STR, "code-exec"))

    def test_ora_home_env_override(self):
        # runtime_paths derives ORA_HOME from the env var.
        self.assertTrue(str(runtime_paths.ORA_HOME).endswith("ora")
                        or os.environ.get("ORA_HOME"))

    def test_watcher_family_roots_come_from_runtime_paths(self):
        # Phase 2: the watcher/heartbeat family moved onto runtime_paths
        # TOGETHER — a partial move would split pointer/state writers from
        # readers under an ORA_HOME relocation (the Revision 7 bug class).
        import corpus_watcher
        import oversight_health
        import oversight_router
        import ped_watcher
        import resources_watcher
        import revisit_sweeper
        import workflow_spec_sweeper
        oversight_root = os.path.join(runtime_paths.DATA_DIR_STR, "oversight")
        for mod in (ped_watcher, corpus_watcher, workflow_spec_sweeper,
                    revisit_sweeper, resources_watcher, oversight_health):
            self.assertEqual(mod.WORKSPACE, runtime_paths.WORKSPACE,
                             f"{mod.__name__}.WORKSPACE off runtime_paths")
            self.assertEqual(mod.OVERSIGHT_DATA_DIR, oversight_root,
                             f"{mod.__name__}.OVERSIGHT_DATA_DIR off root")
        self.assertEqual(oversight_router.WORKSPACE, runtime_paths.WORKSPACE)
        self.assertEqual(oversight_router.VAULT, runtime_paths.VAULT_STR)
        self.assertEqual(
            oversight_router.ROUTER_LOG_PATH,
            os.path.join(oversight_root, "router.jsonl"))

    def test_heartbeat_writers_agree_with_health_reader(self):
        # Every heartbeat producer must write exactly the file
        # oversight_health reads for it (the reader derives dash-separated
        # filenames from the underscore module keys in HEARTBEAT_INTERVALS).
        import corpus_watcher
        import maintenance_scheduler
        import mlx_mutex
        import oversight_health
        import ped_watcher
        import retention_sweeper
        import revisit_sweeper
        import resources_watcher
        import workflow_spec_sweeper
        for mod, key in (
            (ped_watcher, "ped_watcher"),
            (corpus_watcher, "corpus_watcher"),
            (workflow_spec_sweeper, "workflow_spec_sweeper"),
            (revisit_sweeper, "revisit_sweeper"),
            (retention_sweeper, "retention_sweeper"),
            (maintenance_scheduler, "maintenance_scheduler"),
            (resources_watcher, "resources_watcher"),
        ):
            self.assertEqual(mod.HEARTBEAT_FILE,
                             oversight_health.heartbeat_path(key),
                             f"{key} heartbeat writer/reader split")
        self.assertEqual(mlx_mutex._DEFAULT_HEARTBEAT_PATH,
                         oversight_health.heartbeat_path("mlx_worker"))

    def test_conversation_purge_roots_agree_with_writers(self):
        # Phase 2: the stealth purge's default roots and every writer that
        # produces the artifacts it deletes must flow from the same source
        # (envelope writer, job files, stealth doc uploads, vault export).
        from orchestrator import conversation_closeout as cc
        import conversation_memory
        import document_input
        import job_queue
        import vault_export
        sessions_root = runtime_paths.ORA_HOME / "sessions"
        self.assertEqual(cc._DEFAULT_SESSIONS_ROOT, sessions_root)
        self.assertEqual(conversation_memory._DEFAULT_SESSIONS_ROOT,
                         sessions_root)
        self.assertEqual(vault_export._DEFAULT_SESSIONS_ROOT, sessions_root)
        self.assertEqual(job_queue.DEFAULT_SESSIONS_ROOT, sessions_root)
        self.assertEqual(document_input.STEALTH_TEMP_ROOT, str(sessions_root))
        self.assertEqual(cc._DEFAULT_CONVERSATIONS_DIR,
                         runtime_paths.CONVERSATIONS)
        self.assertEqual(cc._DEFAULT_CONVERSATIONS_RAW,
                         vault_export._DEFAULT_RAW_CONVERSATIONS)
        self.assertEqual(cc._DEFAULT_VAULT_SESSIONS,
                         runtime_paths.VAULT / "Sessions")
        self.assertEqual(cc._DEFAULT_CHROMADB_PATH,
                         runtime_paths.ORA_HOME / "chromadb")

    def test_daily_note_roots_come_from_runtime_paths(self):
        # Phase 2: daily_note reconciled onto runtime_paths (ORA_VAULT);
        # ORA_VAULT_PATH remains a call-time override for backward compat.
        import daily_note
        self.assertEqual(daily_note.DATA_DIR, runtime_paths.DATA_DIR_STR)
        self.assertEqual(daily_note.CONVERSATIONS_DIR,
                         runtime_paths.CONVERSATIONS_STR)
        self.assertEqual(daily_note.SESSIONS_DIR,
                         os.path.join(runtime_paths.WORKSPACE, "sessions"))
        if not os.environ.get("ORA_VAULT_PATH"):
            self.assertEqual(daily_note.VAULT_PATH,
                             os.path.expanduser(runtime_paths.VAULT_STR))


# ══════════════════════════════════════════════════════════════════════════
# Phase 2-4 portability (this pass): write-containment boundary, root sourcing,
# server ORA_HOME bootstrap, slash-command repo root, _clean_env Windows vars,
# packet trace-path + risk_gate event-log encoding. These surfaces landed AFTER
# the Phase-1 portability hardening and were reviewed for correctness, not for
# Windows behavior.
# ══════════════════════════════════════════════════════════════════════════


class TestWithinBaseBoundary(unittest.TestCase):
    """runtime_paths.within_base / within_any_base: boundary-anchored +
    case-normalized containment. A raw ``resolved.startswith(base)`` treats a
    mere-prefix SIBLING as inside (``ora-project`` next to ``ora``) and ignores
    Windows case-insensitivity — both closed here."""

    def test_posix_self_descendant_and_sibling(self):
        home = os.path.expanduser("~")
        base = os.path.join(home, "ora")
        self.assertTrue(runtime_paths.within_base(base, base))                       # self
        self.assertTrue(runtime_paths.within_base(os.path.join(base, "config", "x"), base))  # descendant
        self.assertFalse(runtime_paths.within_base(os.path.join(home, "ora-worktrees", "x"), base))  # sibling-prefix
        self.assertFalse(runtime_paths.within_base(os.path.join(home, "orang", "x"), base))          # prefix
        self.assertFalse(runtime_paths.within_base(os.path.join(home, "elsewhere"), base))           # unrelated

    def test_within_any_base(self):
        home = os.path.expanduser("~")
        bases = [os.path.join(home, "ora"), os.path.join(home, "Documents", "vault")]
        self.assertTrue(runtime_paths.within_any_base(os.path.join(home, "Documents", "vault", "n.md"), bases))
        self.assertFalse(runtime_paths.within_any_base(os.path.join(home, "ora-x", "n.md"), bases))

    def test_windows_case_insensitive_and_sibling(self):
        # Simulate Windows normalization: norm_key becomes ntpath.normcase
        # (case-fold + backslashes), which within_base then '/'-normalizes.
        with mock.patch.object(runtime_paths, "norm_key",
                               side_effect=lambda p: ntpath.normcase(str(p))):
            base = r"C:\Users\bob\ora"
            self.assertTrue(runtime_paths.within_base(r"C:\Users\Bob\ORA\config\x.json", base))  # case
            self.assertTrue(runtime_paths.within_base(base, base))
            self.assertFalse(runtime_paths.within_base(r"C:\Users\bob\ora-project\x", base))      # sibling
            self.assertFalse(runtime_paths.within_base(r"D:\Users\bob\ora\x", base))              # other drive


class TestValidatePathContainment(unittest.TestCase):
    """dispatcher.validate_path + file_ops._validate_path: the write-containment
    boundary and the separator-normalized deny-list, on both platforms."""

    def test_dispatcher_blocks_posix_sibling_write(self):
        import dispatcher
        home = os.path.expanduser("~")
        ok, _ = dispatcher.validate_path(os.path.join(home, "ora", "config", "models.json"), "write")
        self.assertTrue(ok)
        ok, reason = dispatcher.validate_path(os.path.join(home, "ora-worktrees", "evil.txt"), "write")
        self.assertFalse(ok, reason)   # sibling of WORKSPACE must NOT be writable

    def test_fileops_blocks_posix_sibling_write(self):
        import file_ops
        home = os.path.expanduser("~")
        ok, _ = file_ops._validate_path(os.path.join(home, "ora", "notes.md"))
        self.assertTrue(ok)
        ok, reason = file_ops._validate_path(os.path.join(home, "ora-project", "evil.md"))
        self.assertFalse(ok, reason)

    def test_deny_list_matches_backslash_paths(self):
        # A Windows-shaped secret path must hit the '/'-shaped DENY_LIST patterns
        # once separators are normalized — a raw resolved.lower() substring test
        # would miss `.aws/credentials` on a backslash path.
        import dispatcher, file_ops
        for p in (r"C:\Users\alice\.aws\credentials",
                  r"C:\Users\alice\.ssh\id_rsa",
                  r"C:\Users\alice\.gnupg\secring"):
            ok, _ = dispatcher.validate_path(p, "read")
            self.assertFalse(ok, p)
            ok, _ = file_ops._validate_path(p)
            self.assertFalse(ok, p)

    def test_path_with_spaces_within_base_allowed(self):
        import dispatcher
        home = os.path.expanduser("~")
        ok, reason = dispatcher.validate_path(
            os.path.join(home, "ora", "my notes", "a file.md"), "write")
        self.assertTrue(ok, reason)


class TestFileOpsRootsFromRuntimePaths(unittest.TestCase):
    """file_ops core roots come from runtime_paths (honor ORA_HOME / a
    relocation), not the old hardcoded ~/ora, ~/Documents defaults."""

    def test_roots_agree_with_runtime_paths(self):
        import file_ops
        self.assertEqual(file_ops.WORKSPACE, runtime_paths.WORKSPACE)
        self.assertEqual(file_ops.VAULT, runtime_paths.VAULT_STR)
        self.assertEqual(file_ops.CONVERSATIONS, runtime_paths.CONVERSATIONS_STR)

    def test_no_hardcoded_user_path_in_source(self):
        src = (_ORCH / "tools" / "file_ops.py").read_text()
        self.assertNotIn("/Users/", src)
        self.assertNotIn('expanduser("~/ora', src)


class TestCleanEnvWindowsVars(unittest.TestCase):
    """bash_execute._clean_env must propagate the Windows-essential system
    variables (SystemRoot etc.) — without %SystemRoot% even a declared POSIX
    shell fails to spawn on Windows (DLL load) — while leaving POSIX identical."""

    def test_windows_propagates_system_vars(self):
        import bash_execute
        fake = {"PATH": r"C:\Windows;C:\Windows\System32",
                "SystemRoot": r"C:\Windows", "SystemDrive": "C:",
                "windir": r"C:\Windows", "COMSPEC": r"C:\Windows\System32\cmd.exe",
                "PATHEXT": ".COM;.EXE;.BAT", "TEMP": r"C:\Users\a\AppData\Local\Temp",
                "USERPROFILE": r"C:\Users\a"}
        with mock.patch.object(os, "name", "nt"), \
             mock.patch.dict(os.environ, fake, clear=True):
            env = bash_execute._clean_env()
        for k in ("SystemRoot", "SystemDrive", "windir", "COMSPEC", "PATHEXT",
                  "TEMP", "USERPROFILE"):
            self.assertEqual(env.get(k), fake[k], k)

    def test_posix_env_unchanged(self):
        import bash_execute
        with mock.patch.object(os, "name", "posix"), \
             mock.patch.dict(os.environ, {"PATH": "/usr/bin", "HOME": "/home/a"},
                             clear=True):
            env = bash_execute._clean_env()
        # No Windows keys leak into a POSIX environment.
        for k in ("SystemRoot", "COMSPEC", "PATHEXT", "windir"):
            self.assertNotIn(k, env)
        self.assertEqual(env.get("PATH"), "/usr/bin")


class TestServerRootHonorsOraHome(unittest.TestCase):
    """server.py's WORKSPACE / CONVERSATIONS_DIR must derive from ORA_HOME /
    ORA_CONVERSATIONS (Windows installs + relocations), not a hardcoded ~/ora.
    Run in a subprocess so the module-level bootstrap is exercised fresh with
    the env set — independent of whether another test already imported server."""

    def test_workspace_and_conversations_relocate(self):
        import json
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory(prefix="ora home ") as ora_home, \
             tempfile.TemporaryDirectory(prefix="ora conv ") as ora_conv:
            boot = (
                "import sys, os, json\n"
                f"REPO = {str(_REPO)!r}\n"
                "for p in (os.path.join(REPO,'orchestrator','tools'), "
                "os.path.join(REPO,'orchestrator'), os.path.join(REPO,'server'), REPO):\n"
                "    sys.path.insert(0, p)\n"
                "import server\n"
                "print('RESULT ' + json.dumps({'ws': server.WORKSPACE, "
                "'conv': server.CONVERSATIONS_DIR}))\n"
            )
            env = dict(os.environ)
            env.update({"ORA_HOME": ora_home, "ORA_CONVERSATIONS": ora_conv,
                        "ORA_TOOL_EVENTS": "off", "ORA_PIPELINE_TRACE": "off"})
            proc = subprocess.run([sys.executable, "-c", boot], env=env,
                                  capture_output=True, text=True, timeout=180)
            marker = [l for l in proc.stdout.splitlines() if l.startswith("RESULT ")]
            self.assertTrue(marker, f"server import failed:\nSTDOUT{proc.stdout}\nSTDERR{proc.stderr}")
            data = json.loads(marker[0][len("RESULT "):])
        # Both roots honor the relocated env (path with a space, too).
        self.assertEqual(os.path.realpath(data["ws"]), os.path.realpath(ora_home))
        self.assertEqual(os.path.realpath(data["conv"]), os.path.realpath(ora_conv))


class TestSlashCommandRepoRoot(unittest.TestCase):
    """slash_commands historical-tool import fallbacks must use a __file__-derived
    repo root, never a hardcoded /Users/<name>/ora path."""

    def test_ora_root_is_file_derived(self):
        import slash_commands
        expected = os.path.dirname(os.path.dirname(os.path.abspath(slash_commands.__file__)))
        self.assertEqual(slash_commands._ORA_ROOT, expected)

    def test_no_hardcoded_user_path_in_source(self):
        src = (_ORCH / "slash_commands.py").read_text()
        self.assertNotIn("/Users/oracle/ora", src)


class TestExecutionPacketTracePathPortable(unittest.TestCase):
    """execution_packet.write_packet builds its path with os.path.join and
    writes UTF-8 — a trace dir with spaces / nested segments and a non-ASCII
    deliverable must round-trip."""

    def test_write_and_read_back_with_spaces_and_unicode(self):
        import json
        import tempfile
        import execution_packet as ep
        with tempfile.TemporaryDirectory(prefix="ora trace ") as td:
            trace = os.path.join(td, "conv 1", "ts 2")   # spaces + nesting
            signals = {"any_mutation": True, "max_mutability": "reversible_write",
                       "source_read_suspected": False, "source_candidate_reads": []}
            ref = ep.construct_and_write(
                signals=signals, context_pkg={"conversation_id": "c1"},
                output_text="a real deliverable body — café / 例文",
                risk_tier="standard", trace_dir=trace)
            self.assertTrue(ref and os.path.exists(ref), ref)
            with open(ref, encoding="utf-8") as f:
                data = json.load(f)
        self.assertEqual(data["risk_tier"], "standard")
        self.assertEqual(data["execution"]["delta"]["max_mutability"], "reversible_write")


class TestRiskGateEventLogEncoding(unittest.TestCase):
    """risk_gate reads the tool-event log and the sticky store as UTF-8, so a
    non-ASCII path/URL in the log (or a relocated DATA_DIR) never crashes the
    fold on a non-UTF-8 default-locale host (Windows)."""

    def test_fold_reads_utf8_event_log(self):
        import json
        import tempfile
        import risk_gate as rgate
        with tempfile.TemporaryDirectory() as td:
            ev = os.path.join(td, "tool-events.jsonl")
            with open(ev, "w", encoding="utf-8") as f:
                # ensure_ascii=False → real multibyte UTF-8 bytes on disk.
                f.write(json.dumps({
                    "action": "web_fetch", "mutability": "read",
                    "reads": [{"what": "https://例え.jp/café", "where": "network"}],
                    "exit": {"ok": True}, "sensitivity": "public", "mutated": False,
                }, ensure_ascii=False) + "\n")
            sig = rgate.fold_route_observed(ev, output_text="a substantive grounded answer body")
        self.assertTrue(sig["source_read_suspected"])
        self.assertIn("web_fetch", sig["source_read_channels"])

    def test_sticky_round_trip_relocated_data_dir(self):
        import tempfile
        import risk_gate as rgate
        with tempfile.TemporaryDirectory(prefix="ora data ") as td:
            sticky = os.path.join(td, "risk-sticky.json")
            with mock.patch.object(rgate, "_sticky_path", lambda: sticky):
                rgate.set_sticky("conv-1", "high-risk")
                self.assertEqual(rgate.get_sticky("conv-1"), "high-risk")
                rgate.set_sticky("conv-1", "auto")            # clear
                self.assertIsNone(rgate.get_sticky("conv-1"))


class TestWindowsSimSinkWriteStaysHostNative(unittest.TestCase):
    """Regression (2026-07-12): a durable sink write under a Windows-simulating
    ``os.name='nt'`` monkeypatch must land on the real host-native path and must
    NEVER create a literal backslash-named file in cwd.

    Before the fix, ``append_bytes_no_follow`` did ``target = Path(path)`` —
    which under the patched ``os.name`` became a ``WindowsPath`` whose fspath
    ``\\var\\...\\tool-events.jsonl`` is *relative* on POSIX, so the real
    ``os.open`` wrote it into the current directory (the repo root). The D-01 /
    D-03 Windows-sim evidence-runner tests leaked exactly that file into ~/ora.
    Each test chdirs into a throwaway dir so a regression litters the temp dir,
    never the checkout."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp(prefix="ora-wsim-cwd-")
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _cwd_backslash_files(self):
        return [n for n in os.listdir(".") if "\\" in n]

    def test_append_bytes_under_simulated_windows_is_host_native(self):
        with tempfile.TemporaryDirectory(prefix="ora-sink-") as box:
            target = os.path.join(box, "tool-events.jsonl")  # forward-slash str
            with mock.patch.object(os, "name", "nt"):
                runtime_paths.append_bytes_no_follow(
                    target, b'{"event":"x"}\n', mode=0o644)
            self.assertTrue(os.path.exists(target), target)
            with open(target, "rb") as f:
                self.assertIn(b'"event":"x"', f.read())
        self.assertEqual(self._cwd_backslash_files(), [],
                         "a backslash file leaked into cwd under os.name='nt'")

    def test_guard_refuses_reflavored_windows_path_on_posix(self):
        # Reproduce the reflavored path a WindowsPath yields on POSIX, then hand
        # it to the durable writer + lock helper: both must refuse loudly rather
        # than write a literal backslash-named file in cwd.
        with mock.patch.object(os, "name", "nt"):
            reflavored = Path("/var/folders/T/box/tool-events.jsonl")
        self.assertIn("\\", os.fspath(reflavored))          # sanity: '\var\...'
        self.assertFalse(reflavored.is_absolute())          # relative on POSIX
        with self.assertRaises(ValueError):
            runtime_paths.append_bytes_no_follow(reflavored, b"x\n")
        with self.assertRaises(ValueError):
            with runtime_paths.locked_file(reflavored):
                pass
        self.assertEqual(self._cwd_backslash_files(), [])

    def test_record_end_to_end_under_simulated_windows_stays_clean(self):
        # The exact original failure signature: os.name='nt' + an armed sandbox
        # + a real tool_events.record() write. The event must land in the
        # forward-slash sandbox and cwd must stay clean.
        with tempfile.TemporaryDirectory(prefix="ora-sandbox-") as box:
            with mock.patch.dict(
                    os.environ,
                    {runtime_paths.OVERSIGHT_SANDBOX_ENV: box,
                     "ORA_TOOL_EVENTS": ""}, clear=False), \
                    mock.patch.object(os, "name", "nt"):
                tool_events.record({
                    "event": "unit-test", "action": "probe",
                    "mutability": "read", "sensitivity": "public"})
            sink = os.path.join(box, "tool-events.jsonl")
            self.assertTrue(os.path.exists(sink),
                            "event did not land in the forward-slash sandbox")
            with open(sink) as f:
                self.assertIn("unit-test", f.read())
        self.assertEqual(self._cwd_backslash_files(), [],
                         "record() leaked a backslash file into cwd")


if __name__ == "__main__":
    unittest.main()
