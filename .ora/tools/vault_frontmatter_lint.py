#!/usr/bin/env python3
"""Ora Execution Review — vault frontmatter lint (self-contained check tool).

Execution Review Phase 8 Chunk C (§4.2). A SELF-CONTAINED, import-free check that
runs INSIDE the evidence runner's sandbox: stdlib + PyYAML only (NO
``orchestrator.*`` imports — the sandbox denies reads under ~/ora; NO git — the
delta scope arrives as a harness-built input file). Ships as the canonical
template in ora's own ``.ora/tools/``; copy into any markdown repo's ``.ora/tools/``.

Strict YAML parse of each changed file's leading ``---`` frontmatter block.
Distinguishes MALFORMED (a parse error) from ABSENT (no block) — the gap
``knowledge_index`` / vault-health cannot. A file listed but missing on disk is
skipped (``skipped_missing``), never a crash (a deleted note must not false-FAIL).

Inputs (read-only, via ``$ORA_CHECK_INPUTS``):
  changed-files.txt   one repo-relative path per line (the turn's changed files)

Args:
  --frontmatter optional|required   absent frontmatter FAILs only when 'required'
  --require <k1,k2,...>             required frontmatter keys (checked only on
                                    frontmatter-bearing files)

stdout: JSON {"checked", "malformed":[{file,error}], "missing_frontmatter":[...],
              "missing_required":[{file,keys}], "skipped_missing":[...], "ok"}
exit:   0 iff ok, 1 on findings, 2 usage error, 3 tooling unavailable.
"""
import argparse
import json
import os
import sys


def _changed_files() -> list:
    d = os.environ.get("ORA_CHECK_INPUTS")
    if not d:
        return []
    path = os.path.join(d, "changed-files.txt")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip()]
    except OSError:
        return []


def _read_frontmatter_block(text: str):
    """Return (has_block, raw_yaml) for a leading ``---`` fenced block."""
    if not text.startswith("---"):
        return False, ""
    lines = text.splitlines()
    # first line is '---' (allow a trailing CR already stripped by splitlines)
    if lines and lines[0].strip() != "---":
        return False, ""
    body = []
    for ln in lines[1:]:
        if ln.strip() == "---":
            return True, "\n".join(body)
        body.append(ln)
    # opened but never closed → treat as malformed frontmatter, not absent
    return True, "\n".join(body)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frontmatter", choices=("optional", "required"),
                    default="optional")
    ap.add_argument("--require", default="")
    try:
        args = ap.parse_args()
    except SystemExit:
        return 2

    try:
        import yaml
    except Exception as e:  # pragma: no cover
        print(json.dumps({"error": f"PyYAML unavailable: {e}", "ok": False}))
        return 3

    require_keys = [k.strip() for k in args.require.replace(",", " ").split()
                    if k.strip()]
    changed = [p for p in _changed_files() if p.lower().endswith(".md")]

    malformed = []
    missing_fm = []
    missing_req = []
    skipped_missing = []
    checked = 0
    for rel in changed:
        if not os.path.isfile(rel):
            skipped_missing.append(rel)
            continue
        checked += 1
        try:
            with open(rel, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            skipped_missing.append(rel)
            continue
        has_block, raw = _read_frontmatter_block(text)
        if not has_block:
            if args.frontmatter == "required":
                missing_fm.append(rel)
            continue
        try:
            data = yaml.safe_load(raw)
        except Exception as e:
            malformed.append({"file": rel, "error": str(e)[:200]})
            continue
        if not isinstance(data, dict):
            malformed.append({"file": rel,
                              "error": "frontmatter is not a YAML mapping"})
            continue
        if require_keys:
            missing = [k for k in require_keys if k not in data]
            if missing:
                missing_req.append({"file": rel, "keys": missing})

    ok = not (malformed or missing_fm or missing_req)
    print(json.dumps({
        "checked": checked, "malformed": malformed,
        "missing_frontmatter": missing_fm, "missing_required": missing_req,
        "skipped_missing": skipped_missing, "ok": ok}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
