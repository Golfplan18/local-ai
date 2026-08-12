#!/usr/bin/env python3
"""Repair the migrated engrams with DETERMINISTIC passes. No model calls.

ONE-TIME MIGRATION TOOL. Delete with the rest of scripts/engram-migration/.

WHY THIS EXISTS
---------------
The Stage 5 writing pass produced 64,144 merged notes whose titles and mechanism
bullets are largely sound but whose `Instance:` lines are not. The cause was an
input-design error, not a weak model: the writer never saw the source notes. It
received member titles plus a list of specifics that Stage 3 had extracted --
isolated keywords, bare dates, filename debris, numbers stripped of their units --
and it assembled those fragments into fluent sentences. A 50-note source-grounded
audit found every edited note needed its Instance line changed.

The fix is not to rewrite those sentences better -- it is to delete them. A
fabricated evidence line is worse than no evidence line: the general claim in the
title stands on its own, while a fluent-looking fake invites belief. Provenance
survives in the frontmatter regardless (`sources:` carries the conversation paths
on 100% of merged notes), so deleting the sentence loses nothing that was true.

Nothing here needs judgement, so nothing here can hallucinate:

  PASS 1  Delete the generated `Instance:` line. It is identified structurally
          (a body line whose text begins "Instance:"), not interpreted.

  PASS 2  (OPT-IN, --sources-section) Append a `## Sources` section of wikilinks
          to the archived originals. OFF by default: the publisher intends to
          delete the archive once the good notes exist, and these would then be
          111,133 dead wikilinks. Provenance is already in the frontmatter --
          `absorbed_from` names the originals, `sources:` names the conversations
          (on 100% of merged notes) -- so the body section records nothing new.

  PASS 3  Restore relationships by remapping edge targets. Edges are keyed by
          claim sentence -- the target note's H1 -- so a changed title dangles
          every edge pointing at it. But old-H1 -> new-H1 is fully derivable
          from what is already on disk: each merged note lists the originals it
          absorbed, and each original still carries its own H1 and its own
          relationship block. 110,908 remap pairs cover 955,109 of the 1,020,227
          edges (93.6%). Targets with no remap point at originals that were never
          absorbed into a merged note; they are dropped rather than left dangling.

This replaces the planned Stage 10, which would have re-extracted the graph with
a model. Re-extraction was never necessary: the graph was intact in the archive
the whole time.

Dry run by default. --apply to write.
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

ARCHIVE_SUBDIR = "Archive/Engram Absorbed Sources 2026-08"

_H1 = re.compile(r"^#\s+(.+)$", re.M)
_ABSORBED = re.compile(r"^absorbed_from:\s*\n((?:[ \t]*-[ \t]+\S.*\n)+)", re.M)
# Edge blocks in the originals. target: may wrap across continuation lines, so it
# runs until the next key at the same or shallower depth.
_EDGE = re.compile(
    r"^[ \t]*-[ \t]+type:[ \t]*(\S+)[ \t]*\n"
    r"[ \t]+target:[ \t]*(.+?)"
    r"(?=\n[ \t]+confidence:|\n[ \t]*-[ \t]+type:|\n[a-z_]+:|\n---)",
    re.M | re.S)
_CONF = re.compile(r"^[ \t]+confidence:[ \t]*(\S+)", re.M)


def h1_of(text: str) -> str | None:
    m = _H1.search(text)
    return m.group(1).strip() if m else None


def absorbed_of(text: str) -> list[str]:
    m = _ABSORBED.search(text)
    if not m:
        return []
    return [ln.strip().lstrip("-").strip().strip("'\"")
            for ln in m.group(1).splitlines() if ln.strip()]


def split_note(text: str) -> tuple[str, str]:
    """(frontmatter_block, body) — frontmatter WITHOUT the --- fences."""
    if not text.startswith("---"):
        return "", text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return "", text
    return parts[1], parts[2]


def strip_instance(body: str) -> tuple[str, bool]:
    """Remove the generated Instance line. Structural, not interpretive."""
    out, removed = [], False
    for ln in body.splitlines():
        if ln.strip().lstrip("-").strip().lower().startswith("instance:"):
            removed = True
            continue
        out.append(ln)
    return "\n".join(out), removed


def edges_from(text: str) -> list[tuple[str, str, str]]:
    """(type, target, confidence) from an original's relationships block."""
    i = text.find("relationships:")
    if i < 0:
        return []
    block = text[i:]
    end = re.search(r"\n---", block)
    if end:
        block = block[:end.start()]
    out = []
    for m in _EDGE.finditer(block):
        etype = m.group(1).strip()
        target = " ".join(m.group(2).split())
        tail = block[m.end():m.end() + 120]
        cm = _CONF.search(tail)
        out.append((etype, target, cm.group(1).strip() if cm else "medium"))
    return out


def yaml_block_scalar(value: str, indent: str = "    ") -> str:
    """Render a long claim sentence safely. Claim sentences contain colons and
    quotes often enough that quoting is fragile; a folded block scalar is not."""
    if len(value) <= 90 and not any(c in value for c in ":#\"'{}[]|>&*!%@`\n"):
        return value
    wrapped, line = [], indent
    for word in value.split():
        if len(line) + len(word) + 1 > 78 and line.strip():
            wrapped.append(line.rstrip())
            line = indent + word
        else:
            line = (line + " " + word) if line.strip() else indent + word
    wrapped.append(line.rstrip())
    return ">-\n" + "\n".join(wrapped)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", default=str(Path.home() / "engram-work"))
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--sample", type=int, default=0,
                    help="print N before/after examples and stop")
    ap.add_argument("--sources-section", action="store_true",
                    help="also append a ## Sources body section of wikilinks to the "
                         "archived originals. OFF by default: the publisher intends "
                         "to delete the archive once the good notes exist, and those "
                         "links would then be 111,133 dead wikilinks. The provenance "
                         "is already in the frontmatter either way — absorbed_from "
                         "names the originals and sources: names the conversations "
                         "(present on 100%% of merged notes) — so the body section "
                         "adds nothing that is not already recorded.")
    args = ap.parse_args()

    vault = Path(args.vault)
    engrams = vault / "Engrams"
    archive = vault / ARCHIVE_SUBDIR
    if not engrams.is_dir() or not archive.is_dir():
        print(f"[fix] missing {engrams} or {archive}", file=sys.stderr)
        return 2

    # ---- index the archive: filename -> (H1, edges) ----------------------
    print("[fix] indexing archived originals...", flush=True)
    arch_h1: dict[str, str] = {}
    arch_edges: dict[str, list[tuple[str, str, str]]] = {}
    for p in archive.glob("*.md"):
        t = p.read_text(encoding="utf-8", errors="replace")
        h = h1_of(t)
        if h:
            arch_h1[p.name] = h
        e = edges_from(t)
        if e:
            arch_edges[p.name] = e
    print(f"[fix]   {len(arch_h1):,} originals, {len(arch_edges):,} with edges")

    # ---- build the remap from the merged notes ---------------------------
    print("[fix] building old-H1 -> new-H1 remap...", flush=True)
    merged: list[tuple[Path, str, str, list[str]]] = []
    remap: dict[str, str] = {}
    for p in engrams.glob("*.md"):
        t = p.read_text(encoding="utf-8", errors="replace")
        if "migration: permanent-note" not in t:
            continue
        nh = h1_of(t)
        if not nh:
            continue
        srcs = absorbed_of(t)
        merged.append((p, t, nh, srcs))
        for fn in srcs:
            oh = arch_h1.get(fn)
            if oh:
                remap[oh] = nh
    print(f"[fix]   {len(merged):,} merged notes, {len(remap):,} remap pairs")

    stats = collections.Counter()
    samples = []

    for p, text, new_h1, srcs in merged:
        front, body = split_note(text)
        if not front:
            stats["no_frontmatter"] += 1
            continue

        before = text
        body2, removed = strip_instance(body)
        if removed:
            stats["instance_removed"] += 1

        # PASS 2 — sources section from absorbed_from
        body2 = re.sub(r"\n##\s+Sources\b.*$", "", body2, flags=re.S).rstrip()
        if srcs and args.sources_section:
            lines = ["", "## Sources", ""]
            for fn in srcs:
                lines.append(f"- [[{fn[:-3] if fn.endswith('.md') else fn}]]")
            body2 = body2 + "\n" + "\n".join(lines)
            stats["sources_added"] += 1
        body2 = body2.rstrip() + "\n"

        # PASS 3 — remapped relationships, deduped on (type, target)
        seen: set[tuple[str, str]] = set()
        rel: list[tuple[str, str, str]] = []
        dropped = 0
        for fn in srcs:
            for etype, target, conf in arch_edges.get(fn, []):
                nt = remap.get(target)
                if not nt:
                    dropped += 1
                    continue
                if nt == new_h1:            # edge to the note's own new self
                    continue
                key = (etype, nt)
                if key in seen:
                    continue
                seen.add(key)
                rel.append((etype, nt, conf))
        stats["edges_kept"] += len(rel)
        stats["edges_dropped"] += dropped
        if rel:
            stats["notes_with_edges"] += 1

        front2 = re.sub(r"\nrelationships:\s*\n(?:[ \t]+.*\n|[ \t]*-.*\n)+", "\n", front)
        front2 = front2.rstrip("\n")
        if rel:
            rl = ["relationships:"]
            for etype, target, conf in rel:
                rl.append(f"- type: {etype}")
                rl.append(f"  target: {yaml_block_scalar(target, '    ')}")
                rl.append(f"  confidence: {conf}")
            front2 = front2 + "\n" + "\n".join(rl)

        out = "---" + front2 + "\n---" + body2 if front2.startswith("\n") \
            else "---\n" + front2 + "\n---" + body2

        if args.sample and len(samples) < args.sample and (removed and rel):
            samples.append((p.name, before, out))

        if args.apply:
            tmp = p.with_suffix(".tmp")
            tmp.write_text(out, encoding="utf-8")
            tmp.replace(p)
            stats["written"] += 1

    if samples:
        for name, before, after in samples:
            print("\n" + "=" * 78)
            print(f"FILE: {name}")
            print("-" * 34 + " BEFORE " + "-" * 34)
            print(before.strip()[:1500])
            print("-" * 35 + " AFTER " + "-" * 35)
            print(after.strip()[:1800])
        return 0

    print("\n[fix] " + ("APPLIED" if args.apply else "DRY RUN — nothing written"))
    for k in ("instance_removed", "sources_added", "notes_with_edges",
              "edges_kept", "edges_dropped", "written", "no_frontmatter"):
        if stats[k]:
            print(f"[fix]   {k:20s} {stats[k]:>9,}")
    if not args.apply:
        print("[fix] re-run with --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
