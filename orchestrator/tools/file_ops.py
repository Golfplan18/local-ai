"""File read and write tools with safety validation."""

import fnmatch
import os
import stat

# Roots come from the single cross-platform source (runtime_paths), so a Windows
# install or an ORA_HOME/ORA_VAULT relocation is honored — not the old hardcoded
# ~/ora, ~/Documents/vault defaults. Guarded import mirrors dispatcher.py.
try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover - package-qualified fallback
    from orchestrator import runtime_paths as _rp

WORKSPACE = _rp.WORKSPACE
VAULT = _rp.VAULT_STR
CONVERSATIONS = _rp.CONVERSATIONS_STR

DENY_LIST = [".ssh", ".gnupg", ".env", "id_rsa", "id_ed25519", ".netrc",
             "credentials", "secrets", "token", ".aws/credentials"]

ALLOWED_BASES = [WORKSPACE, VAULT, CONVERSATIONS]


def model_read_blocked(path: str, *, shell_scope: bool = False,
                       recursive: bool = False) -> bool:
    """Return whether a model read could expose the archived self-spec.

    File tools block the exact archive. Shell reads are more conservative:
    the shell expands globs after profiling, and recursive readers can walk
    from an ancestor into the archive, so their declared scope is denied too.
    """
    resolved = os.path.realpath(os.path.expanduser(path))
    self_spec = os.path.realpath(os.path.join(str(_rp.ORA_HOME),
                                              "mindspec", "self-spec.md"))
    normalized = os.path.normcase(resolved)
    normalized_self_spec = os.path.normcase(self_spec)
    if normalized == normalized_self_spec:
        return True
    if not shell_scope:
        return False

    candidates = [normalized_self_spec]
    if recursive:
        parent = os.path.dirname(normalized_self_spec)
        while parent and parent != os.path.dirname(parent):
            candidates.append(parent)
            parent = os.path.dirname(parent)
        if parent:
            candidates.append(parent)
    try:
        try:
            import system_protection
        except ImportError:  # pragma: no cover
            from orchestrator import system_protection
        patterns = system_protection._brace_expansions(normalized)
    except Exception:
        return True
    if not patterns:
        return True
    return any(
        fnmatch.fnmatchcase(candidate, pattern)
        for pattern in patterns for candidate in candidates
    )


def _validate_path(path: str) -> tuple[bool, str]:
    """Return (allowed, reason). Blocks dangerous paths."""
    try:
        try:
            import system_protection
        except ImportError:  # pragma: no cover
            from orchestrator import system_protection
        if system_protection.approval_authority_conflict(path):
            return False, "Access denied to approval authority state"
    except Exception:
        # Failure to classify authority state cannot make a generic file
        # boundary permissive.
        return False, "Approval authority classification unavailable"
    path = os.path.realpath(os.path.expanduser(path))

    # Block path traversal
    if ".." in path:
        return False, f"Path traversal not allowed: {path}"

    # Block deny-listed patterns — separator-normalized + case-folded so Windows
    # backslash paths still match the '/'-shaped patterns (W1 class, §7).
    path_match = path.replace("\\", "/").lower()
    for pattern in DENY_LIST:
        if pattern in path_match:
            return False, f"Access denied to sensitive path: {pattern}"

    # Must be within an allowed base — boundary-anchored + case-normalized, so a
    # mere-prefix sibling can't slip through (runtime_paths.within_any_base).
    if _rp.within_any_base(path, ALLOWED_BASES):
        return True, "allowed"

    return False, f"Path outside allowed locations: {path}"


def file_read(path: str) -> str:
    allowed, reason = _validate_path(path)
    if not allowed:
        return f"BLOCKED: {reason}"
    path = os.path.realpath(os.path.expanduser(path))
    if model_read_blocked(path):
        return "BLOCKED: archived MindSpec self-spec is not model-readable"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"File not found: {path}"
    except Exception as e:
        return f"Read error: {str(e)}"


def file_write(path: str, content: str) -> str:
    allowed, reason = _validate_path(path)
    if not allowed:
        return f"BLOCKED: {reason}"
    path = os.path.realpath(os.path.expanduser(path))
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            mode = stat.S_IMODE(os.stat(path, follow_symlinks=False).st_mode)
        except FileNotFoundError:
            mode = 0o600
        _rp.atomic_write_text(path, content, mode=mode)
        return f"Written: {path} ({len(content)} characters)"
    except Exception as e:
        return f"Write error: {str(e)}"
