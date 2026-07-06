#!/usr/bin/env python3
"""Ora Execution Review — vault wikilink integrity check (self-contained).

Execution Review Phase 8 Chunk C (§4.2). SELF-CONTAINED, import-free, NO git: it
resolves body ``[[targets]]`` in the changed markdown files against a
harness-precomputed title universe (built OUTSIDE the sandbox and passed in), so
the check runs stdlib-only inside the evidence runner's sandbox.

Inputs (read-only, via ``$ORA_CHECK_INPUTS``):
  changed-files.txt    one repo-relative path per line (the turn's changed files)
  title-universe.txt   one repo-relative path per line = the note universe as it
                       exists at check time (INCLUDING this turn's new notes)

Resolution (Obsidian bare-title semantics — the live vault link language):
  * a ``.md`` universe entry resolves by its basename minus ``.md``  ([[Title]])
  * a non-``.md`` entry resolves by full basename  (SVG embeds: ![[fig-1.svg]])
  * a target containing ``/`` resolves by full repo-relative path (legacy links)
Alias (``[[t|a]]``), heading (``[[t#h]]``) and embed (``![[t]]``) forms are handled;
the resolvable name is the part before ``|`` / ``#``.

Args:
  --allow-file <repo-relative path>   an allowlist of tolerated exact targets
                                      (one per line; e.g. known legacy dead links)

stdout: JSON {"checked", "links", "dangling":[{file,target}], "allowed_skips",
              "skipped_missing":[...], "ok"}
exit:   0 iff none dangling, 1 on findings, 2 usage error.
"""
import argparse
import json
import os
import re
import sys

_WIKILINK_RE = re.compile(r"!?\[\[([^\]]+)\]\]")


def _inputs_dir() -> str:
    return os.environ.get("ORA_CHECK_INPUTS") or ""


def _read_lines(name: str) -> list:
    d = _inputs_dir()
    if not d:
        return []
    try:
        with open(os.path.join(d, name), "r", encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip()]
    except OSError:
        return []


def _strip_frontmatter(text: str) -> str:
    """Return the body (frontmatter removed) so a YAML value never reads as a link."""
    if not text.startswith("---"):
        return text
    lines = text.splitlines()
    if not (lines and lines[0].strip() == "---"):
        return text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[i + 1:])
    return text  # unterminated → treat whole file as body


def _build_universe(paths: list) -> set:
    """Resolvable names: bare title (basename-minus-.md) for .md, full basename for
    non-.md, plus the full relative path for every entry (path-form targets)."""
    universe = set()
    for p in paths:
        p = p.strip()
        if not p:
            continue
        universe.add(p)                       # full relative path
        base = p.rsplit("/", 1)[-1]
        if base.lower().endswith(".md"):
            universe.add(base[:-3])           # bare title
        else:
            universe.add(base)                # non-.md basename (embeds)
    return universe


def _resolvable(target: str) -> str:
    """The name to resolve: strip alias (``|``) and heading (``#``); keep path form."""
    t = target.strip()
    t = t.split("|", 1)[0].strip()
    t = t.split("#", 1)[0].strip()
    return t


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-file", default="")
    try:
        args = ap.parse_args()
    except SystemExit:
        return 2

    changed = [p for p in _read_lines("changed-files.txt")
               if p.lower().endswith(".md")]
    universe = _build_universe(_read_lines("title-universe.txt"))

    allow = set()
    if args.allow_file:
        try:
            with open(args.allow_file, "r", encoding="utf-8") as f:
                allow = {ln.strip() for ln in f if ln.strip()
                         and not ln.lstrip().startswith("#")}
        except OSError:
            allow = set()

    dangling = []
    skipped_missing = []
    checked = 0
    link_count = 0
    allowed_skips = 0
    for rel in changed:
        if not os.path.isfile(rel):
            skipped_missing.append(rel)
            continue
        checked += 1
        try:
            with open(rel, "r", encoding="utf-8") as f:
                body = _strip_frontmatter(f.read())
        except OSError:
            skipped_missing.append(rel)
            continue
        for m in _WIKILINK_RE.finditer(body):
            raw = m.group(1)
            name = _resolvable(raw)
            if not name:
                continue
            link_count += 1
            if name in universe:
                continue
            if name in allow or raw.strip() in allow:
                allowed_skips += 1
                continue
            dangling.append({"file": rel, "target": name})

    ok = not dangling
    print(json.dumps({
        "checked": checked, "links": link_count, "dangling": dangling,
        "allowed_skips": allowed_skips, "skipped_missing": skipped_missing,
        "ok": ok}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
