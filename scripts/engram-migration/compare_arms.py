#!/usr/bin/env python3
"""Three-way Stage 5 arm comparison: Opus/titles vs Opus/bodies vs Fable/titles.

Same 320 units in every arm. Reuses stage6_check.check() so all arms are scored
by the identical rules, then adds arm-vs-arm measures the checker cannot see:
concept-naming rate, concept agreement with the Opus reference, mechanism-bullet
counts (facet absorption), and title nominalization density (the paraphrase
smell that separated Haiku from Opus).
"""
import json, glob, re, collections, statistics, importlib.util
from pathlib import Path

M = Path("/Users/oracle/engram-work/.migration")
ARMS = {"opus-titles": "stage5", "opus-bodies": "stage5_bodies", "fable-titles": "stage5_fable"}

spec = importlib.util.spec_from_file_location(
    "s6", "/Users/oracle/ora/scripts/engram-migration/stage6_check.py")
s6 = importlib.util.module_from_spec(spec); spec.loader.exec_module(s6)

# units with specifics, member_titles, source_text (ground truth)
units = {}
for p in sorted((M / "stage3").glob("result_*.json")):
    try:
        for r in json.loads(p.read_text()):
            if r.get("unit_id"):
                units[r["unit_id"]] = dict(r)
    except Exception:
        pass
for p in sorted((M / "shards").glob("shard_*.json")):
    for u in json.loads(p.read_text()):
        if u["unit_id"] in units:
            units[u["unit_id"]]["member_titles"] = [m["title"] for m in u["members"]]
            units[u["unit_id"]]["source_text"] = " ".join(
                (m.get("title") or "") + " " + (m.get("body") or "") for m in u["members"])

NOM = re.compile(r"\b\w+(?:tion|ment|ance|ence|ity|ness|ism|ization|isation)\b", re.I)
def nomdens(s):
    w = re.findall(r"[A-Za-z]+", s or "")
    return len(NOM.findall(s or "")) / max(1, len(w))

def mech_bullets(body):
    return sum(1 for ln in (body or "").splitlines()
               if ln.strip().lstrip("-").strip()
               and not ln.strip().lstrip("-").strip().lower().startswith("instance:"))

arms = {}
for name, sub in ARMS.items():
    recs = {}
    for p in sorted((M / sub).glob("result_*.json")):
        try:
            for r in json.loads(p.read_text()):
                if r.get("unit_id"):
                    recs[r["unit_id"]] = r
        except Exception:
            print(f"  !! {name}: unparseable {p.name}")
    arms[name] = recs

common = set.intersection(*(set(v) for v in arms.values())) if all(arms.values()) else set()
print(f"arms loaded: { {k: len(v) for k, v in arms.items()} }   common units: {len(common)}")

print(f"\n{'':16s}{'KEEP':>6}{'HARD':>6}{'R1':>5}{'R3':>5}{'R4':>5}{'CLEAN':>7}"
      f"{'concept%':>10}{'bullets':>9}{'nomden%':>9}")
for name, recs in arms.items():
    keeps = [r for r in recs.values() if r.get("verdict") == "KEEP"]
    viol = collections.Counter(); clean = 0
    for r in keeps:
        u = units.get(r["unit_id"], {})
        v = s6.check(r, u)
        if not [x for x in v if not x.startswith("R6")]:
            clean += 1
        for code in v:
            key = "HARD" if code.startswith("HARD") else code.split("_")[0].split(":")[0]
            viol[key] += 1
    named = sum(1 for r in keeps if (r.get("standard_concept") or "").strip())
    mb = [mech_bullets(r.get("new_body")) for r in keeps]
    nd = [nomdens(r.get("new_title")) for r in keeps]
    print(f"{name:16s}{len(keeps):>6}{viol['HARD']:>6}{viol['R1']:>5}{viol['R3']:>5}"
          f"{viol['R4']:>5}{clean:>7}"
          f"{named/max(1,len(keeps))*100:>9.1f}%{statistics.mean(mb):>9.2f}"
          f"{statistics.mean(nd)*100:>8.2f}%")

# concept agreement vs the opus-titles reference
ref = arms.get("opus-titles", {})
nrm = s6 if hasattr(s6, "norm") else None
spec8 = importlib.util.spec_from_file_location(
    "s8b", "/Users/oracle/ora/scripts/engram-migration/stage8b_concept_audit.py")
s8b = importlib.util.module_from_spec(spec8); spec8.loader.exec_module(s8b)
print("\nconcept agreement with opus-titles (same unit, both named a concept):")
for name, recs in arms.items():
    if name == "opus-titles":
        continue
    both = [u for u in common
            if (ref[u].get("standard_concept") or "").strip()
            and (recs[u].get("standard_concept") or "").strip()]
    agree = sum(1 for u in both
                if s8b.norm(ref[u]["standard_concept"]) == s8b.norm(recs[u]["standard_concept"]))
    print(f"  {name:14s} both-named={len(both):3d}  exact-normalised-agree={agree} "
          f"({agree/max(1,len(both))*100:.0f}%)")

# side-by-side sample
print("\n" + "=" * 90)
shown = 0
for uid in sorted(common):
    r0 = arms["opus-titles"].get(uid); rf = arms["fable-titles"].get(uid)
    rb = arms["opus-bodies"].get(uid)
    if not (r0 and rf and rb):
        continue
    if units.get(uid, {}).get("verdict") != "KEEP" or (units[uid].get("size", 1) if "size" in units[uid] else 5) < 1:
        pass
    print(f"\n[{uid}] {len(units[uid].get('member_titles') or [])} members")
    print(f"  OPUS/T : {r0.get('new_title','')[:118]}   [{r0.get('standard_concept','')}]")
    print(f"  OPUS/B : {rb.get('new_title','')[:118]}   [{rb.get('standard_concept','')}]")
    print(f"  FABLE  : {rf.get('new_title','')[:118]}   [{rf.get('standard_concept','')}]")
    shown += 1
    if shown >= 6:
        break
