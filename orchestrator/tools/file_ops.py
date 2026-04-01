"""File read and write tools with safety validation."""

import os

WORKSPACE = os.path.expanduser("~/local-ai/")
VAULT = os.path.expanduser("~/Documents/vault/")
CONVERSATIONS = os.path.expanduser("~/Documents/conversations/")

DENY_LIST = [".ssh", ".gnupg", ".env", "id_rsa", "id_ed25519", ".netrc",
             "credentials", "secrets", "token", ".aws/credentials"]

ALLOWED_BASES = [WORKSPACE, VAULT, CONVERSATIONS]


def _validate_path(path: str) -> tuple[bool, str]:
    """Return (allowed, reason). Blocks dangerous paths."""
    path = os.path.realpath(os.path.expanduser(path))

    # Block path traversal
    if ".." in path:
        return False, f"Path traversal not allowed: {path}"

    # Block deny-listed patterns
    path_lower = path.lower()
    for pattern in DENY_LIST:
        if pattern in path_lower:
            return False, f"Access denied to sensitive path: {pattern}"

    # Must be within an allowed base
    for base in ALLOWED_BASES:
        if path.startswith(os.path.realpath(base)):
            return True, "allowed"

    return False, f"Path outside allowed locations: {path}"


def file_read(path: str) -> str:
    allowed, reason = _validate_path(path)
    if not allowed:
        return f"BLOCKED: {reason}"
    path = os.path.expanduser(path)
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
    path = os.path.expanduser(path)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Written: {path} ({len(content)} characters)"
    except Exception as e:
        return f"Write error: {str(e)}"
