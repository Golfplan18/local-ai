"""File search tools: grep across files and directory listing."""

import os
import subprocess


def grep_files(pattern: str, directory: str, file_extension: str = None,
               max_results: int = 50) -> list:
    """Search for a text pattern across files in a directory.

    Returns list of {file, line_number, content} dicts, capped at max_results.
    """
    directory = os.path.expanduser(directory)
    if not os.path.isdir(directory):
        return [{"error": f"Directory not found: {directory}"}]

    cmd = ["grep", "-rn", "--", pattern, directory]
    if file_extension:
        ext = file_extension.lstrip(".")
        cmd = ["grep", "-rn", f"--include=*.{ext}", "--", pattern, directory]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )
        lines = result.stdout.strip().splitlines()
        results = []
        for line in lines[:max_results]:
            # Format: path:line_number:content
            parts = line.split(":", 2)
            if len(parts) >= 3:
                results.append({
                    "file": parts[0],
                    "line_number": int(parts[1]) if parts[1].isdigit() else 0,
                    "content": parts[2],
                })
            else:
                results.append({"file": line, "line_number": 0, "content": ""})
        if len(lines) > max_results:
            results.append({
                "file": "(truncated)",
                "line_number": 0,
                "content": f"Showing {max_results} of {len(lines)} matches",
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
