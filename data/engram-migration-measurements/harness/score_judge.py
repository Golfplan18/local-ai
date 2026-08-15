"""Score a judge against the 80-case benchmark.

Ground truth is Opus's pairwise verdicts, not a human's. This measures AGREEMENT
WITH OPUS, not truth. Treat a disagreement as a case to read, not as a judge
error — several may be Opus's mistakes.

Recall is the metric that decides the design: a false positive costs one more
free M3 rewrite, a missed defect ships into the corpus.

Usage:  score_judge.py <name> <verdicts.json | dir-of-json>
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

MIG = pathlib.Path(os.path.expanduser("~/engram-work/.migration"))


def load_verdicts(target: str) -> dict[str, dict]:
    p = pathlib.Path(target)
    if p.is_dir():
        out = {}
        for f in p.glob("*.json"):
            r = json.loads(f.read_text())
            out[r["case_id"]] = r
        return out
    data = json.loads(p.read_text())
    rows = data["verdicts"] if isinstance(data, dict) else data
    return {r["case_id"]: r for r in rows}


def main() -> int:
    name, target = sys.argv[1], sys.argv[2]
    labels = json.loads((MIG / "judge_benchmark80_labels.json").read_text())
    got = load_verdicts(target)

    missing = [c for c in labels if c not in got]
    tp = fp = tn = fn = 0
    caught, missed, false_alarms = [], [], []
    for cid, truth in labels.items():
        v = got.get(cid)
        if not v:
            continue
        said = v.get("verdict")
        if truth == "DEFECT" and said == "DEFECT":
            tp += 1; caught.append((cid, v.get("defect_kind"), v.get("reason", "")))
        elif truth == "DEFECT":
            fn += 1; missed.append((cid, v.get("reason", "")))
        elif said == "DEFECT":
            fp += 1; false_alarms.append((cid, v.get("defect_kind"), v.get("reason", "")))
        else:
            tn += 1

    n = tp + fp + tn + fn
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0

    print(f"=== {name} ===")
    print(f"scored {n}/80   (no verdict returned for {len(missing)})")
    print(f"  caught  {tp}/10 real defects        RECALL     {rec:.0%}")
    print(f"  missed  {fn}/10")
    print(f"  false alarms {fp}/70 sound notes    FALSE-POS  {fpr:.0%}")
    print(f"  precision {prec:.0%}   -> flagging {tp + fp}/{n} notes redoes "
          f"{(tp + fp) / n:.0%} of the corpus to fix {tp}/10 defects")
    print()
    print("--- CAUGHT (real defects it found) ---")
    for cid, kind, why in caught:
        print(f"  [{kind}] {cid.split('::')[0][:52]}")
        print(f"      {why[:190]}")
    print()
    print("--- MISSED (real defects it called sound) ---")
    for cid, why in missed:
        print(f"  {cid.split('::')[0][:60]}")
    print()
    print(f"--- FALSE ALARMS (first 6 of {fp}) ---")
    for cid, kind, why in false_alarms[:6]:
        print(f"  [{kind}] {cid.split('::')[0][:52]}")
        print(f"      {why[:190]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
