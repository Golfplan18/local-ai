#!/usr/bin/env python3
"""Ora Execution Review — render validity check (self-contained).

Execution Review Phase 8 Chunk C (§4.4). SELF-CONTAINED, stdlib-only mechanical
validity of rendered artifacts: file exists, nonzero, and PARSES. Perceptual
quality is NOT checked here — it stays a judgment lane with ``verdict: null`` by
construction (the §5 category-error guard).

  * .svg / .xml            → well-formed XML (xml.etree parse)
  * .docx / .pptx / .xlsx  → a valid zip that opens (OOXML container)
  * .pdf                   → ``%PDF-`` header
  * anything else          → skipped (not this tool's business)

Inputs (read-only, via ``$ORA_CHECK_INPUTS``):
  changed-files.txt   one repo-relative path per line

A file listed but missing on disk is skipped (never a false FAIL — a deleted
artifact is not an invalid one).

stdout: JSON {"checked", "invalid":[{file,reason}], "skipped_ext", "skipped_missing",
              "ok"}
exit:   0 iff ok, 1 on findings, 2 usage error.
"""
import json
import os
import sys
import zipfile

_XML_EXT = (".svg", ".xml")
_ZIP_EXT = (".docx", ".pptx", ".xlsx")
_ALL_EXT = _XML_EXT + _ZIP_EXT + (".pdf",)


def _changed_files() -> list:
    d = os.environ.get("ORA_CHECK_INPUTS")
    if not d:
        return []
    try:
        with open(os.path.join(d, "changed-files.txt"), "r",
                  encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip()]
    except OSError:
        return []


def _validate(rel: str) -> str | None:
    """Return a failure reason, or None if valid."""
    try:
        if os.path.getsize(rel) == 0:
            return "empty file"
    except OSError as e:
        return f"stat error: {e}"
    low = rel.lower()
    if low.endswith(_XML_EXT):
        try:
            import xml.etree.ElementTree as ET
            ET.parse(rel)
            return None
        except Exception as e:
            return f"XML parse error: {str(e)[:120]}"
    if low.endswith(_ZIP_EXT):
        try:
            with zipfile.ZipFile(rel) as z:
                bad = z.testzip()
                if bad is not None:
                    return f"corrupt zip entry: {bad}"
            return None
        except Exception as e:
            return f"not a valid OOXML zip: {str(e)[:120]}"
    if low.endswith(".pdf"):
        try:
            with open(rel, "rb") as f:
                head = f.read(5)
            if head != b"%PDF-":
                return "missing %PDF- header"
            return None
        except Exception as e:
            return f"read error: {str(e)[:120]}"
    return None  # unreachable — extension pre-filtered


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    changed = _changed_files()
    invalid = []
    skipped_ext = 0
    skipped_missing = []
    checked = 0
    for rel in changed:
        if not rel.lower().endswith(_ALL_EXT):
            skipped_ext += 1
            continue
        if not os.path.isfile(rel):
            skipped_missing.append(rel)
            continue
        checked += 1
        reason = _validate(rel)
        if reason:
            invalid.append({"file": rel, "reason": reason})
    ok = not invalid
    print(json.dumps({
        "checked": checked, "invalid": invalid, "skipped_ext": skipped_ext,
        "skipped_missing": skipped_missing, "ok": ok}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
