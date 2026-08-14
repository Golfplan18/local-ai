#!/usr/bin/env python3
"""Completion gate over the rewrite outputs. No model calls.

ONE-TIME MIGRATION TOOL. Delete with the rest of scripts/engram-migration/.

The review that examined this pipeline (finding E7) noted the runner treats any
existing output file as complete, validates little past ID and title, increments
`ok` even where a result was rejected, and exits zero with failures outstanding.
This is the gate that has to pass before anything is written into a note.

It proves a bijection — every worklist entry has exactly one output and every
output maps to a worklist entry — and then validates each record field by field.
Known defects it was written to catch, both observed in real output:

  * `body` arriving as a JSON array instead of a string. Two of the first 3,148
    outputs had this. Applying it verbatim would write "['- a', '- b']" into a
    note.
  * `body` carrying the model's own commentary after the bullets, which would be
    published as if it were part of the note.

Nothing here is repaired automatically. Repair is a decision: an invalid record
should be re-run, and re-running is free. The gate's job is to make the invalid
set exact and visible.

Exit code is non-zero if any record fails, so this can gate a script.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

VALID_VERDICTS = {"KEEP", "SPLIT", "ARCHIVE"}

# A body line that is really the model talking about its own work. Only
# unambiguous markers: an earlier version included the bare participles
# "Preserved|Dropped|Kept", which flagged two perfectly good bullets —
# "Kept on defense, the challenger argues only within terms its opponent
# defines" and "Dropped into the charged silence after an emotional outburst, a
# parable stops functioning as instruction". Those are ordinary sentence openers.
# Proxying a judgement question with a string match has over-fired five times in
# this project; the fix each time is to narrow the pattern to things that cannot
# be legitimate prose.
_COMMENTARY = re.compile(
    r"^\s*-?\s*(I |I've |I have |Note to |Note:|As requested|Here is the|Here's the|"
    r"This note |The above |The note above|My rewrite|In this rewrite)", re.I)

# The real leak risk: the prompt asks for the note, then a `---` line, then two or
# three sentences of self-report. If that separator or the text after it lands in
# the body, the self-report gets published as if it were the note.
_SELF_REPORT = re.compile(
    r"^\s*-{3,}\s*$|\b(a careless summary|what I preserved|I judged|"
    r"the sources assert|unsupported in the sources)\b", re.I | re.M)


def check(rec: dict, note_id: str) -> list[str]:
    bad: list[str] = []
    v = rec.get("verdict")
    if v not in VALID_VERDICTS:
        bad.append(f"verdict={v!r}")

    if rec.get("note_id") != note_id:
        bad.append(f"note_id mismatch ({rec.get('note_id')!r})")

    title = rec.get("title")
    if not isinstance(title, str) or not title.strip():
        bad.append("title missing or not a string")
    else:
        if "\n" in title:
            bad.append("title contains a newline")
        if re.search(r"[*_`]", title):
            bad.append("markdown in title")

    if v == "ARCHIVE":
        pass  # body not required
    else:
        body = rec.get("body")
        if isinstance(body, list):
            bad.append("body is an ARRAY, not a string")
        elif not isinstance(body, str) or not body.strip():
            bad.append("body missing or not a string")
        else:
            lines = [l for l in body.splitlines() if l.strip()]
            if not lines:
                bad.append("body has no lines")
            if not any(l.strip().startswith("-") for l in lines):
                bad.append("body has no bullet lines")
            for l in lines:
                if _COMMENTARY.match(l):
                    bad.append(f"body carries commentary: {l.strip()[:60]!r}")
                    break
            m = _SELF_REPORT.search(body)
            if m:
                bad.append(f"body carries the self-report block: {m.group(0)[:40]!r}")

    if v == "SPLIT":
        sec = rec.get("split_second_note")
        if not isinstance(sec, dict):
            bad.append("SPLIT without split_second_note")
        else:
            if not isinstance(sec.get("title"), str) or not sec["title"].strip():
                bad.append("SPLIT second note missing title")
            sb = sec.get("body")
            if isinstance(sb, list):
                bad.append("SPLIT second body is an ARRAY")
            elif not isinstance(sb, str) or not sb.strip():
                bad.append("SPLIT second note missing body")

    srcs = rec.get("source_files")
    if not isinstance(srcs, list) or not srcs:
        bad.append("source_files missing or empty")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", default=str(Path.home() / "engram-work"))
    ap.add_argument("--worklist", default=None)
    ap.add_argument("--examples", type=int, default=3)
    args = ap.parse_args()

    vault = Path(args.vault)
    outdir = vault / ".migration" / "rewrite"
    wl_path = Path(args.worklist) if args.worklist else vault / ".migration" / "opus_worklist.json"
    engrams = vault / "Engrams"

    worklist = [Path(x).stem for x in json.loads(wl_path.read_text())]
    expected = set(worklist)
    outputs = {p.stem: p for p in outdir.glob("*.json")}

    print(f"[validate] worklist entries : {len(worklist):,} ({len(expected):,} distinct)")
    print(f"[validate] output files     : {len(outputs):,}")

    missing = expected - set(outputs)
    extra = set(outputs) - expected
    print(f"[validate] missing outputs  : {len(missing):,}")
    print(f"[validate] outputs not on the worklist: {len(extra):,}")
    for m in sorted(missing)[:args.examples]:
        print(f"[validate]     missing: {m[:70]}")
    for m in sorted(extra)[:args.examples]:
        print(f"[validate]     extra:   {m[:70]}")

    stats = collections.Counter()
    problems: dict[str, list[str]] = {}
    verdicts = collections.Counter()
    for stem, p in outputs.items():
        try:
            rec = json.loads(p.read_text())
        except Exception as e:
            problems[stem] = [f"unparseable JSON: {e}"]
            stats["unparseable"] += 1
            continue
        if isinstance(rec, list):
            rec = rec[0] if rec else {}
        verdicts[rec.get("verdict")] += 1
        bad = check(rec, stem)
        if bad:
            problems[stem] = bad
            for b in bad:
                stats[b.split("(")[0].split(":")[0].strip()] += 1
        # does the target note still exist?
        if not (engrams / (stem + ".md")).exists():
            problems.setdefault(stem, []).append("target note no longer in Engrams/")
            stats["target missing"] += 1

    print(f"\n[validate] verdicts: {dict(verdicts)}")
    print(f"[validate] records with a problem: {len(problems):,} of {len(outputs):,}")
    if stats:
        print("[validate] problem counts:")
        for k, v in stats.most_common():
            print(f"[validate]     {v:>6,}  {k}")
    shown = 0
    for stem, bad in problems.items():
        if shown >= args.examples:
            break
        print(f"\n[validate]   {stem[:66]}")
        for b in bad:
            print(f"[validate]       {b[:110]}")
        shown += 1

    out = vault / ".migration" / "validation.json"
    out.write_text(json.dumps(
        {"missing": sorted(missing), "extra": sorted(extra), "problems": problems},
        indent=1, ensure_ascii=False), encoding="utf-8")

    clean = not missing and not extra and not problems
    print(f"\n[validate] {'PASS — bijection exact, every record valid' if clean else 'FAIL'}")
    print(f"[validate] detail -> {out}")
    if not clean:
        print("[validate] re-run rewrite_run.py after deleting the invalid outputs; "
              "a missing output re-enters the worklist automatically")
    return 0 if clean else 1


if __name__ == "__main__":
    sys.exit(main())
