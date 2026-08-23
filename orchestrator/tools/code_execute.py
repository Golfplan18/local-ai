"""Sandboxed Python execution (Execution Review Phase 1).

Replaces boot.py's legacy ``_code_execute`` bypass, which ran arbitrary
Python with only proxy-env-var "no network" protection and no gate or
event log. This version runs under macOS ``sandbox-exec`` with:

  - network denied entirely (verified enforceable: socket connect raises
    PermissionError under the profile),
  - file writes confined to a scratch directory + TMPDIR,
  - a minimal environment with no ambient credentials.

Denied-entirely egress plus a write-confined sandbox with no secrets in the
environment satisfies the spec's *orchestrated* enforcement preconditions
(§7: sandbox, prevention-by-absence, egress denied or logged), so events
from this tool carry enforcement_model="orchestrated". When sandbox-exec is
unavailable (non-macOS), the tool reports axes with unknown=True so the
dispatcher gate fails closed instead of running unsandboxed.
"""

from __future__ import annotations

import os
import locale
import math
import signal
import shutil
import subprocess
import sys
import threading
import time

try:
    import runtime_paths as _rp
    WORKSPACE = _rp.WORKSPACE
    _SCRATCH_ROOT = _rp.SCRATCH_DIR_STR
    _PRIVATE_DENY_ROOTS = [_rp.WORKSPACE, _rp.VAULT_STR, _rp.CONVERSATIONS_STR]
except ImportError:  # pragma: no cover
    WORKSPACE = os.path.expanduser("~/ora/")
    _SCRATCH_ROOT = os.path.join(WORKSPACE, "scratch")
    _PRIVATE_DENY_ROOTS = [WORKSPACE,
                           os.path.expanduser("~/Documents/vault"),
                           os.path.expanduser("~/Documents/conversations")]
SCRATCH_DIR = os.path.join(_SCRATCH_ROOT, "code-exec")

# Keep model-generated output from becoming a second memory budget. This is a
# combined stdout/stderr byte cap: the child is terminated as soon as the cap
# is crossed, while reader threads continue draining the pipes until reaping
# is complete. The limit is deliberately generous for normal computation
# results, but finite on a laptop with a large or accidental print loop.
MAX_RESULT_BYTES = 1024 * 1024
_READ_CHUNK_BYTES = 64 * 1024

# Thirty seconds remains the ordinary tool timeout. The upper bound is only an
# emergency ceiling for malformed/model-supplied values such as None, infinity
# or an accidentally enormous integer.
DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 300


def _sandbox_backend() -> str | None:
    """The sandbox implementation for this platform, or None when none is
    available. Phase 1 implements only the macOS ``sandbox-exec`` backend;
    Windows/Linux have no backend and code_execute is unavailable/gated there.
    A Windows sandbox is future work — this is not cross-platform sandboxing."""
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        return "sandbox-exec"
    return None


_SANDBOX_EXEC = shutil.which("sandbox-exec") if sys.platform == "darwin" else None


def sandbox_available() -> bool:
    return _sandbox_backend() is not None


def code_execute_axes() -> dict:
    """Axes for the manifest/gate. Only the macOS sandbox earns the
    'orchestrated' enforcement label; on every other platform there is no
    sandbox → fail closed (gated) and enforcement is never 'orchestrated'."""
    if sandbox_available():
        return {"category": "execute", "mutability": "reversible_write",
                "sensitivity": "private", "egress": "none",
                "enforcement": "orchestrated"}
    return {"category": "execute", "mutability": "irreversible",
            "sensitivity": "secret", "egress": "external",
            "enforcement": "boundary_only", "unknown": True}


def _sandbox_profile(scratch: str, tmpdir: str) -> str:
    # Deny ALL reads under the user's real home AND under every Ora private
    # root, then re-allow only the scratch/tmp dirs the runtime needs (the
    # allows must follow the denies — sandbox-exec is last-match-wins).
    # Without the home deny, arbitrary Python could read any private file
    # under $HOME (~/Documents, ~/ora, ~/.ssh, …) and exfiltrate it via
    # stdout — the one egress channel network-deny doesn't cover. The
    # explicit private roots matter because runtime_paths makes them
    # env-relocatable (ORA_HOME / ORA_VAULT / ORA_CONVERSATIONS): a vault
    # moved OUTSIDE $HOME must stay unreadable, or the tool's declared
    # sensitivity=private / egress=none axes would be false. The Python
    # runtime itself (stdlib, site-packages) lives outside these roots
    # (/opt/homebrew, /usr, /System), so the denies don't break compute.
    deny_roots = [os.path.realpath(os.path.expanduser("~"))]
    for root in _PRIVATE_DENY_ROOTS:
        try:
            real = os.path.realpath(os.path.expanduser(str(root)))
        except Exception:
            continue
        if real and real != "/" and real not in deny_roots:
            deny_roots.append(real)
    denies = "".join(
        f'(deny file-read* (subpath "{r}"))' for r in deny_roots)
    return (
        "(version 1)"
        "(allow default)"
        "(deny process-fork)"
        "(deny network*)"
        + denies +
        f'(allow file-read* (subpath "{os.path.realpath(scratch)}"))'
        f'(allow file-read* (subpath "{os.path.realpath(tmpdir)}"))'
        "(deny file-write*)"
        f'(allow file-write* (subpath "{os.path.realpath(scratch)}"))'
        f'(allow file-write* (subpath "{os.path.realpath(tmpdir)}"))'
        '(allow file-write* (subpath "/dev"))'
    )


def _clean_env(scratch: str, tmpdir: str) -> dict:
    """Minimal env: no API keys, no keychain hints, no SSH agent."""
    env = {}
    for key in ("PATH", "LANG", "LC_ALL"):
        if key in os.environ:
            env[key] = os.environ[key]
    env["HOME"] = scratch
    env["TMPDIR"] = tmpdir
    return env


def _normalize_timeout(timeout) -> int | float:
    """Return a finite, non-negative timeout with an emergency ceiling."""
    if timeout is None or isinstance(timeout, bool):
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(timeout)
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_TIMEOUT_SECONDS
    if math.isnan(value) or value < 0:
        return DEFAULT_TIMEOUT_SECONDS
    if math.isinf(value) or value > MAX_TIMEOUT_SECONDS:
        return MAX_TIMEOUT_SECONDS
    if value.is_integer():
        return int(value)
    return value


class _BoundedCapture:
    """Retain at most one combined stdout/stderr result in parent memory."""

    def __init__(self, limit: int):
        self._limit = limit
        self._total = 0
        self._stdout = bytearray()
        self._stderr = bytearray()
        self._lock = threading.Lock()
        self.exceeded = threading.Event()

    def add(self, stream: str, chunk: bytes) -> None:
        with self._lock:
            remaining = self._limit - self._total
            if remaining > 0:
                kept = chunk[:remaining]
                if stream == "stdout":
                    self._stdout.extend(kept)
                else:
                    self._stderr.extend(kept)
                self._total += len(kept)
            if len(chunk) > max(remaining, 0):
                self.exceeded.set()

    def values(self) -> tuple[bytes, bytes]:
        with self._lock:
            return bytes(self._stdout), bytes(self._stderr)


def _drain_pipe(pipe, capture: _BoundedCapture, stream: str) -> None:
    """Drain a child pipe without retaining more than the combined cap."""
    try:
        while True:
            chunk = pipe.read(_READ_CHUNK_BYTES)
            if not chunk:
                return
            capture.add(stream, chunk)
    finally:
        pipe.close()


def _terminate_process_group(process: subprocess.Popen) -> None:
    """Kill and reap the process group created for one code-execute call."""
    try:
        # start_new_session=True makes the Popen PID the group leader, so this
        # also removes any owned descendants that could otherwise keep a pipe
        # open after the Python parent exits.
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        # The process may have exited between the poll and kill. The direct
        # fallback still handles platforms/test doubles without killpg.
        try:
            process.kill()
        except (OSError, ProcessLookupError):
            pass
    try:
        process.wait()
    except ChildProcessError:
        # A prior poll/wait already reaped it; there is no child left to reap.
        pass


def _decode_capture(value: bytes) -> str:
    encoding = locale.getpreferredencoding(False) or "utf-8"
    return value.decode(encoding, errors="replace")


def _format_result(stdout: bytes, stderr: bytes, *, truncated: bool) -> str:
    out = _decode_capture(stdout).strip()
    err = _decode_capture(stderr).strip()
    if err:
        result = f"{out}\n[stderr] {err}".strip()
    else:
        result = out or "[code_execute] (no output)"
    if truncated:
        marker = (f"[code_execute] Output truncated after {MAX_RESULT_BYTES} "
                  "bytes; process terminated.")
        return f"{result}\n{marker}".strip()
    return result


def code_execute(code: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    """Run Python code in the sandbox. Returns stdout (+ prefixed stderr)."""
    if not code.strip():
        return "[code_execute] No code provided."
    if not sandbox_available():
        return (f"[code_execute unavailable on this platform "
                f"({sys.platform}) — Phase 1 sandboxing is macOS-only "
                f"(sandbox-exec). The action is gated, never run "
                f"unsandboxed.]")
    effective_timeout = _normalize_timeout(timeout)
    os.makedirs(SCRATCH_DIR, exist_ok=True)
    tmpdir = os.path.join(SCRATCH_DIR, "tmp")
    os.makedirs(tmpdir, exist_ok=True)
    profile = _sandbox_profile(SCRATCH_DIR, tmpdir)
    process = None
    capture = _BoundedCapture(MAX_RESULT_BYTES)
    readers = []
    try:
        process = subprocess.Popen(
            [_SANDBOX_EXEC, "-p", profile, sys.executable, "-c", code],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False,
            cwd=SCRATCH_DIR, env=_clean_env(SCRATCH_DIR, tmpdir),
            start_new_session=True,
        )
        readers = [
            threading.Thread(target=_drain_pipe,
                              args=(process.stdout, capture, "stdout")),
            threading.Thread(target=_drain_pipe,
                              args=(process.stderr, capture, "stderr")),
        ]
        for reader in readers:
            reader.start()

        timed_out = False
        truncated = False
        deadline = time.monotonic() + effective_timeout
        while process.poll() is None:
            if capture.exceeded.is_set():
                truncated = True
                _terminate_process_group(process)
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                _terminate_process_group(process)
                break
            try:
                process.wait(timeout=min(remaining, 0.05))
            except subprocess.TimeoutExpired:
                continue

        # A short-lived process can finish before the reader observes the
        # final over-cap chunk. Check once more before joining the drainers.
        if capture.exceeded.is_set() and not timed_out:
            truncated = True
            _terminate_process_group(process)
        for reader in readers:
            reader.join()
        if timed_out:
            return f"[code_execute] Timeout after {effective_timeout}s"
        return _format_result(*capture.values(), truncated=truncated or
                              capture.exceeded.is_set())
    except Exception as e:
        if process is not None:
            _terminate_process_group(process)
        for reader in readers:
            reader.join()
        return f"[code_execute] {e}"
