"""Targeted file editing — replace a unique string in a file."""

import os


def edit_file(file_path: str, old_string: str, new_string: str) -> dict:
    """Replace old_string with new_string in file_path.

    old_string must appear exactly once in the file.
    Path validation is handled by the dispatcher, not here.
    """
    file_path = os.path.expanduser(file_path)

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
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
    except Exception as e:
        return {"success": False, "error": f"Write error: {e}"}

    return {
        "success": True,
        "file": file_path,
        "chars_replaced": len(old_string),
        "chars_inserted": len(new_string),
    }
