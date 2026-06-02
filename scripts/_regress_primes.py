#!/usr/bin/env /opt/homebrew/bin/python3
"""Regression harness for the pre-routing pipeline.

Extracts the prime prompt for every technique in
`Reference — Trigger Prompt Corpus.md`, runs each through
run_pre_routing_pipeline, and emits a per-technique routing outcome.

Usage:
    _regress_primes.py snapshot <out.json>     # write baseline/after snapshot
    _regress_primes.py diff <before.json> <after.json>   # compare two snapshots

A "routing outcome" is the tuple (dispatched_mode_id, bypass, has_pending).
A break = the prime's intended-mode match flips from MATCH to non-MATCH,
OR the outcome tuple changes between snapshots.
"""
import json
import os
import re
import sys

ORCH = "/Users/oracle/ora/orchestrator"
if ORCH not in sys.path:
    sys.path.insert(0, ORCH)

CORPUS = os.path.expanduser(
    "~/Documents/vault/Reference — Trigger Prompt Corpus.md"
)


def extract_primes(path: str) -> list[dict]:
    """Return [{technique, intended_mode, prime}] for each #### block."""
    with open(path) as f:
        text = f.read()
    primes = []
    # Split on level-3/4 technique headings: #### `name` (modes) and
    # ### `name` (visual tools). Territory/section headings have no
    # backtick-wrapped first token and are skipped below.
    blocks = re.split(r"\n#{3,4} ", text)
    for blk in blocks[1:]:
        # technique name is the first backtick-wrapped token
        mname = re.match(r"`([^`]+)`", blk)
        if not mname:
            continue
        technique = mname.group(1).strip()
        # Modes use "**Intended mode:**"; visual tools use "**Routes to:**".
        im = re.search(r"\*\*(?:Intended mode|Routes to):\*\*\s*`([^`]+)`", blk)
        intended = im.group(1).strip() if im else technique
        # Prime prompt: the "1. ..." line in the Prime prompt section.
        # Capture from the Prime-prompt marker to the Other-examples marker.
        pm = re.search(
            r"\*\*Prime prompt[^\n]*\*\*\s*\n+\s*1\.\s+(.*?)(?:\n\n|\n\*\*|\Z)",
            blk, re.DOTALL,
        )
        if not pm:
            continue
        prime = pm.group(1).strip().replace("\n", " ")
        primes.append({
            "technique": technique,
            "intended_mode": intended,
            "prime": prime,
        })
    return primes


def run_one(prime: str) -> dict:
    from boot import run_pre_routing_pipeline
    r = run_pre_routing_pipeline(prime)
    dispatched = r.get("dispatched_mode_id")
    bypass = bool(r.get("bypass_to_direct_response"))
    pending = r.get("pending_clarification") is not None
    if dispatched and not pending:
        verdict = "PASS"
    elif bypass:
        verdict = "BYPASS"
    elif pending:
        verdict = "CLARIFICATION"
    else:
        verdict = "UNRESOLVED"
    return {
        "verdict": verdict,
        "dispatched": dispatched,
        "bypass": bypass,
        "pending": pending,
        "territory": r.get("territory"),
        "confidence": r.get("confidence"),
        "pending_stage": r.get("pending_clarification_stage"),
    }


def snapshot(out_path: str):
    primes = extract_primes(CORPUS)
    results = []
    for p in primes:
        out = run_one(p["prime"])
        out["technique"] = p["technique"]
        out["intended_mode"] = p["intended_mode"]
        out["match"] = (out["dispatched"] == p["intended_mode"]
                        and out["verdict"] == "PASS")
        out["prime"] = p["prime"]
        results.append(out)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    total = len(results)
    matched = sum(1 for r in results if r["match"])
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    print(f"techniques: {total}")
    print(f"PASS verdict: {passed}/{total}")
    print(f"dispatch == intended mode (clean): {matched}/{total}")
    nonmatch = [r for r in results if not r["match"]]
    if nonmatch:
        print(f"\n{len(nonmatch)} technique(s) NOT routing to intended mode:")
        for r in nonmatch:
            print(f"  {r['technique']:32} intended={r['intended_mode']:26} "
                  f"got={str(r['dispatched']):26} [{r['verdict']}]")
    print(f"\nsnapshot written: {out_path}")


def diff(before_path: str, after_path: str):
    with open(before_path) as f:
        before = {r["technique"]: r for r in json.load(f)}
    with open(after_path) as f:
        after = {r["technique"]: r for r in json.load(f)}

    def outcome(r):
        return (r["dispatched"], r["bypass"], r["pending"])

    breaks = []
    improvements = []
    for tech, b in before.items():
        a = after.get(tech)
        if a is None:
            continue
        if outcome(b) != outcome(a):
            # changed outcome — classify
            if b["match"] and not a["match"]:
                breaks.append((tech, b, a))
            elif not b["match"] and a["match"]:
                improvements.append((tech, b, a))
            else:
                # outcome changed but match status same — neutral/inspect
                breaks.append((tech, b, a)) if b["match"] else \
                    improvements.append((tech, b, a))
    print("=" * 70)
    print(f"REGRESSION DIFF  {before_path}  ->  {after_path}")
    print("=" * 70)
    b_match = sum(1 for r in before.values() if r["match"])
    a_match = sum(1 for r in after.values() if r["match"])
    print(f"clean (dispatch==intended): {b_match} -> {a_match}")
    print()
    if not breaks:
        print("✅ ZERO BREAKS — every previously-clean prime still routes "
              "to its intended mode with the same outcome.")
    else:
        print(f"❌ {len(breaks)} BREAK(S):")
        for tech, b, a in breaks:
            print(f"  {tech}")
            print(f"     before: {b['verdict']:14} -> {b['dispatched']}")
            print(f"     after:  {a['verdict']:14} -> {a['dispatched']}")
    print()
    if improvements:
        print(f"📈 {len(improvements)} CHANGED-FOR-BETTER / neutral:")
        for tech, b, a in improvements:
            print(f"  {tech}: {b['dispatched']}/{b['verdict']} -> "
                  f"{a['dispatched']}/{a['verdict']}")
    return len(breaks)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "snapshot":
        snapshot(sys.argv[2])
    elif len(sys.argv) >= 4 and sys.argv[1] == "diff":
        n = diff(sys.argv[2], sys.argv[3])
        sys.exit(1 if n else 0)
    else:
        print(__doc__)
        sys.exit(2)
