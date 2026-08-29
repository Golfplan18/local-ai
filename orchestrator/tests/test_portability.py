"""Cross-platform (macOS + Windows) portability tests for the Execution
Review Phase 1 instrumentation. These run on macOS/Linux CI and simulate
Windows via ntpath/PureWindowsPath and platform monkeypatching — no Windows
host required. Covers the judge's portability conditions."""

from __future__ import annotations

import contextlib
import json
import ntpath
import os
import re
import shutil
import subprocess
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
        from orchestrator import runtime_hygiene, triggers
        self.assertFalse(hasattr(runtime_hygiene, "fcntl"))
        self.assertFalse(hasattr(triggers, "fcntl"))

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

    def test_runtime_lock_consumers_use_windows_primitive_and_same_sidecars(self):
        from orchestrator import runtime_hygiene, triggers

        calls = []

        class _FakeMsvcrt:
            LK_NBLCK = 1
            LK_UNLCK = 2

            def locking(self, fd, mode, nbytes):
                calls.append(mode)

        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(runtime_paths, "_fcntl", None), \
             mock.patch.object(runtime_paths, "_msvcrt", _FakeMsvcrt()), \
             mock.patch.object(triggers._rp, "DATA_DIR_STR", tmp):
            hygiene_lock = Path(tmp) / ".event-ledger.lock"
            with runtime_hygiene._exclusive(hygiene_lock):
                pass
            with triggers._exclusive():
                pass

            trigger_lock = Path(tmp) / "triggers" / ".triggers.lock"
            self.assertTrue(hygiene_lock.is_file())
            self.assertTrue(trigger_lock.is_file())
            self.assertFalse(Path(str(hygiene_lock) + ".lock").exists())
            self.assertFalse(Path(str(trigger_lock) + ".lock").exists())

        self.assertEqual(calls, [1, 2, 1, 2])

    def test_runtime_lock_consumers_surface_contention_timeout(self):
        from orchestrator import runtime_hygiene, triggers

        @contextlib.contextmanager
        def contended(_path, timeout=runtime_paths.DEFAULT_LOCK_TIMEOUT):
            raise TimeoutError(f"lock remained contended for {timeout}s")
            yield  # pragma: no cover

        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(runtime_paths, "locked_file", contended), \
             mock.patch.object(triggers._rp, "DATA_DIR_STR", tmp):
            with self.assertRaisesRegex(TimeoutError, "remained contended"):
                with runtime_hygiene._exclusive(Path(tmp) / ".event-ledger.lock"):
                    pass
            with self.assertRaisesRegex(TimeoutError, "remained contended"):
                with triggers._exclusive():
                    pass

    def test_locked_file_without_any_primitive_does_not_crash(self):
        with mock.patch.object(runtime_paths, "_fcntl", None), \
             mock.patch.object(runtime_paths, "_msvcrt", None):
            tmp = os.path.join(tempfile.mkdtemp(), "x.json")
            with runtime_paths.locked_file(tmp):
                with open(tmp, "w") as _f:
                    _f.write("1")
        with open(tmp) as _f:
            self.assertEqual(_f.read(), "1")


class TestCrossPlatformDirectArgv(unittest.TestCase):
    """Commands are modeled and executed as argv on every platform.

    The former Windows POSIX-shell compatibility layer is intentionally gone:
    it would reinterpret the model string after classification.  Windows still
    receives its native executable directly with ``shell=False``.
    """

    def test_declaring_a_shell_cannot_enable_shell_grammar(self):
        import bash_execute
        with mock.patch.dict(
            os.environ, {"ORA_POSIX_SHELL": r"C:\\Git\\bin\\bash.exe"},
        ):
            profile = bash_execute.resolve_shell_profile("echo one && echo two")
        self.assertTrue(profile["unknown"])
        self.assertIn("shell operators", profile["reason"])

    def test_windows_quoted_paths_follow_native_direct_argv_rules(self):
        import bash_execute
        command = (
            r'"C:\Program Files\Git\cmd\git.exe" '
            r'-C "C:\Users\Ora User\repo" status --short '
            r'"literal\\\"quote"'
        )
        self.assertEqual(
            bash_execute._split_windows_command_line_fallback(command),
            [
                r"C:\Program Files\Git\cmd\git.exe",
                "-C",
                r"C:\Users\Ora User\repo",
                "status",
                "--short",
                'literal\\"quote',
            ],
        )

    def test_windows_foreground_uses_prepared_argv_without_shell(self):
        import bash_execute
        prepared = bash_execute.prepare_command("echo hi")
        completed = mock.Mock(stdout="hi\n", stderr="", returncode=0)
        with mock.patch.object(os, "name", "nt"), \
             mock.patch.object(
                 bash_execute.subprocess, "run", return_value=completed,
             ) as run:
            result = bash_execute.execute_command(prepared)
        args, kwargs = run.call_args
        self.assertEqual(args[0], list(prepared.argv))
        self.assertIs(kwargs["shell"], False)
        self.assertEqual(result["returncode"], 0)

    def test_windows_background_uses_prepared_argv_without_shell(self):
        import bash_execute
        prepared = bash_execute.prepare_command("sleep 5")
        process = mock.Mock(pid=4242)
        process.poll.return_value = None
        before = list(bash_execute.MANAGED_PROCESSES)
        try:
            with mock.patch.object(os, "name", "nt"), \
                 mock.patch.object(
                     bash_execute.subprocess, "Popen", return_value=process,
                 ) as popen:
                result = bash_execute.execute_command(prepared, background=True)
            args, kwargs = popen.call_args
            self.assertEqual(args[0], list(prepared.argv))
            self.assertIs(kwargs["shell"], False)
            self.assertEqual(result["pid"], 4242)
        finally:
            bash_execute.MANAGED_PROCESSES[:] = before

    def test_ampersand_is_refused_instead_of_becoming_background(self):
        import bash_execute
        with mock.patch.object(bash_execute.subprocess, "Popen") as popen:
            result = bash_execute.execute_command("sleep 5 &", background=True)
        popen.assert_not_called()
        self.assertIsNone(result["pid"])
        self.assertIn("not executed", result["status"])


# Config files that are deliberately machine-specific and gitignored, so a
# real absolute path in them is correct rather than a leak (CLAUDE.md:
# "config/models.json is machine-specific and gitignored"; the same holds
# for the ChromaDB collection binding). Only consulted when git can't be
# asked which files are actually checked in.
_MACHINE_LOCAL_CONFIGS = {"models.json", "chromadb.json"}


def _tracked_config_files(suffix: str) -> list[Path] | None:
    """Files under config/ ending in ``suffix`` that git reports as tracked.

    ``None`` when git cannot be asked at all (a source tarball, a vendored
    copy), so each caller can fall back to its own filesystem walk."""
    try:
        out = subprocess.run(
            ["git", "-C", str(_ORCH.parent), "ls-files", "--", "config"],
            capture_output=True, text=True, timeout=30, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    tracked = [_ORCH.parent / line for line in out.splitlines()
               if line.endswith(suffix)]
    return tracked or None


def _checked_in_config_json() -> list[Path]:
    """Every JSON file under config/ that ships with the repository.

    Prefers git's own answer, so a newly added machine-local config is
    excluded the moment it's gitignored, and falls back to a filesystem
    walk minus the known machine-local names when git isn't available
    (a source tarball, a vendored copy)."""
    tracked = _tracked_config_files(".json")
    if tracked is not None:
        return tracked
    config_dir = _ORCH.parent / "config"
    return [p for p in sorted(config_dir.rglob("*.json"))
            if p.name not in _MACHINE_LOCAL_CONFIGS]


def _checked_in_config_markdown() -> list[Path]:
    """Every Markdown file under config/ that ships with the repository.

    Same shipped-configuration surface as the JSON above, different file
    type: the generated indexes and the visual-schema guides are read into
    a model's context window verbatim. Nothing policed them — the config
    sweep parses JSON, and the portability linter's users-oracle rule only
    inspects code extensions — which is how 69 lines of the packager's home
    directory rode along in framework-library-index.md,
    rag-manifest-compiled.md, and visual-schemas/README.md."""
    tracked = _tracked_config_files(".md")
    if tracked is not None:
        return tracked
    return sorted((_ORCH.parent / "config").rglob("*.md"))


_HOME_ROOTED_TEXT = re.compile(r"/Users/|/home/|[A-Za-z]:\\Users")


def _home_rooted_strings(node, trail="$"):
    """Yield (json path, value) for every string holding somebody's home
    directory — POSIX ``/Users/x`` or ``/home/x``, or Windows ``C:\\Users``."""
    if isinstance(node, str):
        if ("/Users/" in node or "/home/" in node
                or re.search(r"[A-Za-z]:\\Users", node)):
            yield trail, node
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _home_rooted_strings(item, f"{trail}[{i}]")
    elif isinstance(node, dict):
        for key, item in node.items():
            yield from _home_rooted_strings(item, f"{trail}.{key}")


class TestMcpConfigPortability(unittest.TestCase):
    """Revision 7 [P1]: the checked-in MCP registry carries no machine- or
    platform-specific absolute paths; placeholders resolve at launch through
    env overrides / runtime_paths."""

    def _registry(self):
        import json
        with open(_ORCH.parent / "config" / "mcp-servers.json") as f:
            return json.load(f)

    def test_no_hardcoded_user_paths_in_checked_in_config(self):
        # The MCP registry, field by field — the original expectation.
        for server in self._registry()["servers"]:
            for arg in server.get("args", []):
                self.assertFalse(arg.startswith("/Users/"), arg)
                self.assertFalse(arg.startswith("/home/"), arg)
                self.assertNotIn(":\\Users", arg)
            cmd = server.get("command", "")
            self.assertFalse(cmd.startswith("/Users/"), cmd)

        # Every OTHER checked-in config the running system loads, whole-file.
        # The registry was the only file this ever policed, so the packager's
        # own home directory shipped in routing-config.json (six local
        # model_paths, the vault / conversations / chromadb roots) and in
        # capabilities.json — none of which exist on anyone else's machine.
        # Placeholders belong in these files; absolute home paths do not.
        offenders = []
        for path in _checked_in_config_json():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue  # unreadable/non-JSON is another test's problem
            for trail, value in _home_rooted_strings(loaded):
                offenders.append(
                    f"{path.relative_to(_ORCH.parent)} {trail} = {value!r}")
        self.assertEqual(
            offenders, [],
            "checked-in config carries a home-directory path; use a "
            "${ORA_HOME} / ${ORA_VAULT} / ${ORA_CONVERSATIONS} / "
            "${ORA_CHROMADB} placeholder and let the loader expand it:\n  "
            + "\n  ".join(offenders))

    def test_no_hardcoded_user_paths_in_checked_in_config_markdown(self):
        """The same rule, applied to config/'s Markdown.

        `framework-library-index.md` and `rag-manifest-compiled.md` are
        written by scripts/generate-indexes.sh and
        scripts/compile-rag-manifest.sh and are handed to a model as
        context, so a packager's home directory in them ships to every
        clone and describes a tree that clone does not have. Fixing the
        files is only half the fix — a generator still pinned to the
        packager's layout puts the paths straight back on the next run."""
        offenders = []
        for path in _checked_in_config_markdown():
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if _HOME_ROOTED_TEXT.search(line):
                    offenders.append(
                        f"{path.relative_to(_ORCH.parent)}:{lineno}: "
                        f"{line.strip()[:110]}")
        self.assertEqual(
            offenders, [],
            "checked-in config Markdown carries a home-directory path; "
            "emit it relative to the workspace root or as a ${ORA_HOME} "
            "placeholder, and fix the generator that wrote it:\n  "
            + "\n  ".join(offenders))

    def test_runtime_configs_use_placeholders_and_expand(self):
        """The two configs that carried the author's paths now carry
        placeholders — and those placeholders resolve to the RUNNING
        install, not to a baked location."""
        config_dir = _ORCH.parent / "config"
        routing = json.loads(
            (config_dir / "routing-config.json").read_text(encoding="utf-8"))
        locals_ = [ep for ep in routing.get("endpoints", [])
                   if ep.get("type") == "local" and ep.get("model_path")]
        self.assertTrue(locals_, "no local endpoints to check")
        for endpoint in locals_:
            self.assertTrue(
                endpoint["model_path"].startswith("${ORA_HOME}"),
                endpoint["model_path"])

        relocated = os.path.join(os.sep, "opt", "ora clone")
        with mock.patch.dict(os.environ, {"ORA_HOME": relocated}):
            expanded = runtime_paths.expand_placeholders(routing)
        for endpoint in expanded["endpoints"]:
            if endpoint.get("type") == "local" and endpoint.get("model_path"):
                self.assertTrue(
                    endpoint["model_path"].startswith(relocated),
                    endpoint["model_path"])

        capabilities = json.loads(
            (config_dir / "capabilities.json").read_text(encoding="utf-8"))
        self.assertTrue(
            capabilities["_canonical_source"].startswith("${ORA_VAULT}"),
            capabilities["_canonical_source"])

    def test_routing_config_loaders_expand_placeholders(self):
        """boot and the Router are the two loaders that turn a local
        endpoint's model_path into a filesystem path; both must expand."""
        import boot
        rc = boot.load_routing_config()
        for endpoint in rc.get("endpoints", []):
            self.assertNotIn("${ORA_", str(endpoint.get("model_path") or ""))

        from router import Router
        router = Router()
        for endpoint in router.config.get("endpoints", []):
            self.assertNotIn("${ORA_", str(endpoint.get("model_path") or ""))

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
        # Reader mode mirrors connect(): binary so byte limits and strict
        # UTF-8 validation happen before JSON parsing.
        conn = mcp_client.MCPConnection(name="test-pipe", command="unused")
        conn.process = types.SimpleNamespace(
            stdout=os.fdopen(r, "rb"))
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

    def test_bad_bytes_fail_connection_before_json_parse(self):
        conn, writer = self._make_pipe_connection(binary_writer=True)
        try:
            writer.write(b"\xff\xfe garbage \x9d\n")
            writer.flush()
            with self.assertRaisesRegex(Exception, "invalid UTF-8"):
                conn._recv(timeout=5)
        finally:
            writer.close()

    def test_popen_uses_binary_stdio_for_predecode_byte_bounds(self):
        import mcp_client
        with mock.patch.object(mcp_client.subprocess, "Popen",
                               side_effect=RuntimeError("stop")) as m:
            conn = mcp_client.MCPConnection(name="t", command="unused")
            self.assertFalse(conn.connect())
        kwargs = m.call_args.kwargs
        self.assertIs(kwargs.get("text"), False)
        self.assertNotIn("encoding", kwargs)
        self.assertNotIn("errors", kwargs)

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

    def test_timeout_input_is_finite_and_bounded(self):
        import code_execute
        self.assertEqual(code_execute._normalize_timeout(None),
                         code_execute.DEFAULT_TIMEOUT_SECONDS)
        self.assertEqual(code_execute._normalize_timeout("not-a-timeout"),
                         code_execute.DEFAULT_TIMEOUT_SECONDS)
        self.assertEqual(code_execute._normalize_timeout(float("nan")),
                         code_execute.DEFAULT_TIMEOUT_SECONDS)
        self.assertEqual(code_execute._normalize_timeout(float("inf")),
                         code_execute.MAX_TIMEOUT_SECONDS)
        self.assertEqual(code_execute._normalize_timeout(10**100),
                         code_execute.MAX_TIMEOUT_SECONDS)
        self.assertEqual(code_execute._normalize_timeout(-1),
                         code_execute.DEFAULT_TIMEOUT_SECONDS)


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
        # Inside the ACTIVE workspace, not a hard-coded ~/ora: from a
        # worktree the literal wrote scratch into the live install and
        # then failed because those files were outside its own base.
        import dispatcher as _d
        root = tempfile.mkdtemp(dir=str(_d.WORKSPACE))
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
        ws = Path(dispatcher.WORKSPACE).resolve()
        ok, _ = dispatcher.validate_path(str(ws / "config" / "models.json"), "write")
        self.assertTrue(ok)
        # A sibling whose name EXTENDS the workspace name is the collision a
        # naive prefix check would wrongly allow ("~/ora" prefixes
        # "~/ora-worktrees"). Built from the real root so it holds anywhere.
        sibling = ws.parent / (ws.name + "-worktrees") / "evil.txt"
        ok, reason = dispatcher.validate_path(str(sibling), "write")
        self.assertFalse(ok, reason)   # sibling of WORKSPACE must NOT be writable

    def test_fileops_blocks_posix_sibling_write(self):
        import file_ops
        ws = Path(file_ops._rp.ORA_HOME).resolve()
        ok, _ = file_ops._validate_path(str(ws / "notes.md"))
        self.assertTrue(ok)
        sibling = ws.parent / (ws.name + "-project") / "evil.md"
        ok, reason = file_ops._validate_path(str(sibling))
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
        ws = Path(dispatcher.WORKSPACE).resolve()
        ok, reason = dispatcher.validate_path(
            str(ws / "my notes" / "a file.md"), "write")
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
    """The clean argv environment keeps only Windows process essentials.

    In particular USERPROFILE is excluded: inheriting it lets Git and provider
    tools rediscover ambient credentials/configuration outside the reviewed
    command authority.
    """

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
                  "TEMP"):
            self.assertEqual(env.get(k), fake[k], k)
        self.assertNotIn("USERPROFILE", env)

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
                "from server import app as server\n"
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
        # No absolute home-rooted path of ANY user — stricter than the
        # single packager path this used to name, and it keeps the source
        # of the assertion free of one itself. Comments are excluded: the
        # module explains in prose why it does NOT use such a path.
        code = "\n".join(line for line in src.splitlines()
                         if not line.lstrip().startswith("#"))
        self.assertNotIn("/Users/", code)
        self.assertNotIn("/home/", code)


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
