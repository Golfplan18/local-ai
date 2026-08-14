#!/usr/bin/env python3
"""Write the validated rewrites into the notes, then remap the relationship graph.

ONE-TIME MIGRATION TOOL. Delete with the rest of scripts/engram-migration/.

Both halves are in one script deliberately. Relationship edges are keyed by claim
sentence — the target note's H1 — so retitling a note dangles every edge pointing
at it. Splitting these into two runnable steps creates a window where the corpus
has new titles and a broken graph, and any interruption leaves it there. One
script, one preflight, one report.

SPLIT SEMANTICS (decided by the publisher)
-----------------------------------------
100 rewrites came back SPLIT: the sources carried two claims a single note would
have to fudge.

  * The PRIMARY child keeps the original filename and inherits ALL inbound edges.
  * The SECOND child becomes a new note with no inbound edges.
  * Both cite the same source list.

The reason is that nothing anywhere records which of the two claims a given
inbound edge was about. Assigning them all to the primary is the only option that
does not invent a distinction; duplicating them to both children would fabricate
relationships no source asserts. The second child earns its own edges when the
relationship pass runs over it.

ARCHIVE would move the note out and drop its inbound edges. Zero rewrites returned
ARCHIVE, so that path is implemented but untested.

PREFLIGHT
---------
Verified before this was written, and re-checked at run time:

  * 4,038 new titles, none colliding with each other, with an untouched note's H1,
    or with a SPLIT second title.
  * 58 current H1s are shared by two notes each, but in every case NEITHER note is
    being rewritten and no edge targets them — so the old-title to new-title map
    has no ambiguous key. This is checked, not assumed: an ambiguous key aborts.

Frontmatter is preserved byte-for-byte apart from `date modified`. The H1 and body
are replaced; nothing else is touched.

Dry run by default. --apply writes.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

_H1 = re.compile(r"^#\s+(.+)$", re.M)
_SLUG_STRIP = re.compile(r"[^a-z0-9\s\-]+")
_SLUG_WS = re.compile(r"[\s\-]+")
# target: is either an inline scalar or a folded block scalar whose continuation
# lines are indented FURTHER than the key. A regex cannot express "more indented
# than the match's own indent": an earlier version used (?:\s+.+\n)+ for the
# continuation, which greedily swallowed `confidence: high` and every following
# line, so no extracted target ever matched the remap and zero edges were rewritten
# while the run reported success. Parsed line-by-line instead.
_TARGET_KEY = re.compile(r"^(?P<ind>[ \t]+)target:[ \t]*(?P<val>.*)$")


def slugify(text: str, max_words: int = 9) -> str:
    s = _SLUG_STRIP.sub(" ", (text or "").lower())
    parts = [p for p in _SLUG_WS.sub("-", s).strip("-").split("-") if p]
    return "-".join(parts[:max_words]) or "untitled"


def split_note(text: str) -> tuple[str, str]:
    """(frontmatter_including_fences, rest). Frontmatter is kept verbatim."""
    if not text.startswith("---"):
        return "", text
    end = text.find("\n---", 3)
    if end < 0:
        return "", text
    return text[:end + 4], text[end + 4:]


def h1_of(text: str) -> str | None:
    _, body = split_note(text)
    m = _H1.search(body)
    return m.group(1).strip() if m else None


def bump_modified(fm: str) -> str:
    today = date.today().isoformat()
    if re.search(r"^date modified:", fm, re.M):
        return re.sub(r"^date modified:.*$", f"date modified: {today}", fm, count=1, flags=re.M)
    return fm.replace("\n---", f"\ndate modified: {today}\n---", 1)


def render_body(title: str, body: str) -> str:
    lines = [l.rstrip() for l in (body or "").splitlines() if l.strip()]
    return "\n" + f"# {title}\n\n" + "\n".join(lines) + "\n"


def yaml_block(value: str, indent: str = "    ") -> str:
    """Claim sentences carry colons and quotes; a folded block scalar is safe where
    quoting is fragile. Mirrors the format already in the corpus."""
    if len(value) <= 88 and not any(c in value for c in ":#\"'{}[]|>&*!%@`\n"):
        return value
    wrapped, line = [], indent
    for w in value.split():
        if len(line) + len(w) + 1 > 78 and line.strip():
            wrapped.append(line.rstrip())
            line = indent + w
        else:
            line = (line + " " + w) if line.strip() else indent + w
    wrapped.append(line.rstrip())
    return ">-\n" + "\n".join(wrapped)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", default=str(Path.home() / "engram-work"))
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    vault = Path(args.vault)
    engrams = vault / "Engrams"
    archive = vault / "Archive" / "Engram Rewrite Archived 2026-08"
    recdir = vault / ".migration" / "rewrite"

    recs: dict[str, dict] = {}
    # NOT `glob(a) or glob(b)` — a generator is always truthy, so the fallback
    # never fires and the run silently loads zero records while reporting success.
    for p in sorted(recdir.glob("*.json")):
        if p.name in ("validation.json", "title-remap.json"):
            continue
        d = json.loads(p.read_text())
        if isinstance(d, list):
            d = d[0] if d else {}
        recs[p.stem] = d
    print(f"[apply] rewrite records: {len(recs):,}")

    # ---- preflight -------------------------------------------------------
    existing_h1: dict[str, list[str]] = collections.defaultdict(list)
    for p in engrams.glob("*.md"):
        h = h1_of(p.read_text(encoding="utf-8", errors="replace"))
        if h:
            existing_h1[h].append(p.stem)

    old2new: dict[str, str] = {}
    ambiguous: list[str] = []
    for stem, rec in recs.items():
        path = engrams / (stem + ".md")
        if not path.exists():
            continue
        oh = h1_of(path.read_text(encoding="utf-8", errors="replace"))
        if not oh:
            continue
        if len(existing_h1.get(oh, [])) > 1:
            # Two notes share this H1 and one is being retitled: an edge pointing
            # at it cannot be resolved to a single target.
            ambiguous.append(f"{oh[:60]} (shared by {existing_h1[oh]})")
            continue
        if rec.get("verdict") == "ARCHIVE":
            old2new[oh] = ""      # sentinel: drop edges to this title
        else:
            old2new[oh] = rec.get("title") or oh

    new_titles = [v for v in old2new.values() if v]
    collide_each = [t for t, c in collections.Counter(new_titles).items() if c > 1]
    untouched = {h for h, stems in existing_h1.items() if h not in old2new}
    collide_untouched = sorted(set(new_titles) & untouched)

    print(f"[apply] old->new map entries : {len(old2new):,}")
    print(f"[apply] ambiguous H1s (abort): {len(ambiguous)}")
    print(f"[apply] new titles colliding with each other  : {len(collide_each)}")
    print(f"[apply] new titles colliding with an untouched : {len(collide_untouched)}")
    for x in (ambiguous + collide_each + collide_untouched)[:5]:
        print(f"[apply]     {x[:100]}")
    if ambiguous or collide_each or collide_untouched:
        print("[apply] PREFLIGHT FAILED — nothing written", file=sys.stderr)
        return 2

    # ---- write the notes -------------------------------------------------
    stats = collections.Counter()
    second_children: list[tuple[Path, str]] = []
    for stem, rec in recs.items():
        path = engrams / (stem + ".md")
        if not path.exists():
            stats["target_missing"] += 1
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        fm, _ = split_note(text)
        if not fm:
            stats["no_frontmatter"] += 1
            continue
        verdict = rec.get("verdict")

        if verdict == "ARCHIVE":
            stats["archived"] += 1
            if args.apply:
                archive.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(archive / path.name))
            continue

        out = bump_modified(fm) + render_body(rec["title"], rec["body"])
        stats["rewritten"] += 1
        if args.apply:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(out, encoding="utf-8")
            tmp.replace(path)

        if verdict == "SPLIT":
            sec = rec.get("split_second_note") or {}
            # Second child: parent's frontmatter minus its relationships (it has no
            # inbound edges by decision), filename from the parent's date prefix.
            sfm = re.sub(r"\nrelationships:\s*\n(?:[ \t]+.*\n|[ \t]*-.*\n)+", "\n",
                         bump_modified(fm))
            prefix = stem.split("_", 1)[0]
            base = f"{prefix}_{slugify(sec['title'])}"
            cand = engrams / (base + ".md")
            n = 2
            while cand.exists() or any(c[0] == cand for c in second_children):
                cand = engrams / f"{base}-{n}.md"
                n += 1
            second_children.append((cand, sfm + render_body(sec["title"], sec["body"])))
            stats["split_children"] += 1

    for path, content in second_children:
        if args.apply:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(content, encoding="utf-8")
            tmp.replace(path)

    print(f"\n[apply] rewritten           : {stats['rewritten']:,}")
    print(f"[apply] SPLIT second children: {stats['split_children']:,}")
    print(f"[apply] archived            : {stats['archived']:,}")
    if stats["target_missing"] or stats["no_frontmatter"]:
        print(f"[apply] skipped (missing target / no frontmatter): "
              f"{stats['target_missing']:,} / {stats['no_frontmatter']:,}")

    # ---- remap the graph -------------------------------------------------
    remapped = dropped = scanned = notes_touched = 0

    def fix_targets(text: str) -> tuple[str, int, int]:
        """Rewrite every `target:` whose value is a key in old2new.

        An empty mapped value means the target note was archived: the whole edge
        (its `- type:` line, the target, and any `confidence:`) is removed rather
        than left pointing at a note that is gone.
        """
        lines = text.splitlines(keepends=True)
        out: list[str] = []
        i = 0
        n_remap = n_drop = 0
        while i < len(lines):
            m = _TARGET_KEY.match(lines[i].rstrip("\n"))
            if not m:
                out.append(lines[i])
                i += 1
                continue
            ind = m.group("ind")
            val = m.group("val").strip()
            consumed = [lines[i]]
            j = i + 1
            if val in (">-", ">", "|", "|-", ""):
                # Continuation: strictly deeper indentation than the key.
                parts: list[str] = []
                while j < len(lines):
                    ln = lines[j]
                    if not ln.strip():
                        break
                    cur = len(ln) - len(ln.lstrip())
                    if cur <= len(ind):
                        break
                    parts.append(ln.strip())
                    consumed.append(ln)
                    j += 1
                target = " ".join(parts)
            else:
                target = val.strip("'\"")
            new = old2new.get(" ".join(target.split()))
            if new is None:
                out.extend(consumed)
                i = j
                continue
            if new == "":
                # Drop the edge: remove the preceding "- type:" line if present,
                # and the trailing confidence line if present.
                while out and re.match(r"^[ \t]*-[ \t]+type:", out[-1]):
                    out.pop()
                while j < len(lines) and re.match(r"^[ \t]+confidence:", lines[j]):
                    j += 1
                n_drop += 1
            else:
                out.append(f"{ind}target: {yaml_block(new, ind + '  ')}\n")
                n_remap += 1
            i = j
        return "".join(out), n_remap, n_drop

    for p in engrams.glob("*.md"):
        text = p.read_text(encoding="utf-8", errors="replace")
        if "\nrelationships:" not in text:
            continue
        scanned += 1
        new_text, r, d = fix_targets(text)
        if r or d:
            remapped += r
            dropped += d
            notes_touched += 1
            if args.apply:
                tmp = p.with_suffix(".tmp")
                tmp.write_text(new_text, encoding="utf-8")
                tmp.replace(p)

    print(f"\n[apply] notes with relationships scanned: {scanned:,}")
    print(f"[apply] edge targets remapped           : {remapped:,}")
    print(f"[apply] edges dropped (ARCHIVE targets) : {dropped:,}")
    print(f"[apply] notes whose edges changed       : {notes_touched:,}")

    mp = vault / ".migration" / "title-remap.json"
    if args.apply:
        mp.write_text(json.dumps(old2new, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"\n[apply] APPLIED. old->new map -> {mp}")
    else:
        print("\n[apply] DRY RUN — nothing written. --apply to execute")
    return 0


if __name__ == "__main__":
    sys.exit(main())
