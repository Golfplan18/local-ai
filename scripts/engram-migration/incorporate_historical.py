#!/usr/bin/env python3
"""Fold Engrams/Historical Atomics/ into the single corpus, archiving what does not belong.

ONE-TIME MIGRATION TOOL. Delete with the rest of scripts/engram-migration/.

WHY THIS FOLDER EXISTS AT ALL
-----------------------------
`phase5_atomic_extraction.py` hardcodes its output to
`Engrams/Historical Atomics/[YYYY]/` — it is the historical backfill pipeline,
separate by design from the live path (`extraction_engine.py`) that produced the
top-level corpus. Every migration script globbed `Engrams/*.md` non-recursively,
so all 14,049 notes were invisible to the entire migration.

They are NOT duplicates of the main corpus, which surprised me. Measured two ways:
of 2,265 distinct (conversation, turn) citations in this folder only 22 also appear
in the absorbed archive — 1.0%. And the date ranges are complementary rather than
overlapping: the main corpus stops at the end of April 2026 (8 notes in May, then
nothing) while 90% of this folder is May, June and July 2026. It is the
continuation, not a copy.

It is also markedly better behaved: 21 notes per conversation against the main
corpus's 59, and 185 near-duplicate title pairs in 14,049 notes. The over-extraction
that motivated the whole migration is largely absent here.

WHAT GETS ARCHIVED RATHER THAN INCORPORATED
-------------------------------------------
  FACT      notes the extraction models tagged `fact`. The publisher's decision:
            "I don't need bare facts." These are things like a polling margin or a
            configuration default — true, sometimes useful, not knowledge-corpus
            material.
  PERISHABLE named political actors and events whose claims expire and carry no
            transferable structure.
  DATED     a year in the title, which pins the claim to a moment.

Everything else moves to the top-level corpus unchanged. Nothing is deleted; the
archived notes go to a dated folder alongside the absorbed sources.

A note tagged `fact` that ALSO looks perishable is archived once, with both reasons
recorded in the manifest.

Dry run by default. --apply moves files.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import shutil
import sys
from pathlib import Path

ARCHIVE_NAME = "Historical Atomics Not Incorporated 2026-08"

_H1 = re.compile(r"^#\s+(.+)$", re.M)
_YEAR = re.compile(r"\b(19|20)\d\d\b")
_PERISH = re.compile(
    r"\b(Trump|Biden|Harris|Vance|Paxton|Cornyn|Hegseth|Musk|Netanyahu|Putin|Zelensky|"
    r"midterm|runoff|primary election|polling|poll numbers|indictment|impeach|pardon|"
    r"tariff rate|CHIPS Act|filibuster|Electoral College|"
    r"House Democrats|House Republicans|Senate Democrats|Senate Republicans)\b")
# The publisher's own forecasts. Reported, never archived — a dated falsifiable
# prediction is a different artifact from a knowledge note and is worth keeping
# findable.
_PRED = re.compile(r"\b(the user|the publisher)\b.{0,40}"
                   r"\b(predicts?|expects?|forecasts?|anticipates?|believes? that)\b", re.I)


def body_of(text: str) -> str:
    parts = text.split("---", 2)
    return (parts[2] if len(parts) > 2 else text).strip()


def title_of(text: str) -> str:
    m = _H1.search(body_of(text))
    return m.group(1).strip() if m else ""


def tags_of(text: str) -> set[str]:
    head = text.split("---", 2)[1] if text.startswith("---") and text.count("---") >= 2 else ""
    return {t for t in re.findall(r"^\s+-\s+([\w-]+)\s*$", head, re.M)}


def classify(text: str) -> tuple[str, list[str]]:
    """Return (destination, reasons). destination is 'corpus' or 'archive'."""
    title = title_of(text)
    tags = tags_of(text)
    reasons: list[str] = []
    if "fact" in tags:
        reasons.append("bare-fact")
    if _PERISH.search(title):
        reasons.append("perishable")
    if _YEAR.search(title):
        reasons.append("dated-title")
    return ("archive" if reasons else "corpus"), reasons


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", default=str(Path.home() / "engram-work"))
    ap.add_argument("--apply", action="store_true", help="move files (default: dry run)")
    args = ap.parse_args()

    vault = Path(args.vault)
    engrams = vault / "Engrams"
    ha = engrams / "Historical Atomics"
    archive = vault / "Archive" / ARCHIVE_NAME
    if not ha.is_dir():
        print(f"[incorporate] {ha} not found — already done?", file=sys.stderr)
        return 2

    notes = sorted(ha.rglob("*.md"))
    print(f"[incorporate] Historical Atomics: {len(notes):,} notes")

    stats = collections.Counter()
    manifest: list[dict] = []
    preds: list[str] = []
    collisions: list[str] = []
    existing = {p.name for p in engrams.glob("*.md")}

    for p in notes:
        text = p.read_text(encoding="utf-8", errors="replace")
        dest_kind, reasons = classify(text)
        title = title_of(text)
        if _PRED.search(title):
            preds.append(f"{p.name} :: {title}")
        stats[dest_kind] += 1
        for r in reasons:
            stats[f"reason:{r}"] += 1
        target_dir = archive if dest_kind == "archive" else engrams
        if dest_kind == "corpus" and p.name in existing:
            # A filename clash would silently overwrite a main-corpus note.
            collisions.append(p.name)
            stats["collision"] += 1
            continue
        manifest.append({"from": str(p.relative_to(vault)), "to": dest_kind,
                         "reasons": reasons, "title": title})
        if args.apply:
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(target_dir / p.name))

    print(f"[incorporate]   -> corpus  : {stats['corpus']:,}")
    print(f"[incorporate]   -> archive : {stats['archive']:,}")
    for r in ("bare-fact", "perishable", "dated-title"):
        if stats[f"reason:{r}"]:
            print(f"[incorporate]        {r:14s} {stats[f'reason:{r}']:,}")
    if collisions:
        print(f"[incorporate]   !! FILENAME COLLISIONS (skipped, not moved): {len(collisions)}")
        for c in collisions[:5]:
            print(f"[incorporate]        {c}")
    print(f"[incorporate]   publisher's own predictions (kept in corpus): {len(preds)}")
    for s in preds[:12]:
        print(f"[incorporate]        {s[:118]}")

    out = vault / ".migration" / "incorporate-manifest.json"
    if args.apply:
        out.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
        # Remove the now-empty year directories.
        for d in sorted(ha.rglob("*"), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        if ha.is_dir() and not any(ha.iterdir()):
            ha.rmdir()
            print(f"[incorporate] removed empty {ha.name}/")
        print(f"[incorporate] APPLIED. manifest -> {out}")
    else:
        print(f"[incorporate] DRY RUN — nothing moved. --apply to execute")
    return 0


if __name__ == "__main__":
    sys.exit(main())
