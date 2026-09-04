"""Targeted file editing — replace a unique string in a file."""

import os
import stat

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover - package-qualified import context
    from orchestrator import runtime_paths as _rp


def edit_file(file_path: str, old_string: str, new_string: str) -> dict:
    """Replace old_string with new_string in file_path.

    old_string must appear exactly once in the file.
    Path validation is handled by the dispatcher, not here.
    """
    try:
        try:
            import system_protection
        except ImportError:  # pragma: no cover
            from orchestrator import system_protection
        if system_protection.approval_authority_conflict(file_path):
            return {"success": False,
                    "error": "BLOCKED: approval authority state"}
    except Exception:
        return {"success": False,
                "error": "BLOCKED: authority classification unavailable"}

    file_path = os.path.realpath(os.path.expanduser(file_path))

    if not os.path.isfile(file_path):
        return {"success": False, "error": f"File not found: {file_path}"}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return {"success": False, "error": f"Read error: {e}"}

    count = content.count(old_string)
    if count == 0:
        return {"success": False, "error": "String not found in file."}
    if count > 1:
        return {"success": False,
                "error": f"String appears {count} times — must be unique for safe replacement."}

    new_content = content.replace(old_string, new_string, 1)

    try:
        mode = stat.S_IMODE(
            os.stat(file_path, follow_symlinks=False).st_mode
        )
        _rp.atomic_write_text(file_path, new_content, mode=mode)
    except Exception as e:
        return {"success": False, "error": f"Write error: {e}"}

    return {
        "success": True,
        "file": file_path,
        "chars_replaced": len(old_string),
        "chars_inserted": len(new_string),
    }
