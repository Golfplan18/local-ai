#!/usr/bin/env python3
"""Stage 7 — apply the migration to the vault.

ONE-TIME MIGRATION TOOL. Delete with the rest of scripts/engram-migration/.

This is the only destructive step. It writes one permanent note per KEEP unit,
deletes the member notes that were absorbed into it, moves RESOURCES units to
Resources/, and moves ARCHIVE units to a dated Archive/ subdirectory.

Safety properties, in order of importance:

  * DRY RUN BY DEFAULT. --apply is required to touch anything.
  * REFUSES TO RUN while Stage 6 reports any HARD violation. A HARD violation is
    silent corruption (a fabricated Instance specific, a note with no claim in
    it), and once members are deleted the original is gone from the working tree.
  * Git is the undo. This runs inside the engram-work worktree on its own branch;
    every delete and move is recoverable with git checkout.
  * IDEMPOTENT. A unit whose members are already gone is skipped, so an
    interrupted run can be re-invoked safely.
  * Provenance is preserved, not discarded: every merged note records the files
    it absorbed and their sources.

The `relationships` frontmatter is deliberately DROPPED. All 1,020,227 existing
edges are keyed by claim sentence -- the target note's H1 -- and every title
changes here, so 99.6% of them would dangle. Stage 10 rebuilds the graph against
the new titles.
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

ARCHIVE_SUBDIR = "Engram Over-extraction 2026-08"
# Absorbed members are moved here rather than deleted, so a merged note can
# always be audited against the sources it claims to summarise.
ABSORBED_SUBDIR = "Engram Absorbed Sources 2026-08"

_SLUG_STRIP = re.compile(r"[^a-z0-9\s\-]+")
_SLUG_WS = re.compile(r"[\s\-]+")


def slugify(text: str, max_words: int = 8) -> str:
    s = _SLUG_STRIP.sub(" ", (text or "").lower())
    parts = [p for p in _SLUG_WS.sub("-", s).strip("-").split("-") if p]
    return "-".join(parts[:max_words]) or "untitled"


def yaml_escape(v) -> str:
    s = "" if v is None else str(v)
    if not s:
        return "''"
    if any(c in s for c in ":#[]{},&*!|>'\"%@`\n") or s.strip() != s:
        return "'" + s.replace("'", "''") + "'"
    return s


def parse_front(text: str) -> tuple[dict, str]:
    """Minimal frontmatter reader — scalar keys only, which is all we need."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm: dict[str, str] = {}
    for line in parts[1].splitlines():
        m = re.match(r"^([a-z_][a-z0-9_ ]*):\s*(.*)$", line)
        if m and m.group(2).strip():
            fm[m.group(1).strip()] = m.group(2).strip()
    return fm, parts[2]


def build_note(rec: dict, members: list[dict], engrams: Path) -> tuple[str, str]:
    """Return (filename, content) for a merged permanent note."""
    fronts, dates, sources, platforms, nexus = [], [], [], [], ""
    for m in members:
        p = engrams / m["file"]
        if not p.exists():
            continue
        fm, _ = parse_front(p.read_text(encoding="utf-8", errors="replace"))
        fronts.append(fm)
        if fm.get("date created"):
            dates.append(fm["date created"])
        for key in ("source_chat", "source_path"):
            if fm.get(key):
                sources.append(fm[key])
        if fm.get("source_platform"):
            platforms.append(fm["source_platform"])
        if not nexus and fm.get("nexus") and fm["nexus"] not in ("null", "~"):
            nexus = fm["nexus"]

    created = min(dates) if dates else date.today().isoformat()
    today = date.today().isoformat()
    types = [m.get("type") for m in members if m.get("type")]
    note_type = collections.Counter(types).most_common(1)[0][0] if types else "principle"

    lines = ["---"]
    lines.append(f"nexus: {yaml_escape(nexus) if nexus else ''}")
    lines.append("type: engram")
    lines.append("tags:")
    lines.append("  - atomic")
    lines.append(f"  - {note_type}")
    lines.append(f"date created: {created}")
    lines.append(f"date modified: {today}")
    if rec.get("standard_concept"):
        lines.append(f"standard_concept: {yaml_escape(rec['standard_concept'])}")
    lines.append(f"absorbed_count: {len(members)}")
    lines.append("absorbed_from:")
    for m in members:
        lines.append(f"  - {yaml_escape(m['file'])}")
    if sources:
        lines.append("sources:")
        for s in sorted(set(sources))[:12]:
            lines.append(f"  - {yaml_escape(s)}")
    if platforms:
        lines.append(f"source_platforms: {yaml_escape(','.join(sorted(set(platforms))))}")
    lines.append("migration: permanent-note-2026-08")
    # Which model wrote this note. A later quality pass can then target
    # exactly the population written by a given model instead of
    # re-auditing the whole corpus.
    if rec.get("written_by"):
        lines.append(f"written_by: {yaml_escape(rec['written_by'])}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {rec['new_title']}")
    lines.append("")
    lines.append((rec.get("new_body") or "").strip())
    lines.append("")
    content = "\n".join(lines) + "\n"

    fname = f"{created}_{slugify(rec['new_title'])}.md"
    return fname, content


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", default=str(Path.home() / "engram-work"))
    ap.add_argument("--migration", default=str(Path.home() / "engram-work" / ".migration"))
    ap.add_argument("--apply", action="store_true",
                    help="actually write/move/delete (default is a dry run)")
    ap.add_argument("--allow-hard", action="store_true",
                    help="proceed despite HARD violations — do not use casually")
    args = ap.parse_args()

    vault = Path(args.vault)
    M = Path(args.migration)
    engrams = vault / "Engrams"
    resources = vault / "Resources"
    archive = vault / "Archive" / ARCHIVE_SUBDIR
    absorbed = vault / "Archive" / ABSORBED_SUBDIR

    # HARD-violation gate
    rp = M / "repair.json"
    if rp.exists():
        hard = [r for r in json.loads(rp.read_text())
                if any(v.startswith("HARD") for v in r.get("violations", []))]
        if hard and not args.allow_hard:
            print(f"[stage7] REFUSING: {len(hard):,} records carry a HARD violation "
                  f"(fabricated specific, missing Instance, or no mechanism).\n"
                  f"[stage7] Repair them first, or pass --allow-hard if you have "
                  f"reviewed every one.", file=sys.stderr)
            return 2
    else:
        print("[stage7] note: no repair.json — run stage6_check.py first", file=sys.stderr)

    # unit -> members, from the shards
    members_of: dict[str, list[dict]] = {}
    for p in sorted((M / "shards").glob("shard_*.json")):
        for u in json.loads(p.read_text()):
            members_of[u["unit_id"]] = u["members"]

    # stage 3 verdicts (authoritative for RESOURCES / ARCHIVE units that never
    # reached stage 5)
    v3: dict[str, str] = {}
    for p in sorted((M / "stage3").glob("result_*.json")):
        try:
            recs = json.loads(p.read_text())
        except Exception:
            continue
        for r in (recs if isinstance(recs, list) else recs.get("results", [])):
            if r.get("unit_id"):
                v3[r["unit_id"]] = r.get("verdict", "")

    # stage 5 written notes
    s5: dict[str, dict] = {}
    for p in sorted((M / "stage5").glob("result_*.json")):
        try:
            recs = json.loads(p.read_text())
        except Exception:
            continue
        for r in (recs if isinstance(recs, list) else recs.get("results", [])):
            if r.get("unit_id"):
                s5[r["unit_id"]] = r

    stats = collections.Counter()
    written: set[str] = set()
    do = args.apply
    if do:
        engrams.mkdir(parents=True, exist_ok=True)
        resources.mkdir(parents=True, exist_ok=True)
        archive.mkdir(parents=True, exist_ok=True)
        absorbed.mkdir(parents=True, exist_ok=True)

    for uid, members in members_of.items():
        verdict = (s5.get(uid) or {}).get("verdict") or v3.get(uid) or ""
        present = [m for m in members if (engrams / m["file"]).exists()]
        if not present:
            stats["skipped_already_applied"] += 1
            continue

        if verdict == "KEEP":
            rec = s5.get(uid)
            if not rec or not rec.get("new_title"):
                stats["keep_without_stage5_output"] += 1
                continue
            fname, content = build_note(rec, present, engrams)
            dest = engrams / fname
            n = 1
            while (str(dest) in written) or (dest.exists() and dest.name not in
                                            {m["file"] for m in present}):
                dest = engrams / f"{fname[:-3]}-{n}.md"
                n += 1
            written.add(str(dest))
            if do:
                dest.write_text(content, encoding="utf-8")
                for m in present:
                    f = engrams / m["file"]
                    if f != dest:
                        # ARCHIVE the absorbed member, never delete it.
                        #
                        # The judgement defects in this pipeline are not
                        # mechanically detectable: an invented canonical term, a
                        # paraphrase that failed to raise the level, a silently
                        # dropped facet, a platitude. All of them are structurally
                        # perfect. The ONLY way to find them later is to re-read a
                        # merged note against the sources it claims to summarise --
                        # which is impossible if those sources were deleted.
                        #
                        # Keeping them turns a questionable writing pass into a
                        # first draft: absorbed_from plus these files let a later
                        # pass audit and rewrite any note. Cost is ~500 MB of
                        # markdown, against permanently unverifiable output.
                        shutil.move(str(f), str(absorbed / m["file"]))
            stats["notes_written"] += 1
            stats["members_absorbed"] += len(present)

        elif verdict == "RESOURCES":
            for m in present:
                src = engrams / m["file"]
                if do:
                    txt = src.read_text(encoding="utf-8", errors="replace")
                    txt = re.sub(r"^type:\s*engram\s*$", "type: resource",
                                 txt, count=1, flags=re.M)
                    (resources / m["file"]).write_text(txt, encoding="utf-8")
                    src.unlink()
                stats["moved_to_resources"] += 1

        elif verdict == "ARCHIVE":
            for m in present:
                if do:
                    shutil.move(str(engrams / m["file"]), str(archive / m["file"]))
                stats["moved_to_archive"] += 1
        else:
            stats["no_verdict_left_in_place"] += len(present)

    mode = "APPLIED" if do else "DRY RUN (nothing changed)"
    print(f"[stage7] {mode}")
    for k, v in stats.most_common():
        print(f"   {k:30s} {v:8,}")
    remaining = len([p for p in engrams.glob('*.md')])
    delta = stats['members_absorbed'] + stats['moved_to_resources'] + stats['moved_to_archive'] \
        - stats['notes_written']
    print(f"   {'Engrams/ now':30s} {remaining:8,}")
    if not do:
        print(f"   {'would become':30s} {remaining - delta:8,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
