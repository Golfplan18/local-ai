"""Regression tests for Ora's consolidated server launch paths."""

from __future__ import annotations

import ast
import http.server
import json
import os
import plistlib
import re
import subprocess
import sys
import threading
import shutil
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "run-ora-server.sh"
START = ROOT / "start.sh"
STOP = ROOT / "stop.sh"
PLIST_TEMPLATE = ROOT / "installer" / "macos" / "com.ora.server.plist.template"
APP_LAUNCHER = ROOT / "installer" / "macos" / "ora-app-launcher.sh"
SWAP_ICON = ROOT / "swap-icon.sh"
SERVICE_MANAGER = ROOT / "scripts" / "ora-launchd.sh"
SERVER = ROOT / "server" / "app.py"
START_BAT = ROOT / "start.bat"
STOP_BAT = ROOT / "stop.bat"
INSTALLER = ROOT / "scripts" / "install.py"
GITIGNORE = ROOT / ".gitignore"
GITATTRIBUTES = ROOT / ".gitattributes"
LAUNCH_EXAMPLE = ROOT / ".claude" / "launch.json.example"

RUNTIME_FLAGS = {
    "ORA_RAG_SELECTION": "1",
    "ORA_RAG_FIT_GATE_SLOT": "sidebar",
    "ORA_WEB_EXTRACTION": "1",
    "ORA_RUNTIME_ENGRAM_PROMOTION": "1",
    "ORA_RUNTIME_ENGRAM_AUTOCOMMIT": "1",
    "ORA_DELIVERABLE_SCRUB": "1",
    "ORA_OR_STATS": "1",
    "ORA_EXECUTION_LOOP": "1",
}


def _bat_source(path: Path) -> str:
    """Read a batch file with its real line endings left in place.

    `read_text` opens in universal-newline mode, which turns every CRLF into a
    bare LF before any assertion below ever sees it. That would hide the one
    thing the batch files must get right — cmd.exe needs CRLF — and it would
    let the byte-identity check pass on two blocks whose line endings differ.
    """
    return path.read_bytes().decode("utf-8")


def _bat_shared_block(source: str, name: str) -> str | None:
    """Return the body of a `REM ---- shared: <name> ----` block, or None.

    start.bat and stop.bat carry these blocks byte-identical so the two scripts
    cannot drift into disagreeing about which process belongs to this checkout.
    The markers tolerate either line ending, but the body is returned exactly as
    it appears on disk, so comparing two bodies compares their endings too.
    """
    match = re.search(
        rf"^REM ---- shared: {re.escape(name)} ----\r?\n"
        rf"(.*?)"
        rf"^REM ---- end shared: {re.escape(name)} ----\r?$",
        source,
        re.DOTALL | re.MULTILINE,
    )
    return match.group(1) if match else None


def _bat_server_files(source: str) -> set[str]:
    """Every `server\\<name>.py` a batch launcher names, as repo-relative paths."""
    return {
        found.replace("\\", "/")
        for found in re.findall(r"\\(server\\[A-Za-z0-9_.-]+\.py)", source)
    }


WINDOWS_TARGET = "C:\\ora\\server\\app.py"
WINDOWS_TARGET_WITH_SPACE = "C:\\Users\\Jane Doe\\ora\\server\\app.py"

# Command lines a Windows box can plausibly be running, and whether stop.bat is
# entitled to kill each one. Only a process the launcher itself started is.
WINDOWS_STOP_CASES = (
    (f"python -m py_compile {WINDOWS_TARGET}", False),
    (f"python -m pytest {WINDOWS_TARGET}", False),
    (f"python C:\\tools\\fmt.py {WINDOWS_TARGET}", False),
    (f"notepad {WINDOWS_TARGET}", False),
    (f"python {WINDOWS_TARGET}.bak --oversight", False),
    (WINDOWS_TARGET, False),
    (f"python {WINDOWS_TARGET}", True),
    (f"C:\\ora\\.venv\\Scripts\\python.exe {WINDOWS_TARGET}", True),
    (f"C:\\Python311\\python3.11.exe -u {WINDOWS_TARGET} --oversight --no-open", True),
)

# The same nine shapes as a POSIX `ps` line. Windows command lines quote an
# argument containing a space; `ps` output does not, so the shape "a path with a
# space in it" is the quoted case on one side and the bare case on the other.
POSIX_TARGET = "/ora/server/app.py"
POSIX_STOP_CASES = (
    (f"python -m py_compile {POSIX_TARGET}", POSIX_TARGET),
    (f"python -m pytest {POSIX_TARGET}", POSIX_TARGET),
    (f"python /tools/fmt.py {POSIX_TARGET}", POSIX_TARGET),
    (f"vim {POSIX_TARGET}", POSIX_TARGET),
    (f"python {POSIX_TARGET}.bak --oversight", POSIX_TARGET),
    (POSIX_TARGET, POSIX_TARGET),
    (f"python {POSIX_TARGET}", POSIX_TARGET),
    (f"/ora/.venv/bin/python3 {POSIX_TARGET}", POSIX_TARGET),
    (f"/usr/bin/python3.11 -u {POSIX_TARGET} --oversight --no-open", POSIX_TARGET),
)

# Quoting is Windows-only, so these have no `ps` counterpart to compare against.
WINDOWS_QUOTED_STOP_CASES = (
    (f'"C:\\Python311\\python.exe" "{WINDOWS_TARGET_WITH_SPACE}" --oversight', True),
    (f'python -m py_compile "{WINDOWS_TARGET_WITH_SPACE}"', False),
    (f'python "C:\\tools\\fmt.py" "{WINDOWS_TARGET_WITH_SPACE}"', False),
)


def _windows_stop_matches(block: str, command_line: str, target: str) -> bool:
    """Would the shipped PowerShell predicate kill this process?

    Windows is not available here and neither is PowerShell, so this is a hand
    translation of the one-liner in the `ora-stop-owned-server` block, statement
    for statement. The interpreter pattern is read out of the block rather than
    repeated, so the assertion cannot drift away from what actually ships; the
    test above pins the surrounding statements textually for the same reason.
    """
    interpreter = re.search(r"-notmatch '([^']+)'", block)
    assert interpreter, "the stop block no longer tests the preceding argument"
    target = target.lower()
    line = command_line.lower()
    position = line.find(target)                        # IndexOf($target, Ordinal)
    if position < 0:
        return False
    before = line[:position]                            # Substring(0, $pos)
    after = line[position + len(target):]               # Substring($pos + Length)
    if before.endswith('"') != after.startswith('"'):   # quotes have to pair
        return False
    if after.startswith('"'):
        before = before[:-1]
        after = after[1:]
    if len(after) > 0 and not after.startswith(" "):    # the path ends its argument
        return False
    parts = before.replace('"', "").rstrip().replace("/", "\\").split("\\")
    return re.match(interpreter.group(1), parts[-1]) is not None


def _posix_stop_awk_program() -> str:
    """The awk program stop.sh really runs, lifted out of the script."""
    match = re.search(r"awk '(.*?)'\)\"", STOP.read_text(encoding="utf-8"), re.DOTALL)
    assert match, "stop.sh no longer selects processes with awk"
    return match.group(1)


def _posix_stop_matches(program: str, command_line: str, target: str) -> bool:
    completed = subprocess.run(
        ["awk", program],
        input=f"4242 {command_line}\n",
        text=True,
        capture_output=True,
        env={"ORA_STOP_SERVER_TARGET": target, "PATH": "/usr/bin:/bin"},
        check=False,
    )
    assert not completed.stderr.strip(), completed.stderr
    return completed.stdout.split() == ["4242"]


def _bat_stop_outcome(source: str, code: int) -> dict:
    """Walk stop.bat's `if "!STOP_RC!"==...` chain the way cmd.exe would.

    Returns what the operator is told, and what the script exits with, for one
    exit code out of the shared stop block.
    """
    lines = [line.rstrip("\r") for line in source.split("\n")]
    start = next(
        index for index, line in enumerate(lines)
        if line.startswith('if "!STOP_RC!"=="')
    )
    branches, guard, body = [], lines[start], []
    for line in lines[start + 1:]:
        stripped = line.strip()
        if stripped.startswith(") else"):
            branches.append((guard, body))
            guard, body = stripped, []
        elif stripped == ")":
            branches.append((guard, body))
            break
        else:
            body.append(stripped)
    else:  # pragma: no cover - the chain is always closed
        raise AssertionError("stop.bat's STOP_RC chain is unterminated")

    tail = lines[lines.index(")", start):]
    fallthrough = next(
        (line for line in tail if line.startswith("exit /b")), "exit /b 0"
    )
    for guard, body in branches:
        match = re.search(r'"!STOP_RC!"=="(\d+)"', guard)
        if match is not None and int(match.group(1)) != code:
            continue
        if match is None and not guard.startswith(") else ("):
            continue
        echoed = [
            line[len("echo "):] for line in body if line.startswith("echo ")
        ]
        exits = [line for line in body if line.startswith("exit /b")]
        chosen = exits[0] if exits else fallthrough
        return {"echo": echoed, "exit": int(chosen.split()[-1])}
    raise AssertionError(f"no branch of stop.bat handles exit code {code}")


def _load_server_port_contract():
    """Load only app.py's port helpers, not its 21k-line runtime graph."""
    tree = ast.parse(SERVER.read_text(encoding="utf-8"), filename=str(SERVER))
    wanted_assignments = {"_SERVER_HOST", "_DEFAULT_SERVER_PORTS"}
    wanted_defs = {"ServerPortError", "_port_is_available", "_select_server_port"}
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id in wanted_assignments
                for target in node.targets):
            nodes.append(node)
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in wanted_defs:
            nodes.append(node)
    namespace = {"os": os}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
                 str(SERVER), "exec"), namespace)
    return namespace


def _load_server_workspace_contract():
    """Load the checkout-root bootstrap without importing the server graph."""
    tree = ast.parse(SERVER.read_text(encoding="utf-8"), filename=str(SERVER))
    node = next(
        item for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "_resolve_server_workspace"
    )
    namespace = {"os": os, "Path": Path, "__file__": str(SERVER)}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
                 str(SERVER), "exec"), namespace)
    return namespace["_resolve_server_workspace"]


def _load_startup_refresh_contract(rp):
    """Load the startup callers and their real environment/path helpers."""
    tree = ast.parse(SERVER.read_text(encoding="utf-8"), filename=str(SERVER))
    assignments = {
        "OPENROUTER_REFRESH_SCRIPT", "DIRECT_API_REFRESH_SCRIPT",
        "OPENROUTER_STALE_DAYS", "DIRECT_API_STALE_DAYS",
    }
    definitions = {
        "_model_refresh_env", "_openrouter_catalog_path", "_direct_api_marker_path",
        "_refresh_direct_apis_if_stale", "_refresh_openrouter_if_stale",
    }
    nodes = [node for node in tree.body if (
        isinstance(node, ast.FunctionDef) and node.name in definitions
    ) or (
        isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in assignments
            for target in node.targets
        )
    )]
    namespace = {"os": os, "sys": sys, "rp": rp, "WORKSPACE": str(ROOT)}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
                 str(SERVER), "exec"), namespace)
    return namespace


def _run_with_fake_python(tmp_path: Path, *args: str, overrides: dict[str, str] | None = None):
    workspace = tmp_path / "ora root"
    server_dir = workspace / "server"
    server_dir.mkdir(parents=True)
    (server_dir / "app.py").write_text("# test sentinel\n", encoding="utf-8")

    capture = tmp_path / "capture"
    capture.mkdir()
    fake_python = tmp_path / "fake python"
    fake_python.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$@\" > \"$ORA_TEST_CAPTURE/argv\"\n"
        "env > \"$ORA_TEST_CAPTURE/env\"\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "ORA_HOME": str(workspace),
            "ORA_PYTHON": str(fake_python),
            "ORA_TEST_CAPTURE": str(capture),
        }
    )
    for flag in RUNTIME_FLAGS:
        env.pop(flag, None)
    if overrides:
        env.update(overrides)

    completed = subprocess.run(
        ["bash", str(RUNNER), *args],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    argv = (capture / "argv").read_text(encoding="utf-8").splitlines()
    child_env = dict(
        line.split("=", 1)
        for line in (capture / "env").read_text(encoding="utf-8").splitlines()
        if "=" in line
    )
    return completed, workspace, argv, child_env




class TestServerLaunchers(unittest.TestCase):
    def setUp(self):
        # The launchers deliberately resolve symlinks (``pwd -P``), and on
        # macOS the temp root is /var -> /private/var. Resolve once here so
        # every expected path a test derives matches what they report.
        self.tmp_path = Path(tempfile.mkdtemp()).resolve()

    def tearDown(self):
        shutil.rmtree(self.tmp_path, ignore_errors=True)

    def _assert_startup_refresh(self, direct, timeout):
        import runtime_paths as rp

        runtime = self.tmp_path / "private runtime"
        config = runtime / "config"
        config.mkdir(parents=True)
        selected = str(self.tmp_path / "selected venv" / "python")
        label = "Direct-API" if direct else "OpenRouter"
        function = ("_refresh_direct_apis_if_stale" if direct
                    else "_refresh_openrouter_if_stale")
        script = ROOT / "scripts" / (
            "refresh-direct-apis.py" if direct else "refresh-openrouter.py"
        )
        state = config / (
            ".direct-api-refresh-stamp" if direct else "openrouter-catalog.json"
        )
        old_bytes = b"previous successful refresh"
        now = 2_000_000_000
        with mock.patch.multiple(
            rp, ORA_HOME=self.tmp_path / "private seed", RUNTIME_ROOT=runtime,
            RUNTIME_CONFIG_DIR=config, RUNTIME_DATA_DIR=runtime / "data",
            RUNTIME_CONFIGURATIONS_DIR=config / "configurations",
        ), mock.patch.dict(os.environ, {
            "D23_INHERITED": "retained",
            "ORA_MODEL_CATALOG_PATH": "inherited value must be overridden",
            "ORA_DIRECT_API_REFRESH_MARKER": str(config / ".direct-api-refresh-stamp"),
        }), mock.patch.object(sys, "executable", selected), \
                mock.patch("time.time", return_value=now):
            refresh = _load_startup_refresh_contract(rp)[function]
            expected_env = os.environ.copy()
            expected_env.update(rp.runtime_refresh_env())
            for outcome in ("fresh", "success", "nonzero", "timeout", "missing"):
                with self.subTest(outcome=outcome):
                    state.write_bytes(old_bytes)
                    mtime = now if outcome == "fresh" else now - 8 * 86400
                    os.utime(state, (mtime, mtime))
                    if outcome == "missing":
                        state.unlink()
                    result = subprocess.CompletedProcess(
                        [], 3 if outcome == "nonzero" else 0,
                        stdout="refreshed", stderr="catalogue refresh failed",
                    )
                    with mock.patch.object(subprocess, "run", return_value=result) as run, \
                            mock.patch("builtins.print") as printed:
                        if outcome == "timeout":
                            run.side_effect = subprocess.TimeoutExpired([selected, str(script)], timeout)
                        self.assertIsNone(refresh())  # Failure must let startup continue.
                    if outcome == "fresh":
                        run.assert_not_called()
                        self.assertEqual(state.read_bytes(), old_bytes)
                        continue
                    run.assert_called_once_with(
                        [selected, str(script)], capture_output=True, text=True,
                        timeout=timeout, env=expected_env,
                    )
                    messages = "\n".join(str(call.args[0]) for call in printed.call_args_list)
                    if outcome in {"nonzero", "timeout"}:
                        self.assertEqual(state.read_bytes(), old_bytes)
                        self.assertEqual(state.stat().st_mtime, mtime)
                        self.assertIn(f"{label} refresh " + (
                            "failed:" if outcome == "nonzero" else "exception:"
                        ), messages)
                    else:
                        self.assertIn(f"{label} catalog refreshed.", messages)
                        if direct:
                            self.assertEqual(float(state.read_text(encoding="utf-8")), now)
                        elif outcome == "success":
                            self.assertEqual(state.read_bytes(), old_bytes)

    def test_startup_direct_api_refresh_uses_running_interpreter(self):
        self._assert_startup_refresh(direct=True, timeout=120)

    def test_startup_openrouter_refresh_uses_running_interpreter(self):
        self._assert_startup_refresh(direct=False, timeout=60)

    def test_foreground_launcher_exports_every_runtime_flag(self):
        completed, workspace, argv, child_env = _run_with_fake_python(
            self.tmp_path,
            "--scheduler",
            overrides={"ORA_WEB_EXTRACTION": "0", "PATH": "/usr/bin:/bin"},
        )
    
        assert completed.returncode == 0, completed.stderr
        assert argv == [
            str(workspace / "server" / "app.py"),
            "--oversight",
            "--scheduler",
        ]
        assert child_env["ORA_HOME"] == str(workspace)
        assert child_env["PYTHONUNBUFFERED"] == "1"
        assert child_env["PATH"].startswith(
            f"{os.environ['HOME']}/.local/bin:{os.environ['HOME']}/bin:"
            "/opt/homebrew/bin:/usr/local/bin:"
        )
        for name, default in RUNTIME_FLAGS.items():
            expected = "0" if name == "ORA_WEB_EXTRACTION" else default
            assert child_env[name] == expected

    def test_foreground_launcher_preserves_explicit_server_port(self):
        completed, _workspace, _argv, child_env = _run_with_fake_python(
            self.tmp_path, overrides={"PORT": "6200"})
    
        assert completed.returncode == 0, completed.stderr
        assert child_env["PORT"] == "6200"

    def test_no_oversight_is_stripped_without_losing_other_arguments(self):
        completed, workspace, argv, _ = _run_with_fake_python(
            self.tmp_path, "--scheduler", "--no-oversight", "--future-option"
        )
    
        assert completed.returncode == 0, completed.stderr
        assert argv == [
            str(workspace / "server" / "app.py"),
            "--scheduler",
            "--future-option",
        ]

    def test_foreground_launcher_honors_activated_virtualenv_before_path_fallback(self):
        workspace = self.tmp_path / "ora root"
        (workspace / "server").mkdir(parents=True)
        (workspace / "server" / "app.py").write_text(
            "# test sentinel\n", encoding="utf-8"
        )
    
        capture = self.tmp_path / "capture"
        capture.mkdir()
        venv = self.tmp_path / "active venv"
        venv_python = venv / "bin" / "python"
        venv_python.parent.mkdir(parents=True)
        fallback_python = self.tmp_path / "home" / ".local" / "bin" / "python3"
        fallback_python.parent.mkdir(parents=True)
    
        capture_script = (
            "#!/bin/sh\n"
            "printf '%s\\n' \"$0\" > \"$ORA_TEST_CAPTURE/selected\"\n"
            "printf '%s\\n' \"$@\" > \"$ORA_TEST_CAPTURE/argv\"\n"
            "env > \"$ORA_TEST_CAPTURE/env\"\n"
        )
        for executable in (venv_python, fallback_python):
            executable.write_text(capture_script, encoding="utf-8")
            executable.chmod(0o755)
    
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(self.tmp_path / "home"),
                "ORA_HOME": str(workspace),
                "VIRTUAL_ENV": str(venv),
                "ORA_TEST_CAPTURE": str(capture),
                # Simulate launchd's sparse inherited PATH. The runner still adds
                # its supported fallback locations, but the active venv must win.
                "PATH": "/usr/bin:/bin",
            }
        )
        env.pop("ORA_PYTHON", None)
    
        completed = subprocess.run(
            ["bash", str(RUNNER)],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
    
        assert completed.returncode == 0, completed.stderr
        assert (capture / "selected").read_text(encoding="utf-8").strip() == str(
            venv_python
        )
        assert (capture / "argv").read_text(encoding="utf-8").splitlines() == [
            str(workspace / "server" / "app.py"),
            "--oversight",
        ]
        child_env = dict(
            line.split("=", 1)
            for line in (capture / "env").read_text(encoding="utf-8").splitlines()
            if "=" in line
        )
        assert child_env["VIRTUAL_ENV"] == str(venv)
        assert child_env["PATH"].startswith(
            f"{self.tmp_path / 'home'}/.local/bin:{self.tmp_path / 'home'}/bin:"
            "/opt/homebrew/bin:/usr/local/bin:"
        )

    def test_interactive_start_delegates_to_foreground_launcher(self):
        source = START.read_text(encoding="utf-8")
    
        assert 'SERVER_LAUNCHER="$WORKSPACE/run-ora-server.sh"' in source
        assert 'nohup "$SERVER_LAUNCHER" "$@"' in source
        assert source.count("server/app.py") == 1  # exact-argv legacy-process guard
        assert 'exec "$PYTHON" "$WORKSPACE/server/app.py"' not in source
        assert "pkill" not in source

    def test_interactive_start_rejects_zero_timeout_before_launching(self):
        completed = subprocess.run(
            ["bash", str(START)],
            env={
                **os.environ,
                "HOME": str(self.tmp_path),
                "ORA_HOME": str(self.tmp_path),
                "ORA_START_TIMEOUT": "0",
                "ORA_NO_BROWSER": "1",
            },
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 2
        assert "positive integer" in completed.stderr

    def test_interactive_start_rejects_invalid_explicit_port_before_launching(self):
        completed = subprocess.run(
            ["bash", str(START)],
            env={
                **os.environ,
                "HOME": str(self.tmp_path),
                "ORA_HOME": str(self.tmp_path),
                "PORT": "05000",
                "ORA_NO_BROWSER": "1",
            },
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 2
        assert "PORT must be a canonical integer" in completed.stderr

    def test_interactive_launchers_poll_exact_explicit_port(self):
        workspace = self.tmp_path / "ora root"
        (workspace / "scripts").mkdir(parents=True)
        fake_bin = self.tmp_path / "bin"
        fake_bin.mkdir()
        (fake_bin / "python3").symlink_to(sys.executable)
        forbidden_start = (
            "#!/bin/sh\n"
            'printf \'%s\\n\' "$0 $*" >> "$ORA_TEST_CAPTURE/starts"\n'
            "exit 99\n"
        )
        stubs = {
            workspace / "run-ora-server.sh": forbidden_start,
            workspace / "scripts" / "ora-launchd.sh": forbidden_start,
            fake_bin / "curl": (
                "#!/bin/sh\n"
                'printf \'%s\\n\' "$4" >> "$ORA_TEST_CAPTURE/probes"\n'
                'if [ "$4" = "http://localhost:$ORA_TEST_READY_PORT/health" ]; then\n'
                '  printf \'{"ora_home":"%s"}\\n\' "$ORA_HOME"\n'
                'elif [ "$4" = "http://localhost:5000/health" ]; then\n'
                '  printf \'{"ora_home":"%s/other checkout"}\\n\' "$ORA_HOME"\n'
                "else\n  exit 22\nfi\n"
            ),
            fake_bin / "launchctl": (
                "#!/bin/sh\n"
                'printf \'%s\\n\' "$*" >> "$ORA_TEST_CAPTURE/launchctl"\n'
                '[ "$1" = "print" ] && [ "$ORA_TEST_SUPERVISED" = "1" ]\n'
            ),
            fake_bin / "open": (
                "#!/bin/sh\n"
                'printf \'%s\\n\' "$@" >> "$ORA_TEST_CAPTURE/browser"\n'
            ),
        }
        for path, source in stubs.items():
            path.write_text(source, encoding="utf-8")
            path.chmod(0o755)

        # The first case reaches the last default port after rejecting another
        # checkout at 5000. Run the real system Bash, including macOS Bash 3.2.
        for name, port, supervised in (
            ("default", None, "1"),
            ("explicit", "6123", "0"),
            ("supervised override", "6123", "1"),
        ):
            with self.subTest(name=name):
                capture = self.tmp_path / name
                capture.mkdir()
                for log in ("starts", "probes", "launchctl", "browser"):
                    (capture / log).touch()
                env = {
                    "PATH": f"{fake_bin}:/usr/bin:/bin",
                    "HOME": str(self.tmp_path),
                    "ORA_HOME": str(workspace),
                    "ORA_START_TIMEOUT": "1",
                    "ORA_TEST_CAPTURE": str(capture),
                    "ORA_TEST_READY_PORT": port or "5010",
                    "ORA_TEST_SUPERVISED": supervised,
                }
                if port is not None:
                    env["PORT"] = port
                completed = subprocess.run(
                    ["/bin/bash", str(START)], cwd=workspace, env=env,
                    text=True, capture_output=True, check=False, timeout=10,
                )
                rejected = port is not None and supervised == "1"
                assert completed.returncode == (2 if rejected else 0), completed
                probes = [] if rejected else (
                    [port] if port is not None else list(range(5000, 5011))
                )
                assert (capture / "probes").read_text().splitlines() == [
                    f"http://localhost:{number}/health" for number in probes
                ]
                assert (capture / "browser").read_text().splitlines() == (
                    [] if rejected else [f"http://localhost:{port or '5010'}"]
                )
                assert (capture / "starts").read_text() == ""
                assert (capture / "launchctl").read_text().splitlines() == [
                    f"print gui/{os.getuid()}/com.ora.server"
                ]
                if rejected:
                    assert "cannot be applied while Ora is managed by launchd" in completed.stderr

        posix = START.read_text(encoding="utf-8")
        windows = _bat_source(START_BAT)
    
        assert 'ports=( "$PORT" )' in posix
        assert '"${PORT+x}" == "x" && "$launchd_state" != "none"' in posix
        assert 'set "ORA_HEALTH_PORT=!PORT!"' in windows
        assert "call :check_health_identity" in windows
        assert 'set "FOUND_PORT=!PORT!"' in windows
        assert "s.bind(('localhost',int(os.environ['PORT'])))" in windows

    def test_windows_launcher_targets_its_own_or_explicit_checkout(self):
        source = _bat_source(START_BAT)
    
        assert "if defined ORA_HOME" in source
        assert 'set "WORKSPACE=!ORA_HOME!"' in source
        assert 'set "WORKSPACE=%~dp0"' in source
        assert 'set "ORA_HOME=!WORKSPACE!"' in source
        assert "%USERPROFILE%\\ora" not in source

        launch_block = re.search(
            r'^setlocal DisableDelayedExpansion\r?\n'
            r'(?P<launch>%PYTHON% -c "[^\r\n]*subprocess\.Popen[^\r\n]*" %\*)\r?\n'
            r'^endlocal\r?$',
            source,
            re.MULTILINE,
        )
        assert launch_block, (
            "start.bat must disable cmd delayed expansion around its embedded "
            "Python spawn and forwarded argv"
        )
        launch_line = launch_block.group("launch")
        match = re.fullmatch(r'%PYTHON% -c "(.*)" %\*', launch_line)
        assert match, "start.bat no longer exposes one testable Python spawn"
        launch_code = match.group(1)
        target = self.tmp_path / "ora root" / "server" / "app.py"
        pid_file = self.tmp_path / "ora root" / ".ora-server.pid"
        target.parent.mkdir(parents=True)

        def launched_argv(*args):
            process = mock.Mock(pid=4242)
            env = {
                **os.environ,
                "ORA_SERVER_TARGET": str(target),
                "ORA_SERVER_PID_FILE": str(pid_file),
            }
            with mock.patch.dict(os.environ, env, clear=True), \
                 mock.patch.object(sys, "argv", ["-c", *args]), \
                 mock.patch.object(
                     subprocess, "CREATE_NEW_PROCESS_GROUP", 0, create=True,
                 ), \
                 mock.patch.object(
                     subprocess, "Popen", return_value=process,
                 ) as popen:
                exec(compile(launch_code, "start.bat", "exec"), {})
            return popen.call_args.args[0]

        assert launched_argv("--scheduler") == [
            sys.executable,
            str(target),
            "--oversight",
            "--scheduler",
        ]
        assert launched_argv(
            "--scheduler", "--no-oversight", "--future-option"
        ) == [
            sys.executable,
            str(target),
            "--scheduler",
            "--future-option",
        ]

    def test_windows_health_probe_rejects_a_different_checkout(self):
        source = _bat_source(START_BAT)
        match = re.search(
            r"REM ORA_HEALTH_IDENTITY_CHECK[^\r\n]*\r?\n"
            r"%PYTHON% -c \"([^\r\n]+)\" >nul",
            source,
        )
        assert match, "health identity command is missing from start.bat"
        health_code = match.group(1)
    
        class HealthHandler(http.server.BaseHTTPRequestHandler):
            ora_home = ""
    
            def do_GET(self):
                body = json.dumps({"status": "ok", "ora_home": self.ora_home}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
    
            def log_message(self, _format, *_args):
                pass
    
        server = http.server.HTTPServer(("127.0.0.1", 0), HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        intended = self.tmp_path / "intended checkout"
        intended.mkdir()
        env = {
            **os.environ,
            "ORA_HOME": str(intended),
            "ORA_HEALTH_PORT": str(server.server_port),
        }
        try:
            HealthHandler.ora_home = str(self.tmp_path / "other checkout")
            wrong = subprocess.run(
                [sys.executable, "-c", health_code], env=env, check=False
            )
            HealthHandler.ora_home = str(intended)
            correct = subprocess.run(
                [sys.executable, "-c", health_code], env=env, check=False
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
    
        assert wrong.returncode == 1
        assert correct.returncode == 0

    def test_windows_launchers_only_name_server_files_that_exist(self):
        """start.bat launched `server\\server.py` for three weeks after it was renamed.

        That path was correct when start.bat was written (d8704d5b,
        2026-04-27): `server/server.py` had shipped since the initial commit.
        The rename to `server/app.py` (f14ea5b0, 2026-07-31) swept 95 files,
        including start.sh, stop.sh, run-ora-server.sh and ora-launchd.sh —
        every launcher except the two batch scripts. Windows broke that day
        and stayed broken until the repair on 2026-08-21.

        The suite passed throughout, because nothing checked the launch target
        against the filesystem. Every server file either batch script names —
        the one it launches and the one its failure message tells the user to
        run by hand — has to be a real file in this checkout.
        """
        start_source = _bat_source(START_BAT)
        stop_source = _bat_source(STOP_BAT)

        named = _bat_server_files(start_source) | _bat_server_files(stop_source)
        assert named, "the Windows launchers name no server file at all"
        missing = sorted(rel for rel in named if not (ROOT / rel).is_file())
        assert not missing, f"Windows launchers point at missing files: {missing}"
        assert named == {"server/app.py"}
        assert "server.py" not in start_source
        assert "server.py" not in stop_source

    def test_windows_launch_and_recovery_advice_name_one_command(self):
        source = _bat_source(START_BAT)
        lines = source.splitlines()

        launch = [line for line in lines if "subprocess.Popen" in line]
        assert len(launch) == 1, "start.bat should spawn the server exactly once"
        assert "os.environ['ORA_SERVER_TARGET']" in launch[0]

        recovery = [
            line for line in lines if line.startswith("echo ERROR: Server did not start")
        ]
        assert len(recovery) == 1
        # The advice must reproduce the launch, not a second guess at the path.
        assert "%PYTHON%" in recovery[0]
        assert "!ORA_SERVER_TARGET!" in recovery[0]

    def test_windows_start_and_stop_share_one_process_identity_mechanism(self):
        """Both scripts must find the server the same way, or stop is a lottery.

        They used to run `tasklist /v | findstr server.py`, which searches the
        WINDOW TITLE — the launcher's own window is titled "Ora Server", so the
        match was against the wrong field entirely.
        """
        start_source = _bat_source(START_BAT)
        stop_source = _bat_source(STOP_BAT)

        for name in ("ora-process-identity", "ora-stop-owned-server"):
            in_start = _bat_shared_block(start_source, name)
            in_stop = _bat_shared_block(stop_source, name)
            assert in_start, f"start.bat is missing the '{name}' block"
            assert in_stop, f"stop.bat is missing the '{name}' block"
            assert in_start == in_stop, f"'{name}' has drifted between the two"

        identity = _bat_shared_block(start_source, "ora-process-identity")
        assert 'set "ORA_SERVER_TARGET=%%~fI"' in identity
        assert 'set "ORA_SERVER_PID_FILE=%%~fI"' in identity

        # start.bat records the PID it launched; stop.bat consumes that file.
        assert "write_text(str(child.pid)" in start_source
        assert "ORA_SERVER_PID_FILE" in stop_source
        assert "call :stop_owned_server" in start_source
        assert "call :stop_owned_server" in stop_source

        # Both scripts resolve the same checkout, so neither can reach into
        # another one, and neither identifies anything by window title.
        for source in (start_source, stop_source):
            assert 'set "WORKSPACE=!ORA_HOME!"' in source
            assert 'set "WORKSPACE=%~dp0"' in source
            assert "tasklist" not in source
            assert "findstr" not in source
            assert "taskkill" not in source

    def test_windows_stop_reverifies_a_recorded_pid_before_killing_it(self):
        block = _bat_shared_block(
            _bat_source(STOP_BAT), "ora-stop-owned-server"
        )
        assert block

        assert "Get-CimInstance Win32_Process" in block
        # With a PID file, only that PID is a candidate...
        assert "$proc.ProcessId -ne $owned" in block
        # ...and it is still killed only if it is a Python interpreter running
        # this checkout's exact server file, so a PID Windows has recycled onto
        # something else survives.
        assert "$name.ToLower().StartsWith('python')" in block
        assert "$cl.IndexOf($target, $ord)" in block
        assert "Stop-Process -Id $proc.ProcessId -Force" in block
        assert "Stop-Process -Name" not in block

    def test_windows_stop_matches_only_the_argument_after_an_interpreter(self):
        """A path anywhere in a command line is not evidence the launcher ran it.

        The first version of this block accepted the server path in ANY argument
        position, so `python -m pytest <server>` and `python fmt.py <server>` --
        neither of them started by start.bat -- were force-killed. The rule is
        positional, as it already was in stop.sh: whatever sits immediately
        before the path has to be a Python interpreter and optional -flags, and
        the path has to end its own argument.
        """
        block = _bat_shared_block(_bat_source(STOP_BAT), "ora-stop-owned-server")
        assert block

        # The position-blind matcher must not come back.
        assert "$cl.Contains($target + ' ')" not in block
        assert "$cl.Contains($target + [char]34)" not in block
        assert "$cl.EndsWith($target)" not in block

        # ...and the positional one must be doing the work.
        for fragment in (
            "$pos = $cl.IndexOf($target, $ord)",
            "$before = $cl.Substring(0, $pos)",
            "$after = $cl.Substring($pos + $target.Length)",
            "$parts = $before.Replace($q, '').TrimEnd().Split([char[]]('\\', '/'))",
            "$exe = $parts[$parts.Length - 1]",
        ):
            assert fragment in block, f"the positional rule lost: {fragment}"

        for command_line, expected in WINDOWS_STOP_CASES:
            actual = _windows_stop_matches(block, command_line, WINDOWS_TARGET)
            assert actual == expected, (
                f"{command_line!r} should {'match' if expected else 'not match'}"
            )

        # Windows quotes any argument with a space in it, so a checkout under
        # C:\Users\Jane Doe still has to be stoppable -- without the quotes
        # becoming a way back into the position-blind behaviour.
        for command_line, expected in WINDOWS_QUOTED_STOP_CASES:
            actual = _windows_stop_matches(
                block, command_line, WINDOWS_TARGET_WITH_SPACE
            )
            assert actual == expected, (
                f"{command_line!r} should {'match' if expected else 'not match'}"
            )

    def test_windows_and_posix_stop_agree_on_the_same_process_shapes(self):
        """One rule, two implementations -- they have to reach the same verdict.

        stop.sh's awk is the reference and is executed here for real. The
        Windows side is a translation (no PowerShell on this platform), so the
        value of this test is the comparison: every process shape either both
        of them kill, or neither does.
        """
        block = _bat_shared_block(_bat_source(STOP_BAT), "ora-stop-owned-server")
        assert block
        program = _posix_stop_awk_program()

        for index, (windows_line, _expected) in enumerate(WINDOWS_STOP_CASES):
            posix_line, posix_target = POSIX_STOP_CASES[index]
            windows = _windows_stop_matches(block, windows_line, WINDOWS_TARGET)
            posix = _posix_stop_matches(program, posix_line, posix_target)
            assert windows == posix, (
                "the two stop paths disagree:\n"
                f"  windows {'kills' if windows else 'spares'}: {windows_line}\n"
                f"  posix   {'kills' if posix else 'spares'}: {posix_line}"
            )

    def test_windows_stop_counts_only_kills_that_actually_happened(self):
        """`stop.bat` used to print "Server stopped." having killed nothing.

        `Stop-Process -ErrorAction SilentlyContinue` swallows the access-denied
        an elevated server produces, and the counter was incremented regardless.
        """
        block = _bat_shared_block(_bat_source(STOP_BAT), "ora-stop-owned-server")
        assert block

        assert "Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop" in block, (
            "a kill that fails must raise, not be swallowed"
        )
        # The success counter is reachable only from the statement after the kill.
        kill = "try { Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop; " \
               "$stopped = $stopped + 1 } catch { $failed = $failed + 1 }"
        assert kill in block
        assert block.count("$stopped = $stopped + 1") == 1

    def test_windows_stop_separates_a_broken_stop_from_an_idle_machine(self):
        """A stop that could not run is not the same fact as nothing to stop.

        With powershell.exe missing or blocked, cmd returns 9009 -- and the old
        script read every non-zero code as "Server was not running.", which
        reassures the operator that a server they cannot see is gone.
        """
        source = _bat_source(STOP_BAT)
        block = _bat_shared_block(source, "ora-stop-owned-server")
        assert block

        # Distinct outcomes carry distinct codes, and none of them is bare 1 --
        # PowerShell itself exits 1 when it dies of an unhandled error.
        assert "$code = 3" in block and "$code = 0" in block
        assert "$code = 2" in block and "$code = 4" in block

        stopped = _bat_stop_outcome(source, 0)
        assert stopped["exit"] == 0
        assert any("Server stopped." in line for line in stopped["echo"])

        idle = _bat_stop_outcome(source, 3)
        assert idle["exit"] == 0
        assert any("Server was not running." in line for line in idle["echo"])

        for code in (2, 4, 9009, 1, 255):
            outcome = _bat_stop_outcome(source, code)
            assert outcome["exit"] == 1, f"exit code {code} must fail loudly"
            assert any(line.startswith("ERROR:") for line in outcome["echo"]), (
                f"exit code {code} produced no error message"
            )
            assert not any("was not running" in line for line in outcome["echo"]), (
                f"exit code {code} still reports the machine as idle"
            )
        assert "powershell.exe" in " ".join(_bat_stop_outcome(source, 9009)["echo"])

    def test_windows_launcher_states_the_installer_python_floor(self):
        tree = ast.parse(INSTALLER.read_text(encoding="utf-8"), filename=str(INSTALLER))
        floor = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "PREFLIGHT_MIN_PYTHON"
                for target in node.targets
            ):
                floor = ast.literal_eval(node.value)
        assert floor, "scripts/install.py no longer declares PREFLIGHT_MIN_PYTHON"

        required = "{}.{}".format(*floor[:2])
        source = _bat_source(START_BAT)
        assert f"Python {required}+" in source
        # No second, contradictory version claim anywhere in the launcher.
        assert set(re.findall(r"Python (\d+\.\d+)\+", source)) == {required}

    def test_each_launcher_ships_the_line_endings_its_interpreter_needs(self):
        """Batch files reach Windows as CRLF; shell scripts stay LF.

        cmd.exe walks a batch file by byte offset rather than by line, and with
        LF-only endings it can resume mid-line after a `goto` — the label lookup
        lands somewhere the author never wrote, and nothing reports an error.
        Both batch files use labels, and neither had ever run on Windows, so
        there was never any evidence LF worked there.

        Bytes on disk are only half the guarantee. Without the .gitattributes
        rule the next fresh clone, or a checkout on another platform, quietly
        puts LF back — so this asserts the rule as well as the result.
        """
        for path in (START_BAT, STOP_BAT):
            raw = path.read_bytes()
            assert b"\n" in raw, f"{path.name} has no line endings to check"
            bare_lf = raw.count(b"\n") - raw.count(b"\r\n")
            assert bare_lf == 0, (
                f"{path.name} must use CRLF throughout; found {bare_lf} bare LF endings"
            )

        # A trailing CR is part of the shebang or the command to a POSIX shell,
        # so these break outright if a checkout ever converts them.
        posix_scripts = sorted(ROOT.glob("*.sh")) + sorted((ROOT / "scripts").glob("*.sh"))
        assert {START, STOP, SERVICE_MANAGER}.issubset(set(posix_scripts))
        for path in posix_scripts:
            assert b"\r" not in path.read_bytes(), (
                f"{path.relative_to(ROOT)} carries CR bytes; POSIX shells choke on them"
            )

        rules = {
            line.split()[0]: line.split()[1:]
            for line in GITATTRIBUTES.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        assert rules.get("*.bat") == ["text", "eol=crlf"], (
            ".gitattributes must pin *.bat to CRLF or a fresh clone reverts it"
        )
        assert rules.get("*.ps1") == ["text", "eol=crlf"]
        assert rules.get("*.sh") == ["text", "eol=lf"], (
            ".gitattributes must pin *.sh to LF; Git for Windows defaults "
            "core.autocrlf=true and would otherwise convert them on clone"
        )

        # `*.sh` cannot see a script with no extension, and five of them under
        # scripts/ carry shebangs. They were measured coming out CRLF in a
        # default Git-for-Windows clone, which breaks them outright, so each
        # needs a rule of its own. A new one added later fails here until it
        # gets a line.
        shebanged = sorted(
            path for path in (ROOT / "scripts").iterdir()
            if path.is_file()
            and not path.suffix
            and path.read_bytes()[:2] == b"#!"
        )
        assert shebanged, "no extensionless scripts found to check"
        for path in shebanged:
            relative = path.relative_to(ROOT).as_posix()
            assert rules.get(relative) == ["text", "eol=lf"], (
                f"{relative} has a shebang and no extension; .gitattributes must "
                "pin it to LF or a Windows clone converts it to CRLF"
            )
            assert b"\r" not in path.read_bytes(), (
                f"{relative} carries CR bytes; its shebang would not resolve"
            )

    def test_interactive_start_rejects_one_shot_port_when_launchd_manages_ora(self):
        home = self.tmp_path / "home"
        workspace = self.tmp_path / "ora root"
        fake_bin = self.tmp_path / "bin"
        fake_bin.mkdir()
        home.mkdir()
        workspace.mkdir()
        runner = workspace / "run-ora-server.sh"
        runner.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
        runner.chmod(0o755)
        launchctl = fake_bin / "launchctl"
        launchctl.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        launchctl.chmod(0o755)
    
        completed = subprocess.run(
            ["bash", str(START)],
            env={
                **os.environ,
                "HOME": str(home),
                "ORA_HOME": str(workspace),
                "PATH": f"{fake_bin}:/usr/bin:/bin",
                "PORT": "6200",
                "ORA_NO_BROWSER": "1",
            },
            text=True,
            capture_output=True,
            check=False,
        )
    
        assert completed.returncode == 2
        assert "cannot be applied while Ora is managed by launchd" in completed.stderr
        assert "Refusing to start on another port" in completed.stderr

    def test_interactive_start_blocks_legacy_server_from_exact_checkout(self):
        home = self.tmp_path / "home"
        workspace = home / "ora root"
        fake_bin = self.tmp_path / "bin"
        target = workspace / "server" / "app.py"
        marker = self.tmp_path / "new-server-launched"
        fake_bin.mkdir(parents=True)
        target.parent.mkdir(parents=True)
        target.write_text("# legacy server sentinel\n", encoding="utf-8")
    
        runner = workspace / "run-ora-server.sh"
        runner.write_text(
            "#!/bin/sh\n"
            ': > "$ORA_TEST_LAUNCH_MARKER"\n',
            encoding="utf-8",
        )
        runner.chmod(0o755)
        (fake_bin / "curl").write_text(
            "#!/bin/sh\n"
            # A pre-identity server is healthy but has no ora_home field.
            "printf '%s\\n' '{\"status\":\"ok\",\"endpoint\":null}'\n",
            encoding="utf-8",
        )
        (fake_bin / "plutil").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        (fake_bin / "launchctl").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        (fake_bin / "ps").write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' '101 /opt/homebrew/bin/python3 -u {target} --oversight'\n"
            f"printf '%s\\n' '202 /usr/bin/vim {target}'\n"
            f"printf '%s\\n' '303 /opt/homebrew/bin/python3 {target}.bak --oversight'\n",
            encoding="utf-8",
        )
        for command in ("curl", "plutil", "launchctl", "ps"):
            (fake_bin / command).chmod(0o755)
    
        completed = subprocess.run(
            ["bash", str(START)],
            env={
                **os.environ,
                "HOME": str(home),
                "ORA_HOME": str(workspace),
                "ORA_NO_BROWSER": "1",
                "ORA_START_TIMEOUT": "1",
                "ORA_TEST_LAUNCH_MARKER": str(marker),
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
            },
            text=True,
            capture_output=True,
            check=False,
        )
    
        assert completed.returncode == 1
        assert "pre-upgrade server" in completed.stderr
        assert "PID(s): 101" in completed.stderr
        assert "202" not in completed.stderr  # editor path mention is not a server
        assert "303" not in completed.stderr  # similarly-prefixed backup is not exact
        assert not marker.exists(), "legacy process guard must run before nohup"

    def test_stop_uses_service_manager_and_limits_unsupervised_fallback(self):
        source = STOP.read_text(encoding="utf-8")
    
        assert 'exec "$SERVICE_MANAGER" stop --ora-home "$WORKSPACE"' in source
        assert 'ORA_STOP_SERVER_TARGET="$WORKSPACE/server/app.py"' in source
        assert "ps -axww -o pid=,command=" in source
        assert "for _attempt in {1..150}" in source
        assert 'pkill -f "server/app.py"' not in source
        assert "pgrep -f --" not in source

    def test_launchd_template_supervises_the_foreground_launcher(self):
        rendered = PLIST_TEMPLATE.read_text(encoding="utf-8").replace(
            "__ORA_HOME__", "/Users/test/ora"
        ).replace("__USER_HOME__", "/Users/test")
        payload = plistlib.loads(rendered.encode("utf-8"))
    
        assert payload["Label"] == "com.ora.server"
        assert payload["ProgramArguments"] == ["/Users/test/ora/run-ora-server.sh"]
        assert payload["WorkingDirectory"] == "/Users/test/ora"
        assert payload["RunAtLoad"] is True
        assert payload["KeepAlive"] is True
        assert payload["EnvironmentVariables"]["HOME"] == "/Users/test"
        assert payload["EnvironmentVariables"]["ORA_HOME"] == "/Users/test/ora"
        assert payload["EnvironmentVariables"]["PATH"].startswith(
            "/Users/test/.local/bin:/Users/test/bin:/opt/homebrew/bin:/usr/local/bin:"
        )

    def test_health_endpoint_exposes_canonical_checkout_identity(self):
        source = SERVER.read_text(encoding="utf-8")
        health_block = source.split('@app.route("/health")', 1)[1].split(
            "\n@app.route", 1
        )[0]
        assert '"ora_home"' in health_block
        assert "os.path.realpath(WORKSPACE)" in health_block

    def test_preview_launch_config_is_machine_local_not_tracked(self):
        patterns = GITIGNORE.read_text(encoding="utf-8").splitlines()
        assert "/.claude/launch.json" in patterns
        tracked = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "--", ".claude/launch.json"],
            text=True, capture_output=True, check=True,
        )
        assert tracked.stdout.strip() == ""

    def test_preview_launch_example_preserves_profiles_and_exact_ports(self):
        example = json.loads(LAUNCH_EXAMPLE.read_text(encoding="utf-8"))
        configurations = example["configurations"]
    
        assert [(item["name"], item["port"]) for item in configurations] == [
            ("ora", 5000),
            ("ora-verify", 5001),
            ("ora-preview", 5002),
            ("ora-preview-2", 5003),
        ]
        for item in configurations:
            assert item["runtimeExecutable"] == "REPLACE_WITH_LOCAL_PYTHON"
            assert item["runtimeArgs"] == ["${workspaceFolder}/server/app.py"]
            assert item["cwd"] == "${workspaceFolder}"
            assert item["env"] == {"PORT": str(item["port"])}
            assert item["autoPort"] is False
            assert "/Users/" not in json.dumps(item)
            assert "/opt/" not in json.dumps(item)

    def test_server_without_ora_home_bootstraps_from_its_own_checkout(self):
        resolve = _load_server_workspace_contract()
        checkout = self.tmp_path / "portable checkout"
        server_file = checkout / "server" / "app.py"
        server_file.parent.mkdir(parents=True)
        server_file.touch()
        env = {}
    
        workspace = resolve(env, server_file)
    
        assert Path(workspace) == checkout.resolve()
        assert env["ORA_HOME"] == str(checkout.resolve())

    def test_server_explicit_ora_home_remains_authoritative(self):
        resolve = _load_server_workspace_contract()
        explicit = self.tmp_path / "selected checkout"
        env = {"ORA_HOME": f"  {explicit}  "}
    
        workspace = resolve(env, self.tmp_path / "other" / "server" / "app.py")
    
        assert Path(workspace) == explicit
        assert env["ORA_HOME"] == str(explicit)

    def test_server_honors_an_explicit_available_port_without_scanning(self):
        contract = _load_server_port_contract()
        seen = []
    
        def available(port):
            seen.append(port)
            return True
    
        selected = contract["_select_server_port"]({"PORT": "6200"},
                                                     available=available)
        assert selected == 6200
        assert seen == [6200]

    def test_server_resolves_port_before_startup_side_effects_and_fails_loudly(self):
        source = SERVER.read_text(encoding="utf-8")
        main = source.split('if __name__ == "__main__":', 1)[1]
        assert main.index("port = _select_server_port()") < main.index(
            "migrate_active_project_pointer")
        assert 'print(f"ERROR: {_port_exc}", file=sys.stderr, flush=True)' in main
        assert "raise SystemExit(2)" in main

    def test_server_rejects_invalid_explicit_port_values(self):
        contract = _load_server_port_contract()
        select = contract["_select_server_port"]
        error = contract["ServerPortError"]
        for raw in ("", " ", "+5000", "05000", "5000.0", "0", "65536",
                    "-1", "abc", "５０００"):
            try:
                select({"PORT": raw}, available=lambda _port: True)
            except error as exc:
                assert "PORT" in str(exc)
            else:  # pragma: no cover - assertion branch
                raise AssertionError(f"invalid PORT accepted: {raw!r}")

    def test_server_explicit_busy_port_fails_without_fallback_scan(self):
        contract = _load_server_port_contract()
        seen = []
    
        def unavailable(port):
            seen.append(port)
            return False
    
        try:
            contract["_select_server_port"]({"PORT": "5002"}, available=unavailable)
        except contract["ServerPortError"] as exc:
            assert "PORT=5002 is unavailable" in str(exc)
            assert "different port" in str(exc)
        else:  # pragma: no cover - assertion branch
            raise AssertionError("occupied explicit PORT silently fell back")
        assert seen == [5002]

    def test_server_unset_port_preserves_first_free_default_scan(self):
        contract = _load_server_port_contract()
        seen = []
    
        def third_is_free(port):
            seen.append(port)
            return port == 5002
    
        selected = contract["_select_server_port"]({}, available=third_is_free)
        assert selected == 5002
        assert seen == [5000, 5001, 5002]

    def test_server_unset_port_fails_when_default_range_is_exhausted(self):
        contract = _load_server_port_contract()
        try:
            contract["_select_server_port"]({}, available=lambda _port: False)
        except contract["ServerPortError"] as exc:
            assert "5000-5010" in str(exc)
        else:  # pragma: no cover - assertion branch
            raise AssertionError("exhausted default range silently selected a port")

    def test_server_port_probe_closes_socket_after_bind_failure(self):
        contract = _load_server_port_contract()
    
        class BusySocket:
            closed = False
    
            def bind(self, _address):
                raise OSError("busy")
    
            def close(self):
                self.closed = True
    
        sock = BusySocket()
        assert contract["_port_is_available"](
            5000, socket_factory=lambda: sock) is False
        assert sock.closed is True

    def test_generated_app_launcher_delegates_to_interactive_start(self):
        source = APP_LAUNCHER.read_text(encoding="utf-8")
    
        assert 'exec "$WORKSPACE/start.sh"' in source
        assert '"$SCRIPT_DIR/../../.."' in source
        assert "$HOME/ora" not in source
        assert "server/app.py" not in source

    def test_icon_swap_targets_relocatable_ora_bundle_and_generated_variants(self):
        source = SWAP_ICON.read_text(encoding="utf-8")
    
        assert 'WORKSPACE="${ORA_HOME:-$SCRIPT_DIR}"' in source
        assert 'config/icons/ora-${VARIANT}.icns' in source
        assert 'BUNDLE="$WORKSPACE/Ora.app"' in source
        assert 'RESOURCE_DIR="$BUNDLE/Contents/Resources"' in source
        assert "dark|light|amber|teal|blue|warm" in source
        assert "$HOME/ora" not in source
        assert "ai.app" not in source

    def test_foreground_launcher_canonicalizes_symlinked_ora_home(self):
        real_home = self.tmp_path / "ora root"
        link_home = self.tmp_path / "ora-link"
        link_home.symlink_to(real_home, target_is_directory=True)
    
        completed, workspace, argv, child_env = _run_with_fake_python(
            self.tmp_path,
            overrides={"ORA_HOME": str(link_home)},
        )
    
        assert completed.returncode == 0, completed.stderr
        assert workspace == real_home
        assert child_env["ORA_HOME"] == str(real_home.resolve())
        assert argv[0] == str(real_home.resolve() / "server" / "app.py")

    def test_service_stop_kills_only_owned_python_server_not_path_decoys(self):
        home = self.tmp_path / "home"
        workspace = home / "ora root"
        fake_bin = self.tmp_path / "bin"
        fake_bin.mkdir(parents=True)
        (workspace / "server").mkdir(parents=True)
        (workspace / "server" / "app.py").write_text("# sentinel\n", encoding="utf-8")
    
        target = workspace / "server" / "app.py"
        killed_state = self.tmp_path / "killed"
        kill_log = self.tmp_path / "kill.log"
        (fake_bin / "uname").write_text("#!/bin/sh\nprintf 'Darwin\\n'\n", encoding="utf-8")
        (fake_bin / "launchctl").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        (fake_bin / "ps").write_text(
            "#!/bin/sh\n"
            'if [ ! -f "$ORA_TEST_KILLED_STATE" ]; then\n'
            f"  printf '%s\\n' '101 /opt/homebrew/bin/python3 -u {target} --oversight'\n"
            "fi\n"
            f"printf '%s\\n' '202 /usr/bin/vim {target}'\n"
            f"printf '%s\\n' '303 /opt/homebrew/bin/python3 {target}.bak --oversight'\n",
            encoding="utf-8",
        )
        for command in ("uname", "launchctl", "ps"):
            (fake_bin / command).chmod(0o755)
    
        bash_env = self.tmp_path / "bash-env"
        bash_env.write_text(
            "kill() {\n"
            '  if [ "${1:-}" = "-0" ]; then return 1; fi\n'
            '  printf \'%s\\n\' "$*" >> "$ORA_TEST_KILL_LOG"\n'
            '  : > "$ORA_TEST_KILLED_STATE"\n'
            "}\n"
            "command() {\n"
            '  if [ "${1:-}" = "-v" ] && [ "${2:-}" = "launchctl" ]; then return 1; fi\n'
            '  builtin command "$@"\n'
            "}\n",
            encoding="utf-8",
        )
        env = os.environ.copy()
        env.update({
            "HOME": str(home),
            "PATH": f"{fake_bin}:{env['PATH']}",
            "BASH_ENV": str(bash_env),
            "ORA_TEST_KILLED_STATE": str(killed_state),
            "ORA_TEST_KILL_LOG": str(kill_log),
        })
    
        completed = subprocess.run(
            ["bash", str(SERVICE_MANAGER), "stop", "--ora-home", str(workspace)],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
    
        assert completed.returncode == 0, completed.stderr
        assert kill_log.read_text(encoding="utf-8").split() == ["101"]
        assert "Stopped unmanaged Ora server" in completed.stdout
    
        killed_state.unlink()
        kill_log.unlink()
        fallback_env = env.copy()
        fallback_env["ORA_HOME"] = str(workspace)
        fallback = subprocess.run(
            ["bash", str(STOP)],
            env=fallback_env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert fallback.returncode == 0, fallback.stderr
        assert kill_log.read_text(encoding="utf-8").split() == ["101"]
        assert "Ora server stopped" in fallback.stdout

    def test_launchd_install_fails_closed_when_expected_instance_never_healthy(self):
        home = self.tmp_path / "home"
        workspace = home / "ora"
        fake_bin = self.tmp_path / "bin"
        logs = workspace / "logs"
        fake_bin.mkdir(parents=True)
        logs.mkdir(parents=True)
        runner = workspace / "run-ora-server.sh"
        runner.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        runner.chmod(0o755)
        (logs / "ora-server.stderr.log").write_text(
            "sentinel launch failure\n", encoding="utf-8"
        )
    
        state = self.tmp_path / "launchctl-state"
        launchctl_log = self.tmp_path / "launchctl.log"
        (fake_bin / "uname").write_text("#!/bin/sh\nprintf 'Darwin\\n'\n", encoding="utf-8")
        (fake_bin / "ps").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (fake_bin / "curl").write_text(
            "#!/bin/sh\n"
            "printf '{\"status\":\"ok\",\"ora_home\":\"/another/worktree\"}\\n'\n",
            encoding="utf-8",
        )
        (fake_bin / "launchctl").write_text(
            "#!/bin/sh\n"
            'printf \'%s\\n\' "$*" >> "$ORA_TEST_LAUNCHCTL_LOG"\n'
            'case "$1" in\n'
            '  print) [ -f "$ORA_TEST_LAUNCHCTL_STATE" ] ;;\n'
            '  bootout) rm -f "$ORA_TEST_LAUNCHCTL_STATE" ;;\n'
            '  bootstrap) : > "$ORA_TEST_LAUNCHCTL_STATE" ;;\n'
            '  *) exit 0 ;;\n'
            "esac\n",
            encoding="utf-8",
        )
        for command in ("uname", "ps", "curl", "launchctl"):
            (fake_bin / command).chmod(0o755)
        env = os.environ.copy()
        env.update({
            "HOME": str(home),
            "PATH": f"{fake_bin}:{env['PATH']}",
            "ORA_LAUNCHD_HEALTH_TIMEOUT": "1",
            "ORA_TEST_LAUNCHCTL_STATE": str(state),
            "ORA_TEST_LAUNCHCTL_LOG": str(launchctl_log),
        })
    
        completed = subprocess.run(
            ["bash", str(SERVICE_MANAGER), "install", "--ora-home", str(workspace)],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
    
        assert completed.returncode == 1
        assert "did not become healthy" in completed.stderr
        assert "sentinel launch failure" in completed.stderr
        assert not state.exists(), "failed health must unload the KeepAlive crash loop"
        assert (home / "Library" / "LaunchAgents" / "com.ora.server.plist").exists()

    def test_worktree_cannot_stop_or_uninstall_service_owned_by_other_checkout(self):
        home = self.tmp_path / "home"
        canonical = home / "ora"
        worktree = home / "ora-worktrees" / "feature"
        fake_bin = self.tmp_path / "bin"
        plist_dir = home / "Library" / "LaunchAgents"
        for directory in (canonical, worktree, fake_bin, plist_dir):
            directory.mkdir(parents=True)
        worktree_manager = worktree / "scripts" / "ora-launchd.sh"
        worktree_manager.parent.mkdir()
        worktree_manager.write_bytes(SERVICE_MANAGER.read_bytes())
        worktree_manager.chmod(0o755)
    
        plist_path = plist_dir / "com.ora.server.plist"
        with plist_path.open("wb") as handle:
            plistlib.dump({
                "Label": "com.ora.server",
                "ProgramArguments": [str(canonical / "run-ora-server.sh")],
                "WorkingDirectory": str(canonical),
            }, handle)
    
        state = self.tmp_path / "launchctl-state"
        state.touch()
        launchctl_log = self.tmp_path / "launchctl.log"
        (fake_bin / "uname").write_text("#!/bin/sh\nprintf 'Darwin\\n'\n", encoding="utf-8")
        (fake_bin / "ps").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (fake_bin / "launchctl").write_text(
            "#!/bin/sh\n"
            'printf \'%s\\n\' "$*" >> "$ORA_TEST_LAUNCHCTL_LOG"\n'
            'case "$1" in\n'
            '  print) [ -f "$ORA_TEST_LAUNCHCTL_STATE" ] ;;\n'
            '  bootout) rm -f "$ORA_TEST_LAUNCHCTL_STATE" ;;\n'
            '  *) exit 0 ;;\n'
            "esac\n",
            encoding="utf-8",
        )
        for command in ("uname", "ps", "launchctl"):
            (fake_bin / command).chmod(0o755)
        env = os.environ.copy()
        env.update({
            "HOME": str(home),
            "PATH": f"{fake_bin}:{env['PATH']}",
            "ORA_TEST_LAUNCHCTL_STATE": str(state),
            "ORA_TEST_LAUNCHCTL_LOG": str(launchctl_log),
        })
    
        wrapper_env = env.copy()
        wrapper_env["ORA_HOME"] = str(worktree)
        stopped = subprocess.run(
            ["bash", str(STOP)],
            env=wrapper_env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert stopped.returncode == 1
        assert "targets a different checkout" in stopped.stderr
        assert state.exists()
        assert plist_path.exists()
    
        uninstalled = subprocess.run(
            ["bash", str(SERVICE_MANAGER), "uninstall", "--ora-home", str(worktree)],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert uninstalled.returncode == 1
        assert "targets a different checkout" in uninstalled.stderr
        assert state.exists()
        assert plist_path.exists()
    
        forced = subprocess.run(
            [
                "bash", str(SERVICE_MANAGER), "uninstall",
                "--ora-home", str(worktree), "--force-target-mismatch",
            ],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert forced.returncode == 0, forced.stderr
        assert not state.exists()
        assert not plist_path.exists()
