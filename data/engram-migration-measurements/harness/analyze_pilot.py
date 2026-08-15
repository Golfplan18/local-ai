"""Measure the 40-note pilot: Option B's exit rate and what actually changed.

The standing-condition sentinel is matched on a dash-normalized, case-folded
prefix. Models are inconsistent about em vs en dash vs hyphen, and an exact
string comparison would silently under-report the very rate this pilot exists
to measure.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import unicodedata

OUT = pathlib.Path(os.path.expanduser("~/engram-work/.migration/pilot40"))
ENG = pathlib.Path(os.path.expanduser("~/engram-work/Engrams"))

SENTINEL = "none standing condition"
H1 = re.compile(r"^#\s+(.+)$", re.M)


def norm(s: str) -> str:
    """Fold dashes to spaces and collapse whitespace, then lowercase."""
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"[‐-―\-:]+", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def current_title(stem: str) -> str:
    p = ENG / f"{stem}.md"
    if not p.exists():
        return ""
    m = H1.search(p.read_text(encoding="utf-8", errors="replace"))
    return m.group(1).strip() if m else ""


def main() -> None:
    files = sorted(OUT.glob("*.json"))
    if not files:
        print("no pilot output yet")
        return

    recs = []
    for f in files:
        try:
            recs.append(json.loads(f.read_text()))
        except Exception as e:
            print(f"UNPARSEABLE {f.name}: {e}")

    verdicts: dict[str, int] = {}
    standing = []
    conversions = []
    domain_bound = 0
    splits = 0
    title_words = []
    changed = 0

    for r in recs:
        v = r.get("verdict", "?")
        verdicts[v] = verdicts.get(v, 0) + 1
        conv = r.get("conversion", "")
        if norm(conv).startswith(SENTINEL):
            standing.append((r["note_id"], r.get("title", ""), conv))
        else:
            conversions.append((r["note_id"], r.get("title", ""), conv))
        if r.get("domain_bound"):
            domain_bound += 1
        if r.get("split_second_note"):
            splits += 1
        title_words.append(len((r.get("title") or "").split()))
        if norm(r.get("title", "")) != norm(current_title(r["note_id"])):
            changed += 1

    n = len(recs)
    print(f"notes returned            : {n} / 40")
    print(f"verdicts                  : {verdicts}")
    print(f"title changed from current: {changed}/{n}  ({changed/n:.0%})")
    print(f"domain_bound true         : {domain_bound}/{n}")
    print(f"carries split_second_note : {splits}/{n}")
    if title_words:
        title_words.sort()
        print(f"title words  min/med/max  : {title_words[0]} / "
              f"{title_words[len(title_words)//2]} / {title_words[-1]}")
    print()
    print(f"STANDING CONDITION (no conversion) : {len(standing)}/{n}  "
          f"({len(standing)/n:.0%})     <- predicted ~33%")
    print(f"CONVERSION found                   : {len(conversions)}/{n}  "
          f"({len(conversions)/n:.0%})")
    print()
    print("=" * 78)
    print("STANDING-CONDITION NOTES — does each name a cost or a beneficiary?")
    print("=" * 78)
    for nid, title, conv in standing:
        print(f"\n  TITLE : {title}")
        print(f"  FIELD : {conv}")
    print()
    print("=" * 78)
    print("CONVERSION NOTES — sample")
    print("=" * 78)
    for nid, title, conv in conversions[:8]:
        print(f"\n  TITLE : {title}")
        print(f"  CONV  : {conv}")


if __name__ == "__main__":
    main()
