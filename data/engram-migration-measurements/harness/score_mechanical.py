"""Score prescan's mechanical detectors against the 80-case judging benchmark.

D2/D3/D4 were built to find MIGRATION damage in the old merged notes. This asks
a different question: do they find defects in an M3 REWRITE? Same shape (note vs
its archived sources), new population, so it has to be measured, not assumed.

D5 is not from prescan. It is the generic fabrication check PLAN.md section 6
describes — note vocabulary that appears nowhere in the source's whole
vocabulary — because fabrication is the largest single defect class in the
labelled set and D2 only catches a fixed list of named terms of art.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib

MIG = pathlib.Path(os.path.expanduser("~/engram-work/.migration"))
PRESCAN = os.path.expanduser("~/ora/scripts/engram-migration/prescan.py")

spec = importlib.util.spec_from_file_location("prescan", PRESCAN)
ps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ps)


def d5_novel_vocabulary(title: str, body: str, source_blob: str,
                        threshold: int) -> list[str]:
    """Content words in the note that appear nowhere in the sources.

    Compared against the source's WHOLE vocabulary, lowercased — the fix that
    stopped the earlier version producing 31 false HARD failures by reading
    "Cultural Accessibility" as invented when the source said "cultural
    accessibility".
    """
    src = ps.content_words(source_blob)
    note = ps.content_words(f"{title}\n{body}")
    novel = sorted(note - src)
    return novel if len(novel) >= threshold else []


def score(name: str, flags: dict[str, bool], labels: dict[str, str]) -> dict:
    tp = sum(1 for c, l in labels.items() if l == "DEFECT" and flags.get(c))
    fn = sum(1 for c, l in labels.items() if l == "DEFECT" and not flags.get(c))
    fp = sum(1 for c, l in labels.items() if l == "SOUND" and flags.get(c))
    tn = sum(1 for c, l in labels.items() if l == "SOUND" and not flags.get(c))
    rec = tp / (tp + fn) if tp + fn else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    # A redo repairs a real defect 87.5% of the time and breaks a sound note 12.5%
    net = tp * 0.875 - fp * 0.125
    return {"name": name, "tp": tp, "fn": fn, "fp": fp, "recall": rec,
            "fpr": fpr, "flagged": tp + fp, "net": net}


def main() -> None:
    cases = json.loads((MIG / "judge_benchmark80_blind.json").read_text())
    labels = json.loads((MIG / "judge_benchmark80_labels.json").read_text())

    detectors: dict[str, dict[str, bool]] = {k: {} for k in
                                             ("D2 imported term", "D3 dropped qualifier",
                                              "D4 tautology", "D2+D3+D4 union")}
    for t in (8, 12, 16, 20, 25, 30):
        detectors[f"D5 novel vocab >={t}"] = {}

    for c in cases:
        cid = c["case_id"]
        blob = "\n\n".join(c["sources"])
        title, body = c["title"], c["body"]
        note_text = f"{title}\n{body}"
        bullets = ps.mechanism_bullets(body)

        d2 = bool(ps.d2_imported_term(title, blob))
        d3 = bool(ps.d3_dropped_qualifier(blob, note_text))
        d4 = bool(ps.d4_tautology(title, bullets))
        detectors["D2 imported term"][cid] = d2
        detectors["D3 dropped qualifier"][cid] = d3
        detectors["D4 tautology"][cid] = d4
        detectors["D2+D3+D4 union"][cid] = d2 or d3 or d4
        for t in (8, 12, 16, 20, 25, 30):
            detectors[f"D5 novel vocab >={t}"][cid] = bool(
                d5_novel_vocabulary(title, body, blob, t))

    print(f"{'detector':<24} {'recall':>7} {'false-pos':>10} {'flagged':>8} "
          f"{'net fixed/10':>13}")
    print("-" * 66)
    rows = [score(n, f, labels) for n, f in detectors.items()]
    for r in rows:
        print(f"{r['name']:<24} {r['tp']}/10 {r['recall']:>4.0%} "
              f"{r['fp']:>4}/70 {r['fpr']:>4.0%} {r['flagged']:>7}/80 "
              f"{r['net']:>+12.1f}")
    print()
    print("For reference, measured on the same 80 cases:")
    print(f"{'Haiku':<24} 0/10   0%    2/70   3%       2/80        -0.3")
    print(f"{'MiniMax M3 self-judge':<24} 4/10  40%   18/70  26%      22/80        +1.3")
    print(f"{'Opus':<24} 10/10 100%    0/70   0%      10/80        +8.8")

    best = max(rows, key=lambda r: r["net"])
    print(f"\nbest mechanical: {best['name']}  net {best['net']:+.1f} of 10")


if __name__ == "__main__":
    main()
