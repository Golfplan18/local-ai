"""Regression tests for Ora's consolidated server launch paths."""

from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "run-ora-server.sh"
START = ROOT / "start.sh"
STOP = ROOT / "stop.sh"
PLIST_TEMPLATE = ROOT / "installer" / "macos" / "com.ora.server.plist.template"
APP_LAUNCHER = ROOT / "installer" / "macos" / "ora-app-launcher.sh"
SWAP_ICON = ROOT / "swap-icon.sh"
SERVICE_MANAGER = ROOT / "scripts" / "ora-launchd.sh"
SERVER = ROOT / "server" / "server.py"

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


def _run_with_fake_python(tmp_path: Path, *args: str, overrides: dict[str, str] | None = None):
    workspace = tmp_path / "ora root"
    server_dir = workspace / "server"
    server_dir.mkdir(parents=True)
    (server_dir / "server.py").write_text("# test sentinel\n", encoding="utf-8")

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


def test_foreground_launcher_exports_every_runtime_flag(tmp_path: Path):
    completed, workspace, argv, child_env = _run_with_fake_python(
        tmp_path,
        "--scheduler",
        overrides={"ORA_WEB_EXTRACTION": "0", "PATH": "/usr/bin:/bin"},
    )

    assert completed.returncode == 0, completed.stderr
    assert argv == [
        str(workspace / "server" / "server.py"),
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


def test_no_oversight_is_stripped_without_losing_other_arguments(tmp_path: Path):
    completed, workspace, argv, _ = _run_with_fake_python(
        tmp_path, "--scheduler", "--no-oversight", "--future-option"
    )

    assert completed.returncode == 0, completed.stderr
    assert argv == [
        str(workspace / "server" / "server.py"),
        "--scheduler",
        "--future-option",
    ]


def test_foreground_launcher_honors_activated_virtualenv_before_path_fallback(
    tmp_path: Path,
):
    workspace = tmp_path / "ora root"
    (workspace / "server").mkdir(parents=True)
    (workspace / "server" / "server.py").write_text(
        "# test sentinel\n", encoding="utf-8"
    )

    capture = tmp_path / "capture"
    capture.mkdir()
    venv = tmp_path / "active venv"
    venv_python = venv / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    fallback_python = tmp_path / "home" / ".local" / "bin" / "python3"
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
            "HOME": str(tmp_path / "home"),
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
        str(workspace / "server" / "server.py"),
        "--oversight",
    ]
    child_env = dict(
        line.split("=", 1)
        for line in (capture / "env").read_text(encoding="utf-8").splitlines()
        if "=" in line
    )
    assert child_env["VIRTUAL_ENV"] == str(venv)
    assert child_env["PATH"].startswith(
        f"{tmp_path / 'home'}/.local/bin:{tmp_path / 'home'}/bin:"
        "/opt/homebrew/bin:/usr/local/bin:"
    )


def test_interactive_start_delegates_to_foreground_launcher():
    source = START.read_text(encoding="utf-8")

    assert 'SERVER_LAUNCHER="$WORKSPACE/run-ora-server.sh"' in source
    assert 'nohup "$SERVER_LAUNCHER" "$@"' in source
    assert source.count("server/server.py") == 1  # exact-argv legacy-process guard
    assert 'exec "$PYTHON" "$WORKSPACE/server/server.py"' not in source
    assert "pkill" not in source


def test_interactive_start_rejects_zero_timeout_before_launching(tmp_path: Path):
    completed = subprocess.run(
        ["bash", str(START)],
        env={
            **os.environ,
            "HOME": str(tmp_path),
            "ORA_HOME": str(tmp_path),
            "ORA_START_TIMEOUT": "0",
            "ORA_NO_BROWSER": "1",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "positive integer" in completed.stderr


def test_interactive_start_blocks_legacy_server_from_exact_checkout(tmp_path: Path):
    home = tmp_path / "home"
    workspace = home / "ora root"
    fake_bin = tmp_path / "bin"
    target = workspace / "server" / "server.py"
    marker = tmp_path / "new-server-launched"
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


def test_stop_uses_service_manager_and_limits_unsupervised_fallback():
    source = STOP.read_text(encoding="utf-8")

    assert 'exec "$SERVICE_MANAGER" stop --ora-home "$WORKSPACE"' in source
    assert 'ORA_STOP_SERVER_TARGET="$WORKSPACE/server/server.py"' in source
    assert "ps -axww -o pid=,command=" in source
    assert "for _attempt in {1..150}" in source
    assert 'pkill -f "server/server.py"' not in source
    assert "pgrep -f --" not in source


def test_launchd_template_supervises_the_foreground_launcher():
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


def test_health_endpoint_exposes_canonical_checkout_identity():
    source = SERVER.read_text(encoding="utf-8")
    health_block = source.split('@app.route("/health")', 1)[1].split(
        "\n@app.route", 1
    )[0]
    assert '"ora_home"' in health_block
    assert "os.path.realpath(WORKSPACE)" in health_block


def test_generated_app_launcher_delegates_to_interactive_start():
    source = APP_LAUNCHER.read_text(encoding="utf-8")

    assert 'exec "$WORKSPACE/start.sh"' in source
    assert '"$SCRIPT_DIR/../../.."' in source
    assert "$HOME/ora" not in source
    assert "server/server.py" not in source


def test_icon_swap_targets_relocatable_ora_bundle_and_generated_variants():
    source = SWAP_ICON.read_text(encoding="utf-8")

    assert 'WORKSPACE="${ORA_HOME:-$SCRIPT_DIR}"' in source
    assert 'config/icons/ora-${VARIANT}.icns' in source
    assert 'BUNDLE="$WORKSPACE/Ora.app"' in source
    assert 'RESOURCE_DIR="$BUNDLE/Contents/Resources"' in source
    assert "dark|light|amber|teal|blue|warm" in source
    assert "$HOME/ora" not in source
    assert "ai.app" not in source


def test_launchd_install_is_idempotent_and_updates_existing_app(tmp_path: Path):
    home = tmp_path / "home & operator"
    workspace = home / "custom install" / "ora"
    workspace_link = home / "ora-link"
    fake_bin = tmp_path / "bin"
    app_macos = workspace / "Ora.app" / "Contents" / "MacOS"
    fake_bin.mkdir(parents=True)
    app_macos.mkdir(parents=True)
    workspace_link.symlink_to(workspace, target_is_directory=True)
    (workspace / "logs").mkdir()

    runner = workspace / "run-ora-server.sh"
    runner.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    runner.chmod(0o755)
    old_app = app_macos / "ai"
    old_app.write_text("#!/bin/sh\n# old launcher\n", encoding="utf-8")
    old_app.chmod(0o755)
    fake_start_log = tmp_path / "app-start.log"
    fake_start = workspace / "start.sh"
    fake_start.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$0\" > \"$ORA_TEST_APP_START_LOG\"\n",
        encoding="utf-8",
    )
    fake_start.chmod(0o755)

    (fake_bin / "uname").write_text(
        "#!/bin/sh\nprintf 'Darwin\\n'\n", encoding="utf-8"
    )
    (fake_bin / "ps").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (fake_bin / "curl").write_text(
        "#!/bin/sh\n"
        "printf '{\"status\":\"ok\",\"ora_home\":\"%s\"}\\n' "
        '"$ORA_TEST_HEALTH_HOME"\n',
        encoding="utf-8",
    )
    (fake_bin / "launchctl").write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> \"$ORA_TEST_LAUNCHCTL_LOG\"\n"
        "case \"$1\" in\n"
        "  print) [ -f \"$ORA_TEST_LAUNCHCTL_STATE\" ] ;;\n"
        "  bootout) rm -f \"$ORA_TEST_LAUNCHCTL_STATE\" ;;\n"
        "  bootstrap) : > \"$ORA_TEST_LAUNCHCTL_STATE\" ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    for command in ("uname", "ps", "curl", "launchctl"):
        (fake_bin / command).chmod(0o755)

    state = tmp_path / "launchctl-state"
    launchctl_log = tmp_path / "launchctl.log"
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            # Exercise both relative-path absolutization and symlink collapse.
            "ORA_HOME": workspace_link.name,
            "PATH": f"{fake_bin}:{env['PATH']}",
            "ORA_TEST_LAUNCHCTL_STATE": str(state),
            "ORA_TEST_LAUNCHCTL_LOG": str(launchctl_log),
            "ORA_TEST_APP_START_LOG": str(fake_start_log),
            "ORA_TEST_HEALTH_HOME": str(workspace),
        }
    )

    for _ in range(2):
        completed = subprocess.run(
            ["bash", str(SERVICE_MANAGER), "install"],
            env=env,
            cwd=home,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr

    installed = home / "Library" / "LaunchAgents" / "com.ora.server.plist"
    with installed.open("rb") as handle:
        payload = plistlib.load(handle)
    assert payload["ProgramArguments"] == [str(runner)]
    assert payload["WorkingDirectory"] == str(workspace)
    assert payload["EnvironmentVariables"]["HOME"] == str(home)
    assert old_app.read_text(encoding="utf-8") == APP_LAUNCHER.read_text(
        encoding="utf-8"
    )
    assert (app_macos / "ai.pre-supervision").read_text(encoding="utf-8") == (
        "#!/bin/sh\n# old launcher\n"
    )
    app_env = env.copy()
    app_env.pop("ORA_HOME", None)
    app_started = subprocess.run(
        [str(old_app)], env=app_env, text=True, capture_output=True, check=False
    )
    assert app_started.returncode == 0, app_started.stderr
    assert fake_start_log.read_text(encoding="utf-8").strip() == str(fake_start)
    calls = launchctl_log.read_text(encoding="utf-8")
    assert calls.count("bootstrap ") == 2
    assert "bootout " in calls

    stopped = subprocess.run(
        ["bash", str(SERVICE_MANAGER), "stop"],
        env=env,
        cwd=home,
        text=True,
        capture_output=True,
        check=False,
    )
    assert stopped.returncode == 0, stopped.stderr
    assert not state.exists()
    assert installed.exists()

    started = subprocess.run(
        ["bash", str(SERVICE_MANAGER), "start"],
        env=env,
        cwd=home,
        text=True,
        capture_output=True,
        check=False,
    )
    assert started.returncode == 0, started.stderr
    assert state.exists()


def test_foreground_launcher_canonicalizes_symlinked_ora_home(tmp_path: Path):
    real_home = tmp_path / "ora root"
    link_home = tmp_path / "ora-link"
    link_home.symlink_to(real_home, target_is_directory=True)

    completed, workspace, argv, child_env = _run_with_fake_python(
        tmp_path,
        overrides={"ORA_HOME": str(link_home)},
    )

    assert completed.returncode == 0, completed.stderr
    assert workspace == real_home
    assert child_env["ORA_HOME"] == str(real_home.resolve())
    assert argv[0] == str(real_home.resolve() / "server" / "server.py")


def test_service_stop_kills_only_owned_python_server_not_path_decoys(tmp_path: Path):
    home = tmp_path / "home"
    workspace = home / "ora root"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(parents=True)
    (workspace / "server").mkdir(parents=True)
    (workspace / "server" / "server.py").write_text("# sentinel\n", encoding="utf-8")

    target = workspace / "server" / "server.py"
    killed_state = tmp_path / "killed"
    kill_log = tmp_path / "kill.log"
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

    bash_env = tmp_path / "bash-env"
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


def test_launchd_install_fails_closed_when_expected_instance_never_healthy(tmp_path: Path):
    home = tmp_path / "home"
    workspace = home / "ora"
    fake_bin = tmp_path / "bin"
    logs = workspace / "logs"
    fake_bin.mkdir(parents=True)
    logs.mkdir(parents=True)
    runner = workspace / "run-ora-server.sh"
    runner.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    runner.chmod(0o755)
    (logs / "ora-server.stderr.log").write_text(
        "sentinel launch failure\n", encoding="utf-8"
    )

    state = tmp_path / "launchctl-state"
    launchctl_log = tmp_path / "launchctl.log"
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


def test_worktree_cannot_stop_or_uninstall_service_owned_by_other_checkout(tmp_path: Path):
    home = tmp_path / "home"
    canonical = home / "ora"
    worktree = home / "ora-worktrees" / "feature"
    fake_bin = tmp_path / "bin"
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

    state = tmp_path / "launchctl-state"
    state.touch()
    launchctl_log = tmp_path / "launchctl.log"
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
