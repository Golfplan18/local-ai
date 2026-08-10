#!/usr/bin/env python3
"""Stage 8b — audit the standard_concept field before it is trusted.

ONE-TIME MIGRATION TOOL. Delete with the rest of scripts/engram-migration/.

WHY THIS EXISTS. standard_concept was specified as a retrieval aid -- the
canonical term a reader would search for. Stage 8 then found it carries almost
the entire cross-domain merge signal: on 2,337 real generalized notes, 985
candidate pairs came from a shared concept name and 1 from title overlap. A field
designed as metadata turned out to be the mechanism, so its quality now decides
which notes get merged (Stage 9) and, through them, what the rebuilt relationship
graph asserts (Stage 10).

Four failure modes, three observed during the trials:

  INVENTED    a canonical-sounding term that is not a real term. Haiku produced
              "Bad faith reasoning" and "Commitment failure"; a fake term is
              worse than none, because it pollutes the vocabulary and misleads
              every later search.
  MISATTRIBUTED  a real term applied to the wrong claim. The A/B caught
              "Confirmation bias" on a note actually about social engineering.
  DRIFT       the same concept spelled differently -- "moral hazard" vs "the
              moral hazard problem" -- so real merges are missed silently.
  OVER-BROAD  a term so general it collects unrelated notes. A concept on 500
              notes yields a 500-note false-merge group.

This script handles what is mechanically decidable: the frequency distribution
(both tails are suspicious), and DRIFT via near-duplicate concept strings. It
emits a review set for the two failure modes that need judgement (INVENTED,
MISATTRIBUTED) -- one batched model pass over DISTINCT CONCEPT NAMES, which is
orders of magnitude cheaper than auditing notes.

Run between Stage 8 and Stage 9. Nothing here modifies notes.
"""
from __future__ import annotations

import argparse
import collections
import difflib
import json
import re
import sys
from pathlib import Path

# PROVISIONAL, pending a look at the real distribution. Both tails are suspect
# rather than wrong: a singleton concept is often correct and specific, and a
# frequent one is often a genuinely common idea. These only route to review.
SINGLETON_IS_SUSPECT = 1
OVER_BROAD_MIN = 150
DRIFT_RATIO = 0.86


def _stem(w: str) -> str:
    """Light suffix fold so 'costly signal'/'costly signaling' and
    'barrier'/'barriers' land on the same key. Deliberately shallow —
    over-stemming would collapse genuinely different concepts.

    The plural rules follow English rather than raw string suffixes. Stripping a
    trailing "es" unconditionally turned "preferences" into "preferenc", which
    never matched "preference"; -es is only dropped after s/x/z/ch/sh.
    """
    if len(w) <= 4:
        return w
    if w.endswith("ies"):
        return w[:-3] + "y"
    if w.endswith("ing"):
        return w[:-3]
    if w.endswith(("ses", "xes", "zes", "ches", "shes")):
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def norm(s: str) -> str:
    s = re.sub(r"\(.*?\)", "", s or "").strip().lower()
    s = re.sub(r"^(the|a|an)\s+", "", s)
    # Punctuation becomes a SPACE, not nothing. Deleting it turned
    # "divide-and-conquer" into "divideandconquer" and "common-enemy effect"
    # into "commonenemy effect", manufacturing drift pairs that were really one
    # concept written two ways.
    s = re.sub(r"[^a-z0-9]+", " ", s)
    # Stem EVERY word, not just the last: the plural often sits on the head noun
    # ("barriers to entry" vs "barrier to entry"), which last-word-only missed.
    words = [_stem(w) for w in s.split() if w]
    return " ".join(words).strip()


def load_notes(M: Path) -> list[dict]:
    out = []
    for sub in ("stage5", "stage9"):
        for p in sorted((M / sub).glob("result_*.json")):
            try:
                recs = json.loads(p.read_text())
            except Exception:
                continue
            for r in (recs if isinstance(recs, list) else recs.get("results", [])):
                if r.get("new_title"):
                    out.append(r)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--migration", default=str(Path.home() / "engram-work" / ".migration"))
    ap.add_argument("--over-broad", type=int, default=OVER_BROAD_MIN)
    args = ap.parse_args()
    M = Path(args.migration)

    notes = load_notes(M)
    if not notes:
        print("[stage8b] no Stage 5/9 output yet", file=sys.stderr)
        return 0

    raw = collections.Counter()
    canon = collections.Counter()
    examples: dict[str, list[str]] = collections.defaultdict(list)
    for r in notes:
        c = (r.get("standard_concept") or "").strip()
        if not c:
            continue
        raw[c] += 1
        n = norm(c)
        canon[n] += 1
        if len(examples[n]) < 3:
            examples[n].append(r["new_title"])

    named = sum(raw.values())
    print(f"[stage8b] notes: {len(notes):,}   carrying a concept: {named:,} "
          f"({named/len(notes)*100:.1f}%)")
    print(f"[stage8b] distinct concept strings: {len(raw):,}   after normalisation: "
          f"{len(canon):,}   collapsed by normalisation: {len(raw)-len(canon):,}")

    # DRIFT — near-duplicate canonical strings that normalisation did not catch
    keys = sorted(canon)
    drift: list[tuple[str, str, float]] = []
    by_first = collections.defaultdict(list)
    for k in keys:
        by_first[k.split()[0][:4] if k.split() else k[:4]].append(k)
    for bucket in by_first.values():
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                a, b = bucket[i], bucket[j]
                r = difflib.SequenceMatcher(None, a, b).ratio()
                if r >= DRIFT_RATIO:
                    drift.append((a, b, round(r, 3)))
    print(f"[stage8b] DRIFT — near-duplicate concept names: {len(drift):,}")
    for a, b, r in drift[:8]:
        print(f"     {r}  '{a}' ~ '{b}'  ({canon[a]} + {canon[b]} notes)")

    # OVER-BROAD
    over = [(c, n) for c, n in canon.most_common() if n >= args.over_broad]
    print(f"[stage8b] OVER-BROAD — concepts on >= {args.over_broad} notes: {len(over):,}")
    for c, n in over[:10]:
        print(f"     {n:6,}  {c}")

    # tails
    singles = [c for c, n in canon.items() if n == SINGLETON_IS_SUSPECT]
    print(f"[stage8b] single-use concepts (review for INVENTED): {len(singles):,} "
          f"= {len(singles)/max(1,len(canon))*100:.1f}% of distinct concepts")
    print(f"[stage8b] frequency: median={sorted(canon.values())[len(canon)//2]}  "
          f"p90={sorted(canon.values())[int(.9*len(canon))]}  max={max(canon.values())}")

    review = {
        "drift": [{"a": a, "b": b, "ratio": r, "a_count": canon[a], "b_count": canon[b]}
                  for a, b, r in drift],
        "over_broad": [{"concept": c, "count": n, "examples": examples[c]} for c, n in over],
        "verify": [{"concept": c, "count": canon[c], "examples": examples[c]}
                   for c in sorted(canon, key=lambda x: canon[x])],
    }
    (M / "concept_audit.json").write_text(json.dumps(review, indent=1))
    print(f"[stage8b] wrote {M/'concept_audit.json'}")
    print(f"[stage8b] the 'verify' list holds {len(canon):,} DISTINCT concept names for one "
          f"batched model pass — INVENTED and MISATTRIBUTED need judgement, and "
          f"auditing {len(canon):,} names is far cheaper than auditing {named:,} notes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
