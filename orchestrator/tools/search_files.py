"""File search tools: grep across files and directory listing."""

import os
import re
import shutil
import subprocess

# Execution Review: recursive grep over an allowed private root (e.g. ~/ora)
# can still traverse INTO secret/sensitive descendants (.env, .ssh, a
# credentials file) and return their contents. The dispatcher gates the
# requested ROOT by its sensitivity, but not per-descendant — so this module
# withholds secret/sensitive descendants from the RESULTS, authoritatively,
# via the tool_events path resolver (boundary-anchored, so a book file named
# 'secrets_of_success.md' is NOT mistaken for a credential file 'secrets.txt').
# The grep-level excludes below are PERFORMANCE ONLY (skip huge/noise dirs) —
# they deliberately do NOT filter by secret name, so legitimate secret-named
# files are not silently dropped; the resolver-based post-filter decides
# withholding and reports a count.

_EXCLUDE_DIRS = ["node_modules", "__pycache__", ".git"]


def _path_is_shielded(path: str) -> bool:
    """True when a result path must be withheld (secret/sensitive), decided
    by the authoritative, boundary-anchored tool_events resolver — the single
    source of truth shared with the shell-read gate."""
    try:
        try:
            import system_protection
        except ImportError:  # pragma: no cover
            from orchestrator import system_protection
        if system_protection.approval_authority_conflict(path):
            return True
        try:
            import tool_events
        except ImportError:
            from orchestrator import tool_events
        return tool_events.resolve_path_sensitivity(path) in ("secret",
                                                              "sensitive")
    except Exception:
        # Fail closed on obvious markers if the resolver is unavailable.
        low = path.lower()
        return any(m in low for m in
                   (".ssh", ".gnupg", ".aws", ".env", "id_rsa", "id_ed25519",
                    ".netrc", "credential", "/secrets", ".pem", ".key",
                    "/creds", "/keys/"))


def _grep_available() -> bool:
    """POSIX `grep` fast-path is used only when the binary exists AND we're
    not on Windows. Everywhere else the Python walker (below) runs. Set
    ORA_SEARCH_PY=1 to force the Python path (used by tests)."""
    if os.environ.get("ORA_SEARCH_PY") == "1":
        return False
    if os.name == "nt":
        return False
    return shutil.which("grep") is not None


def _iter_matches_grep(pattern, directory, file_extension):
    cmd = ["grep", "-rn"]
    for d in _EXCLUDE_DIRS:          # performance/noise only, not secret-name
        cmd.append(f"--exclude-dir={d}")
    if file_extension:
        cmd.append(f"--include=*.{file_extension.lstrip('.')}")
    cmd += ["--", pattern, directory]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    for line in result.stdout.strip().splitlines():
        parts = line.split(":", 2)
        if len(parts) >= 3:
            yield parts[0], (int(parts[1]) if parts[1].isdigit() else 0), parts[2]
        elif line:
            yield line, 0, ""


def _iter_matches_python(pattern, directory, file_extension):
    """Cross-platform fallback: walk the tree, skip noise dirs, and yield
    matching lines. Regex pattern (falls back to literal on bad regex)."""
    try:
        rx = re.compile(pattern)
    except re.error:
        rx = re.compile(re.escape(pattern))
    ext = ("." + file_extension.lstrip(".")) if file_extension else None
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in _EXCLUDE_DIRS]
        for fn in files:
            if ext and not fn.endswith(ext):
                continue
            fpath = os.path.join(root, fn)
            try:
                with open(fpath, "r", errors="ignore") as f:
                    for n, line in enumerate(f, 1):
                        if rx.search(line):
                            yield fpath, n, line.rstrip("\n")
            except (OSError, UnicodeError):
                continue


def grep_files(pattern: str, directory: str, file_extension: str = None,
               max_results: int = 50) -> list:
    """Search for a text pattern across files in a directory.

    Returns list of {file, line_number, content} dicts, capped at max_results.
    Secret/sensitive descendants are excluded so a recursive search over an
    allowed private root cannot leak credential file contents. Uses POSIX
    `grep` when available for speed, else a cross-platform Python walker;
    BOTH pass results through the same secret-descendant withholding filter.
    """
    try:
        try:
            import system_protection
        except ImportError:  # pragma: no cover
            from orchestrator import system_protection
        if system_protection.approval_authority_conflict(
            directory, recursive=True, patterns=True,
        ):
            return [{"error": "BLOCKED: approval authority state"}]
    except Exception:
        return [{"error": "BLOCKED: authority classification unavailable"}]

    directory = os.path.expanduser(directory)
    if not os.path.isdir(directory):
        return [{"error": f"Directory not found: {directory}"}]

    source = (_iter_matches_grep if _grep_available()
              else _iter_matches_python)
    try:
        results = []
        shielded = 0
        total = 0
        for fpath, lineno, content in source(pattern, directory, file_extension):
            total += 1
            # Authoritative per-result exclusion (identical for both backends).
            if _path_is_shielded(fpath):
                shielded += 1
                continue
            if len(results) < max_results:
                results.append({"file": fpath, "line_number": lineno,
                                "content": content})
        remaining = total - len(results) - shielded
        if remaining > 0:
            results.append({
                "file": "(truncated)", "line_number": 0,
                "content": f"Showing {len(results)} of "
                           f"{len(results) + remaining} matches",
            })
        if shielded:
            results.append({
                "file": "(withheld)", "line_number": 0,
                "content": f"{shielded} match(es) in secret/sensitive files "
                           f"were excluded from results.",
            })
        return results
    except subprocess.TimeoutExpired:
        return [{"error": "Search timed out after 30 seconds"}]
    except Exception as e:
        return [{"error": str(e)}]


def list_directory(path: str, max_depth: int = 2) -> str:
    """List files and directories up to max_depth levels deep.

    Excludes hidden files/directories (starting with .) and node_modules.
    Returns a formatted directory tree string.
    """
    try:
        try:
            import system_protection
        except ImportError:  # pragma: no cover
            from orchestrator import system_protection
        if system_protection.approval_authority_conflict(
            path, recursive=True, patterns=True,
        ):
            return "BLOCKED: approval authority state"
    except Exception:
        return "BLOCKED: authority classification unavailable"

    path = os.path.expanduser(path)
    if not os.path.isdir(path):
        return f"Directory not found: {path}"

    lines = []
    base_depth = path.rstrip(os.sep).count(os.sep)

    for root, dirs, files in os.walk(path):
        current_depth = root.rstrip(os.sep).count(os.sep) - base_depth
        if current_depth >= max_depth:
            dirs.clear()
            continue

        # Filter hidden dirs and node_modules
        dirs[:] = sorted(d for d in dirs
                         if not d.startswith(".") and d != "node_modules"
                         and d != "__pycache__")

        indent = "  " * current_depth
        dirname = os.path.basename(root) or path
        lines.append(f"{indent}{dirname}/")

        # List files (skip hidden)
        file_indent = "  " * (current_depth + 1)
        for f in sorted(files):
            if not f.startswith("."):
                lines.append(f"{file_indent}{f}")

    return "\n".join(lines)
