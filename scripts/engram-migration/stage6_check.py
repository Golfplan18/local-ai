#!/usr/bin/env python3
"""Stage 6 — deterministic conformance check over Stage 5 output.

ONE-TIME MIGRATION TOOL. Delete with the rest of scripts/engram-migration/.

Every rule here is mechanically decidable, so it runs over 100% of output rather
than a sample. That is the point: a checker gating everything beats a statistical
estimate of a defect rate, and it costs no model calls.

Rules, each traced to a defect measured during the trials:

  R1  standard_concept, when non-empty, appears verbatim in title or body.
      Trial rate before the prompt fix: 84.1% absent. The model would identify
      "routinization of charisma" and then publish a note that never contained
      the term, leaving it unfindable by the word a reader would search.

  R2  the Instance line introduces no specific absent from the unit's supplied
      specifics list. Trial output invented concrete examples for sources that
      carried none -- fluent, plausible, and indistinguishable from a real
      record. This is the only unrecoverable defect in the pipeline.

  R3  title prohibitions: proper noun, year, mechanism clause, hedge, inventory
      count, absolute.

  R4  facet coverage: a unit with N distinct member titles should not collapse
      to fewer than min(N, 2) mechanism bullets. Members are facets, not
      duplicates; a dropped facet dies when the members are deleted.

  R5  structural: non-empty title and body for KEEP, Instance line present, and
      at least one mechanism bullet (a note carrying only an Instance line has no
      claim in it).

  R6  Stage 3's extracted specifics themselves appear in the source. Measured:
      8.2% of Haiku's specifics are not verbatim in the member text, so
      validating the Instance line against that list alone would bless drift
      that entered a stage earlier. Soft, because much of it is benign case or
      hyphen normalisation -- but it is the only view of that error.

Exit code is non-zero if any HARD rule (R2, R5) fails, since those are silent
corruption rather than style. Writes repair.json listing every failure for the
Stage 7 repair pass.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

HEDGE = re.compile(r"\b(can|may|often|typically|sometimes|tends? to|generally|usually|frequently)\b", re.I)
MECH = re.compile(r"\b(because|when|by \w+ing|through \w+ing|due to)\b", re.I)
COUNT = re.compile(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+"
                   r"(distinct|major|primary|key|main|separate|different|types?|stages?|"
                   r"elements?|areas?|categories|phases?|criteria)\b", re.I)
YEAR = re.compile(r"\b(19|20)\d\d\b")
ABS = re.compile(r"\b(cannot|always|never|proves)\b", re.I)

# Sentence-initial capitals are not proper nouns. An earlier version of this
# checker counted the first word of every title ("Patterned", "Tracking",
# "Binary") as a dropped entity and reported a 92% failure rate that did not
# exist. A token counts only if it appears mid-sentence and never appears
# lowercase in the same text.
BENIGN = set("""The A An In On At By For With When Where What Why How This That These Those
It Its They Their There If As But And Or So Not No Yes One Two Three Four Five
Instance Each Every Both Any All Some Most Many Few Such Once Only Even Still""".split())


def proper_nouns(text: str) -> set[str]:
    """Mid-sentence capitalised tokens, LOWERCASED.

    Returned lowercased so cross-text comparison is case-insensitive. Comparing
    case-sensitively produced a 9.7% false fabrication rate: the writer rendered
    the source's "cultural accessibility" as "Cultural Accessibility", and
    "Cultural" then looked like an entity absent from the source. Nothing was
    invented -- only capitalised. Case is not evidence of fabrication.
    """
    lower = {w.lower() for w in re.findall(r"\b[a-z][a-z\-']{2,}\b", text)}
    out = set()
    for unit in re.split(r"(?:^|[\.\!\?\n]|^\s*-\s*)\s*", text):
        for tok in re.findall(r"\S+", unit)[1:]:
            m = re.match(r"([A-Z][a-zA-Z][a-zA-Z\-']{2,})", tok)
            if m and m.group(1) not in BENIGN and m.group(1).lower() not in lower:
                out.add(m.group(1).lower())
    return out


def vocabulary(text: str) -> set[str]:
    """Every alphabetic token, lowercased. The exclusion set for R2/R6: if the
    source contains a word in any case, a later stage using it is not inventing
    anything."""
    return {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z\-']{1,}", text or "")}


def numbers(text: str) -> set[str]:
    """Numeric tokens, with hyphenated dates kept whole.

    Splitting on hyphens turned "2026-04-29" into {2026, 04, 29}, and a source
    that wrote the date differently then registered "04" and "29" as novel
    figures. Match the full date first and remove it before scanning for bare
    numbers.
    """
    out: set[str] = set()
    rest = text
    for m in re.finditer(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b", text):
        out.add(m.group(0))
    rest = re.sub(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b", " ", text)
    out |= set(re.findall(r"\b\d[\d,\.]*%?\b", rest))
    out |= set(re.findall(r"[$£€]\d[\d,\.]*[KMB]?\b", rest))
    # A bare 1-2 digit number is an enumerator far more often than a fact
    # ("Stage 6", "Chapter 4", bullet indices); it is not a specific worth
    # gating a HARD failure on.
    return {n for n in out if not re.fullmatch(r"\d{1,2}", n)}


def instance_line(body: str) -> str:
    for ln in (body or "").splitlines():
        t = ln.strip().lstrip("-").strip()
        if t.lower().startswith("instance:"):
            return t[len("instance:"):].strip()
    return ""


def mechanism_bullets(body: str) -> int:
    n = 0
    for ln in (body or "").splitlines():
        t = ln.strip().lstrip("-").strip()
        if t and not t.lower().startswith("instance:"):
            n += 1
    return n


def check(rec: dict, unit: dict) -> list[str]:
    """Return violation codes for one Stage 5 record. HARD: prefix = corruption."""
    bad: list[str] = []
    if rec.get("verdict") != "KEEP":
        return bad

    title = (rec.get("new_title") or "").strip()
    body = (rec.get("new_body") or "").strip()
    if not title or not body:
        return ["HARD:R5_empty_output"]

    std = (rec.get("standard_concept") or "").strip()
    if std:
        core = re.sub(r"\(.*?\)", "", std).strip().lower()
        if core and core not in (title + " " + body).lower():
            bad.append("R1_concept_absent")

    inst = instance_line(body)
    if not inst:
        bad.append("HARD:R5_no_instance_line")
    else:
        # Validate against the ORIGINAL member text where we have it, not only
        # against Stage 3's specifics list. Measured: 8.2% of Haiku's extracted
        # specifics do not appear verbatim in the source, so checking the
        # Instance line against that list alone would bless drift that entered
        # one stage earlier. source_text is the union of member titles+bodies.
        allowed = " ".join(unit.get("specifics") or [])
        ground = unit.get("source_text") or ""
        # Compare candidate entities against the source's WHOLE VOCABULARY, not
        # against entities extracted from it. proper_nouns() only returns
        # capitalised tokens, so a source that wrote "cultural accessibility" or
        # "chapter 4" in lowercase contributed nothing to the comparison set and
        # the writer's "Cultural Accessibility" looked invented. A word the
        # source contains in any case is not a fabrication.
        source_vocab = vocabulary(allowed) | vocabulary(ground)
        source_nums = numbers(allowed) | numbers(ground)
        novel_p = {w for w in proper_nouns(inst) if w not in source_vocab}
        novel_n = numbers(inst) - source_nums
        # "none recorded in source" is the sanctioned empty form
        if "none recorded in source" not in inst.lower() and (novel_n or novel_p):
            bad.append("HARD:R2_fabricated_specific")
        if ground:
            gv, gn = vocabulary(ground), numbers(ground)
            drift_p = {w for w in proper_nouns(allowed) if w not in gv}
            drift_n = numbers(allowed) - gn
            if drift_n or drift_p:
                bad.append("R6_specifics_drift")

    tb = []
    if YEAR.search(title): tb.append("year")
    if HEDGE.search(title): tb.append("hedge")
    if MECH.search(title): tb.append("mech")
    if COUNT.search(title): tb.append("inventory")
    if ABS.search(title): tb.append("absolute")
    if proper_nouns(title): tb.append("propernoun")
    if tb:
        bad.append("R3_title:" + "+".join(tb))

    # Zero mechanism bullets means the note carries no claim at all -- only an
    # Instance line. That is structurally empty, not merely thin, so it is hard.
    mech_n = mechanism_bullets(body)
    n_members = len(unit.get("member_titles") or unit.get("member_files") or [])
    if mech_n == 0:
        bad.append("HARD:R5_no_mechanism")
    elif n_members >= 2 and mech_n < min(n_members, 2):
        bad.append("R4_facets_dropped")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--migration", default=str(Path.home() / "engram-work" / ".migration"))
    args = ap.parse_args()
    M = Path(args.migration)

    # units keyed by id, carrying the specifics Stage 3 extracted
    units: dict[str, dict] = {}
    for p in sorted((M / "stage3").glob("result_*.json")):
        try:
            recs = json.loads(p.read_text())
        except Exception:
            continue
        recs = recs if isinstance(recs, list) else recs.get("results", [])
        for r in recs:
            if r.get("unit_id"):
                units[r["unit_id"]] = r
    # member titles AND full source text come from the shards. The source text is
    # the ground truth for R2/R6: it is the only thing in this pipeline that was
    # not written by a model.
    titles: dict[str, list[str]] = {}
    ground: dict[str, str] = {}
    for p in sorted((M / "shards").glob("shard_*.json")):
        for u in json.loads(p.read_text()):
            titles[u["unit_id"]] = [m["title"] for m in u["members"]]
            ground[u["unit_id"]] = " ".join(
                (m.get("title") or "") + " " + (m.get("body") or "") for m in u["members"])
    for uid, u in units.items():
        u["member_titles"] = titles.get(uid, [])
        u["source_text"] = ground.get(uid, "")

    out = sorted((M / "stage5").glob("result_*.json"))
    if not out:
        print("[stage6] no Stage 5 output yet", file=sys.stderr)
        return 0

    fails = collections.Counter()
    repair, n, hard = [], 0, 0
    for p in out:
        try:
            recs = json.loads(p.read_text())
        except Exception as e:
            print(f"[stage6] unparseable {p.name}: {e}", file=sys.stderr)
            continue
        recs = recs if isinstance(recs, list) else recs.get("results", [])
        for r in recs:
            u = units.get(r.get("unit_id"))
            if not u:
                continue
            n += 1
            v = check(r, u)
            for code in v:
                fails[code.split(":")[0] if not code.startswith("HARD") else code.split(":")[1].split("_")[0]] += 1
            if v:
                if any(c.startswith("HARD") for c in v):
                    hard += 1
                repair.append({"unit_id": r["unit_id"], "violations": v,
                               "new_title": r.get("new_title", ""),
                               "shard": p.name})

    print(f"[stage6] KEEP records checked: {n:,}")
    for code, c in fails.most_common():
        print(f"   {code:22s} {c:6,}  {c/max(1,n)*100:5.1f}%")
    clean = n - len(repair)
    print(f"   {'CLEAN':22s} {clean:6,}  {clean/max(1,n)*100:5.1f}%")
    print(f"[stage6] records with a HARD violation (corruption): {hard:,}")

    (M / "repair.json").write_text(json.dumps(repair, indent=1))
    print(f"[stage6] wrote {len(repair):,} repair records -> {M/'repair.json'}")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
