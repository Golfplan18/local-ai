"""Self-healing Lucide icon set builder.

Rebuilds ``~/ora/server/static/runtime/icon-set.json`` from the live
toolbar / pack configs whenever the source files are newer than the
built set, or the built set is empty. Called at server startup so the
icon registry is always in sync with whatever toolbars currently
exist — no manual ``node lucide-tree-shake.js`` required.

This module is the Python equivalent of ``scripts/lucide-tree-shake.js``.
The Node script remains the canonical reference + manual rebuild path;
this Python version is invoked automatically at server boot so users
who don't have Node installed (or don't think to run the script after
adding a toolbar) still get fresh icons.

Public surface
--------------
``rebuild_if_stale() -> dict`` — main entry point. Returns a small
status dict (``{rebuilt: bool, icon_count: int, reason: str}``) for
logging.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ORA_ROOT = Path(__file__).parent.parent
VENDOR_DIR = ORA_ROOT / "server" / "static" / "vendor" / "lucide"
ICONS_DIR = VENDOR_DIR / "icons"
NAMES_FILE = VENDOR_DIR / "names.json"
TOOLBARS_DIR = ORA_ROOT / "config" / "toolbars"
PACKS_DIR = ORA_ROOT / "config" / "packs"
OUT_PATH = ORA_ROOT / "server" / "static" / "runtime" / "icon-set.json"

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _scan_source_files() -> list[Path]:
    """Every toolbar and pack JSON the icon registry could reference."""
    files: list[Path] = []
    if TOOLBARS_DIR.is_dir():
        files.extend(p for p in TOOLBARS_DIR.glob("*.json") if p.is_file())
    if PACKS_DIR.is_dir():
        files.extend(p for p in PACKS_DIR.rglob("*.json") if p.is_file())
    return sorted(files)


def _collect_icon_refs(value: Any, names: set[str]) -> None:
    """Walk a parsed JSON value and collect every Lucide icon-name
    string assigned to a key literally named ``icon``. Inline SVGs are
    skipped (they don't need vendoring)."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, list):
        for item in value:
            _collect_icon_refs(item, names)
        return
    if isinstance(value, dict):
        for key, sub in value.items():
            if key == "icon" and isinstance(sub, str):
                trimmed = sub.strip()
                if (trimmed
                        and not trimmed[:4].lower() == "<svg"
                        and _NAME_RE.match(trimmed)):
                    names.add(trimmed)
            else:
                _collect_icon_refs(sub, names)


def _load_canonical_names() -> tuple[str, set[str]]:
    if not NAMES_FILE.exists():
        return "unknown", set()
    try:
        payload = json.loads(NAMES_FILE.read_text())
    except Exception:
        return "unknown", set()
    return (
        payload.get("version", "unknown"),
        set(payload.get("names", []) or []),
    )


def _existing_payload() -> dict | None:
    if not OUT_PATH.exists():
        return None
    try:
        return json.loads(OUT_PATH.read_text())
    except Exception:
        return None


def _is_stale(source_files: list[Path], existing: dict | None) -> tuple[bool, str]:
    """Decide whether the icon-set needs rebuilding.

    Stale when:
      * The output file doesn't exist.
      * The output is empty (icon_count == 0) but source files exist.
      * Any source file is newer than the output file.
      * The set of referenced names in source files differs from
        ``existing.referenced_names``.
    """
    if existing is None:
        return True, "icon-set.json missing"
    if not OUT_PATH.exists():
        return True, "icon-set.json missing"

    out_mtime = OUT_PATH.stat().st_mtime
    for src in source_files:
        if src.stat().st_mtime > out_mtime:
            return True, f"source newer: {src.name}"

    # Cheap consistency check — recompute the referenced-name set and
    # compare. Catches the case where someone hand-edited a config to
    # the same mtime as the output (unlikely but possible).
    refs: set[str] = set()
    for src in source_files:
        try:
            data = json.loads(src.read_text())
        except Exception:
            continue
        _collect_icon_refs(data, refs)
    prev = set(existing.get("referenced_names", []) or [])
    if refs != prev:
        return True, "referenced-names changed"

    if existing.get("icon_count", 0) == 0 and refs:
        return True, "previous build empty"
    return False, "up-to-date"


def rebuild_if_stale() -> dict:
    """Rebuild the runtime icon-set if the source files have moved
    on. Returns a status dict suitable for logging.

    Safe to call at every server startup; cheap when the set is
    already fresh (just stats source files).
    """
    sources = _scan_source_files()
    existing = _existing_payload()
    stale, reason = _is_stale(sources, existing)
    if not stale:
        return {
            "rebuilt": False,
            "icon_count": (existing or {}).get("icon_count", 0),
            "reason": reason,
        }

    # Collect referenced names.
    refs: set[str] = set()
    for src in sources:
        try:
            data = json.loads(src.read_text())
        except Exception:
            continue
        _collect_icon_refs(data, refs)

    version, canonical = _load_canonical_names()

    output_names = sorted(n for n in refs if n in canonical) if canonical else sorted(refs)
    unknown = sorted(refs - canonical) if canonical else []

    icons: dict[str, str] = {}
    missing: list[str] = []
    for name in output_names:
        svg_path = ICONS_DIR / f"{name}.svg"
        if svg_path.exists():
            try:
                icons[name] = svg_path.read_text()
            except Exception:
                missing.append(name)
        else:
            missing.append(name)

    payload = {
        "version": version,
        "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "source": "orchestrator/icon_set_builder.py",
        "mode": "tree-shaken" if refs else "no-references-found-no-tree-shake-performed",
        "referenced_from": [str(p.relative_to(ORA_ROOT)) for p in sources],
        "referenced_names": sorted(refs),
        "icon_count": len(icons),
        "icons": icons,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, separators=(",", ":")))

    return {
        "rebuilt": True,
        "icon_count": len(icons),
        "reason": reason,
        "unknown_names": unknown,
        "missing_svgs": missing,
    }


if __name__ == "__main__":
    import pprint
    pprint.pprint(rebuild_if_stale())
