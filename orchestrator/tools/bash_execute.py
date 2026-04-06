"""Bash command execution with safety classification, output truncation,
working directory containment, and background process management."""

import os
import re
import signal
import subprocess
import time

WORKSPACE = os.path.expanduser("~/local-ai/")

# ── Background process tracking ────────────────────────────────────────────
MANAGED_PROCESSES = []

# ── Command classifier (deterministic, rule-based) ─────────────────────────

BLOCKED_PATTERNS = [
    r"sudo\s+rm\s+-rf\s+/\s*$",
    r":\(\)\{\s*:\|:&\s*\};:",        # fork bomb
    r">\s*/dev/sd[a-z]",
    r"\bmkfs\b",
    r"(>|>>)\s*/(System|usr|bin|sbin|etc)/",
]

DANGEROUS_PATTERNS = [
    (r"\brm\b", "rm command detected — may delete files"),
    (r"\bchmod\b", "chmod changes file permissions"),
    (r"\bchown\b", "chown changes file ownership"),
    (r"\bsudo\b", "sudo runs with elevated privileges"),
    (r"curl\s.*\|\s*(sh|bash)", "piped download to shell — arbitrary code execution"),
    (r"wget\s.*\|\s*(sh|bash)", "piped download to shell — arbitrary code execution"),
    (r"\bdd\b", "dd writes raw data — can overwrite devices"),
    (r"\bkill\b", "kill terminates processes"),
    (r"\bpkill\b", "pkill terminates processes by pattern"),
    (r"\bsystemctl\b", "systemctl modifies system services"),
    (r"\blaunchctl\b", "launchctl modifies macOS services"),
    (r"/\s+-rf\b", "recursive force deletion with broad scope"),
    (r"\bfind\b.*-delete\b", "find with -delete removes matching files"),
]

SAFE_COMMANDS = {
    "echo", "cat", "ls", "pwd", "whoami", "date", "which", "uname",
    "head", "tail", "wc", "grep", "rg", "find", "python3", "python",
    "git", "npm", "node", "pip3", "pip", "brew",
}

SAFE_GIT_SUBCOMMANDS = {"status", "log", "diff", "branch", "show", "tag", "remote"}


def classify_command(command_string: str) -> dict:
    """Classify a command by risk level. Returns {level, reason}."""
    cmd = command_string.strip()

    # Rule 1: blocked patterns
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, cmd):
            return {"level": "blocked",
                    "reason": f"This command could cause irreversible system damage: matched pattern '{pattern}'"}

    # Rule 2: dangerous patterns
    for pattern, reason in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd):
            return {"level": "dangerous", "reason": reason}

    # Rule 3: check file paths for out-of-workspace references
    ws_real = os.path.realpath(WORKSPACE)
    sensitive_dirs = ["/System", "/usr", "/bin", "/sbin", "/etc",
                      "/Library", "/var", "/private"]
    # Simple path extraction: tokens starting with / or ~
    tokens = cmd.split()
    for token in tokens:
        if token.startswith("/") or token.startswith("~"):
            resolved = os.path.realpath(os.path.expanduser(token))
            for sd in sensitive_dirs:
                if resolved.startswith(sd):
                    return {"level": "dangerous",
                            "reason": f"Command references sensitive directory: {resolved}"}

    # Rule 4: safe commands
    base_cmd = cmd.split("|")[0].strip().split()[0] if cmd.strip() else ""
    # Handle path-qualified commands
    base_cmd = os.path.basename(base_cmd)

    if base_cmd in SAFE_COMMANDS:
        # Special handling for git — only read-only subcommands are safe
        if base_cmd == "git":
            parts = cmd.split("|")[0].strip().split()
            if len(parts) >= 2 and parts[1] in SAFE_GIT_SUBCOMMANDS:
                return {"level": "safe", "reason": f"Read-only git command: git {parts[1]}"}
            return {"level": "moderate", "reason": f"Git write command: {' '.join(parts[:2])}"}
        return {"level": "safe", "reason": "Read-only command within workspace"}

    # Rule 5: default to moderate
    return {"level": "moderate", "reason": "Unclassified command — treated as moderate risk"}


# ── Command execution ──────────────────────────────────────────────────────

def _clean_env() -> dict:
    """Construct a clean subprocess environment."""
    parent = os.environ
    env = {}
    for key in ("PATH", "HOME", "USER", "LANG", "LC_ALL", "TERM", "SHELL",
                "TMPDIR", "SSH_AUTH_SOCK"):
        if key in parent:
            env[key] = parent[key]
    env["WORKSPACE"] = WORKSPACE
    return env


def execute_command(command_string: str, timeout: int = 60,
                    cwd: str = None, background: bool = False,
                    max_output_chars: int = 10000) -> dict:
    """Execute a shell command with safety controls.

    Args:
        command_string: The command to run.
        timeout: Max seconds before killing (ignored for background).
        cwd: Working directory (defaults to WORKSPACE).
        background: If True, run via Popen and return immediately.
        max_output_chars: Truncate stdout/stderr beyond this limit.
    """
    if cwd is None:
        cwd = WORKSPACE

    # Detect background intent from trailing &
    if command_string.rstrip().endswith("&") and not background:
        background = True
        command_string = command_string.rstrip().rstrip("&").rstrip()

    env = _clean_env()

    if background:
        try:
            proc = subprocess.Popen(
                command_string, shell=True, cwd=cwd, env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            MANAGED_PROCESSES.append(proc)
            return {
                "pid": proc.pid,
                "status": "started in background",
                "managed_pids": [p.pid for p in MANAGED_PROCESSES if p.poll() is None],
            }
        except Exception as e:
            return {"pid": None, "status": f"failed to start: {e}"}

    # Foreground execution
    try:
        result = subprocess.run(
            command_string, shell=True, capture_output=True,
            text=True, timeout=timeout, cwd=cwd, env=env,
        )
        stdout = result.stdout
        stderr = result.stderr

        # Output truncation
        truncated = False
        if len(stdout) > max_output_chars:
            total = len(stdout)
            stdout = stdout[:max_output_chars] + (
                f"\n\n[OUTPUT TRUNCATED — showing first {max_output_chars} of "
                f"{total} characters. Pipe through head/tail/grep to narrow results.]"
            )
            truncated = True
        if len(stderr) > max_output_chars:
            total = len(stderr)
            stderr = stderr[:max_output_chars] + (
                f"\n\n[STDERR TRUNCATED — showing first {max_output_chars} of {total} characters.]"
            )
            truncated = True

        return {
            "stdout": stdout,
            "stderr": stderr,
            "returncode": result.returncode,
            "timed_out": False,
            "truncated": truncated,
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds",
            "returncode": -1,
            "timed_out": True,
            "truncated": False,
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "returncode": -1,
            "timed_out": False,
            "truncated": False,
        }


# ── Background process management ─────────────────────────────────────────

def stop_process(pid: int) -> str:
    """Stop a managed background process by PID."""
    target = None
    for proc in MANAGED_PROCESSES:
        if proc.pid == pid:
            target = proc
            break
    if target is None:
        return f"PID {pid} is not a managed process."

    try:
        target.send_signal(signal.SIGTERM)
        try:
            target.wait(timeout=5)
        except subprocess.TimeoutExpired:
            target.kill()
            target.wait(timeout=2)
        MANAGED_PROCESSES.remove(target)
        return f"Process {pid} stopped."
    except Exception as e:
        return f"Error stopping PID {pid}: {e}"


def cleanup_all() -> str:
    """Stop all managed background processes. Called at session end."""
    stopped = []
    for proc in list(MANAGED_PROCESSES):
        try:
            if proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                stopped.append(proc.pid)
        except Exception:
            pass
    MANAGED_PROCESSES.clear()
    if stopped:
        return f"Stopped {len(stopped)} background processes: {stopped}"
    return "No background processes to stop."
