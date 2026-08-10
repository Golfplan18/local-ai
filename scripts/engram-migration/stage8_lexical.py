#!/usr/bin/env python3
"""Stage 8 — cross-domain merge candidates from generalized titles.

ONE-TIME MIGRATION TOOL. Delete with the rest of scripts/engram-migration/.

Stage 2 clustered on embeddings of the ORIGINAL notes and deliberately missed a
whole class of duplicate. Measured on 2,337 Opus-generalized notes: of the pairs
whose generalized titles state the same principle, 70.4% had original embedding
similarity below 0.75 and the median sat at 0.653. Two examples:

    "Compassion requires greater strength than emotional detachment..."
    "True healing presence transfers love into another person's system..."
      -> both generalize to: staying present to another's suffering
      -> original similarity 0.489

    "Expanding terse dialogue into sensory description..."
    "Precise environmental details convey emotional states..."
      -> both generalize to: physical detail transmits an inner state
      -> original similarity 0.504

Embeddings cannot see through the subject-matter costume. Generalization removes
the costume, which is why this pass runs AFTER Stage 5 and not before. It needs
no embedder and no API.

What generalization actually makes uniform is the note's CONCEPT NAME, not its
wording -- see signal 2 below, where that assumption was tested and failed.

Two signals, deliberately ordered:

  1. SHARED STANDARD CONCEPT — two notes Stage 5 independently labelled with the
     same canonical term (both "moral hazard", both "operant extinction") are the
     same concept by the writer's own judgement, reached without either note
     seeing the other. This is the highest-precision signal available and it
     costs nothing to compute.

  2. TITLE OVERLAP — Jaccard over content words. Catches pairs where no canonical
     term exists. MEASURED WEAK: on 2,337 real generalized notes this found 1
     pair against the concept signal's 985. Generalization does not make titles
     lexically uniform -- two notes can both be about costly signaling and share
     almost no words. It makes their CONCEPT nameable, which is why signal 1
     carries this stage and why Stage 5's duty to name the concept matters more
     than a metadata field would suggest.

Output is CANDIDATES, never merges. Stage 2's calibration found that every
sampled cluster carried a real distinction under adversarial review, so a model
decides each merge at Stage 9. Nothing here deletes anything.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

# PROVISIONAL, pending calibration on real Stage 5 output. At 0.34 this signal
# found 1 pair in 2,337 generalized notes while the shared-concept signal found
# 985, so lexical overlap is near-useless at that setting. An earlier scan at
# 0.22 surfaced 27 genuine cross-domain pairs, so the useful band is lower than
# it looks. Retune once Stage 5 has run at scale; do not treat as settled.
DEFAULT_JACCARD = 0.25

STOP = set("""a an the of to in and or that is are for by with as on it this be can when
not from their there they which who what into than more most rather only its each every
those these such over under between within without through across against about""".split())


def content_words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", (s or "").lower())
            if w not in STOP and len(w) > 3}


def norm_concept(s: str) -> str:
    s = re.sub(r"\(.*?\)", "", s or "").strip().lower()
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--migration", default=str(Path.home() / "engram-work" / ".migration"))
    ap.add_argument("--jaccard", type=float, default=DEFAULT_JACCARD,
                    help="title content-word overlap to nominate a pair")
    ap.add_argument("--max-group", type=int, default=10,
                    help="split candidate groups larger than this")
    args = ap.parse_args()
    M = Path(args.migration)

    notes: dict[str, dict] = {}
    for p in sorted((M / "stage5").glob("result_*.json")):
        try:
            recs = json.loads(p.read_text())
        except Exception:
            continue
        for r in (recs if isinstance(recs, list) else recs.get("results", [])):
            if r.get("verdict") == "KEEP" and r.get("new_title"):
                notes[r["unit_id"]] = r
    if not notes:
        print("[stage8] no Stage 5 KEEP notes yet — run Stage 5 first", file=sys.stderr)
        return 0
    ids = list(notes)
    print(f"[stage8] generalized notes: {len(ids):,}")

    pairs: dict[tuple[str, str], str] = {}

    # Signal 1 — shared canonical concept name
    by_concept: dict[str, list[str]] = collections.defaultdict(list)
    for uid in ids:
        c = norm_concept(notes[uid].get("standard_concept", ""))
        if c:
            by_concept[c].append(uid)
    shared = {c: v for c, v in by_concept.items() if len(v) > 1}
    for c, group in shared.items():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                pairs[(group[i], group[j])] = f"concept:{c}"
    print(f"[stage8] notes carrying a canonical concept: "
          f"{sum(1 for u in ids if norm_concept(notes[u].get('standard_concept','')))} ; "
          f"concepts shared by >1 note: {len(shared):,} covering "
          f"{sum(len(v) for v in shared.values()):,} notes")

    # Signal 2 — title content-word overlap, blocked by shared rare word so this
    # stays linear-ish instead of quadratic over the whole corpus.
    toks = {uid: content_words(notes[uid]["new_title"]) for uid in ids}
    inverted: dict[str, list[str]] = collections.defaultdict(list)
    for uid, ws in toks.items():
        for w in ws:
            inverted[w].append(uid)
    df = {w: len(v) for w, v in inverted.items()}
    checked = set()
    for w, bucket in inverted.items():
        if df[w] > 400 or len(bucket) < 2:      # skip words too common to block on
            continue
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                a, b = bucket[i], bucket[j]
                key = (a, b) if a < b else (b, a)
                if key in checked or key in pairs:
                    continue
                checked.add(key)
                u = toks[a] | toks[b]
                if u and len(toks[a] & toks[b]) / len(u) >= args.jaccard:
                    pairs[key] = "title-overlap"
    print(f"[stage8] candidate pairs: {len(pairs):,} "
          f"({sum(1 for v in pairs.values() if v.startswith('concept:')):,} by shared concept, "
          f"{sum(1 for v in pairs.values() if v == 'title-overlap'):,} by title overlap)")

    # Group pairs into candidate sets (leader-style, non-transitive: a runaway
    # transitive component here would hand Stage 9 an unreviewable blob, the same
    # failure connected-components produced at Stage 2).
    adj: dict[str, list[str]] = collections.defaultdict(list)
    for (a, b) in pairs:
        adj[a].append(b)
        adj[b].append(a)
    assigned: set[str] = set()
    groups: list[list[str]] = []
    for lead in sorted(adj, key=lambda i: -len(adj[i])):
        if lead in assigned:
            continue
        g = [lead]
        assigned.add(lead)
        for nb in adj[lead]:
            if nb not in assigned:
                assigned.add(nb)
                g.append(nb)
        if len(g) > 1:
            for s in range(0, len(g), args.max_group):
                groups.append(g[s:s + args.max_group])

    out = []
    for k, g in enumerate(groups):
        out.append({
            "group_id": f"g{k:06d}",
            "reason": pairs.get((g[0], g[1]) if g[0] < g[1] else (g[1], g[0]), "mixed"),
            "members": [{"unit_id": u,
                         "title": notes[u]["new_title"],
                         "standard_concept": notes[u].get("standard_concept", ""),
                         "body": notes[u].get("new_body", "")} for u in g],
        })
    (M / "stage8_groups.json").write_text(json.dumps(out, indent=1))
    covered = sum(len(g["members"]) for g in out)
    print(f"[stage8] candidate groups: {len(out):,} covering {covered:,} notes "
          f"({covered/max(1,len(ids))*100:.1f}%)")
    print(f"[stage8] if every group merged to one note: "
          f"{len(ids) - covered + len(out):,} notes (upper bound on reduction)")
    print(f"[stage8] wrote {M/'stage8_groups.json'} — CANDIDATES ONLY, "
          f"Stage 9 decides each merge")
    return 0


if __name__ == "__main__":
    sys.exit(main())
