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
import shutil
import subprocess
import sys

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


def code_execute(code: str, timeout: int = 30) -> str:
    """Run Python code in the sandbox. Returns stdout (+ prefixed stderr)."""
    if not code.strip():
        return "[code_execute] No code provided."
    if not sandbox_available():
        return (f"[code_execute unavailable on this platform "
                f"({sys.platform}) — Phase 1 sandboxing is macOS-only "
                f"(sandbox-exec). The action is gated, never run "
                f"unsandboxed.]")
    os.makedirs(SCRATCH_DIR, exist_ok=True)
    tmpdir = os.path.join(SCRATCH_DIR, "tmp")
    os.makedirs(tmpdir, exist_ok=True)
    profile = _sandbox_profile(SCRATCH_DIR, tmpdir)
    try:
        result = subprocess.run(
            [_SANDBOX_EXEC, "-p", profile, sys.executable, "-c", code],
            capture_output=True, text=True, timeout=timeout,
            cwd=SCRATCH_DIR, env=_clean_env(SCRATCH_DIR, tmpdir),
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if err:
            return f"{out}\n[stderr] {err}".strip()
        return out or "[code_execute] (no output)"
    except subprocess.TimeoutExpired:
        return f"[code_execute] Timeout after {timeout}s"
    except Exception as e:
        return f"[code_execute] {e}"
