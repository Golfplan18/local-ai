"""Blind-judge the A/B output against the ported writing standard.

Every note from both arms is pooled, stripped of its arm label, shuffled, and
judged one at a time with its source pair attached. The judge never learns
which prompt produced which note.
"""
from __future__ import annotations

import json
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, os.environ["ORA_HOME"])
from orchestrator.historical.cleanup_backends import build_client  # noqa: E402

HERE = Path(__file__).parent
RESULTS = json.loads((HERE / "ab_results.json").read_text())
OUT = HERE / "judge_ab_results.json"
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "claude-opus-4-5-20251101")

RUBRIC = """You are judging ONE note extracted from ONE conversation pair for a \
personal knowledge base, against that base's written standard. You are given the \
source conversation and the note. Judge ONLY against the source.

The standard:

1. CONVERSION-OR-CONDITION. A note earns its place one of two ways. Either the \
title states a CONVERSION — something turns into something and the result is \
perverse ("a leader who blames others turns criticism of his policy into proof \
his enemies are real") — or it states a STANDING CONDITION (something that \
holds, persists, or is withheld, nothing inverting) and names WHAT IT COSTS OR \
WHO IT SERVES. A title that merely describes a procedure or restates a \
mechanism neutrally meets neither bar. A conversion the source does not contain \
is FABRICATED and is a serious defect.

2. QUALIFICATIONS PRESERVED. Any clause in the source that qualifies or limits \
the claim — DESPITE something, EVEN WHEN something, ONLY IF something, WITHOUT \
something — must survive somewhere in the note. Dropping it, leaving a general \
claim that has lost the condition giving it force, is the most serious and most \
common defect. A note left asserting something circular or empty fails here.

3. GENERALIZATION IN RANGE. Too broad is a defect: a noun so abstract the claim \
becomes ambiguous or false of things the noun covers ("a shared system" covering \
a grazing commons). Too narrow is equally a defect: a noun that does not reach \
everything the mechanism reaches. Judge whether the claim stays TRUE across what \
its nouns cover.

4. DOMAIN HANDLED RIGHTLY. Some claims are craft knowledge where the domain IS \
the subject (how to make a character's arc convincing to readers). Those should \
KEEP their field. Others are universal mechanisms wearing a domain as costume; \
those should shed it. A note that strips a domain it needed (now gibberish or \
unintelligible), or keeps a domain it did not need (locked to its instance), \
fails here.

5. NO IMPORTED TERM OF ART. A named concept, bias, theory, or effect that the \
source does not support must not appear. A label that is close but not exact is \
a false claim.

6. ACTORS NAMED. Parties that ACT are identified, as roles rather than as the \
individuals who happened to act. But naming a role repeatedly in one sentence \
until it reads as noise is itself a defect. Pronouns are fine when their \
referent is named in the same sentence.

Reply with ONLY a JSON object:
{"c1_conversion":"PASS|FAIL","c2_qualifications":"PASS|FAIL",
 "c3_generalization":"PASS|FAIL","c4_domain":"PASS|FAIL",
 "c5_no_imported_term":"PASS|FAIL","c6_actors":"PASS|FAIL",
 "verdict":"SOUND|DEFECT","worst_problem":"<one sentence, or empty if SOUND>"}
A note is SOUND only if it would be worth keeping as written. Any FAIL on \
criteria 1, 2 or 5 makes it DEFECT."""


def build_cases():
    cases = []
    for r in RESULTS:
        src = (f"USER:\n{r['source']['user'][:2200]}\n\n"
               f"ASSISTANT:\n{r['source']['ai'][:2200]}")
        for arm in ("old", "new"):
            for i, n in enumerate(r[arm].get("notes", [])):
                if not isinstance(n, dict) or not n.get("title"):
                    continue
                cases.append({
                    "case_id": f"{r['pair']}::{arm}::{i}",
                    "arm": arm, "pair": r["pair"], "source": src,
                    "title": n.get("title", ""), "body": n.get("body", ""),
                    "std_concept": n.get("standard_concept", ""),
                })
    random.Random(4242).shuffle(cases)     # blind: order carries no arm signal
    return cases


def judge(case):
    note = (f"TITLE: {case['title']}\n\nBODY:\n{case['body']}")
    if case["std_concept"]:
        note += f"\n\nstandard_concept field: {case['std_concept']}"
    user = (f"=== SOURCE CONVERSATION ===\n{case['source']}\n\n"
            f"=== NOTE UNDER JUDGEMENT ===\n{note}\n\nJudge it.")
    c = build_client("api")
    # Opus 5 rejects `temperature`; the client only sends it when non-None.
    r = c.call(system=RUBRIC, user=user, model=JUDGE_MODEL,
               max_tokens=1200, temperature=None)
    if r.error:
        return {**case, "judge_error": r.error}
    txt = r.text.strip()
    if "```" in txt:
        txt = txt.split("```")[1].lstrip("json").strip()
    try:
        v = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
    except Exception as e:
        return {**case, "judge_error": f"parse: {e}", "raw": r.text[:300]}
    return {**case, **v}


def main():
    cases = build_cases()
    print(f"judging {len(cases)} notes blind ({JUDGE_MODEL})", flush=True)
    with ThreadPoolExecutor(max_workers=6) as ex:
        judged = list(ex.map(judge, cases))
    OUT.write_text(json.dumps(judged, indent=1))

    crits = ["c1_conversion", "c2_qualifications", "c3_generalization",
             "c4_domain", "c5_no_imported_term", "c6_actors"]
    print(f"\n{'':22}  {'OLD':>12}  {'NEW':>12}")
    for arm in ("old", "new"):
        pass
    rows = {}
    for crit in crits + ["verdict"]:
        rows[crit] = {}
        for arm in ("old", "new"):
            a = [j for j in judged if j["arm"] == arm and "judge_error" not in j]
            if crit == "verdict":
                good = sum(1 for j in a if j.get("verdict") == "SOUND")
            else:
                good = sum(1 for j in a if j.get(crit) == "PASS")
            rows[crit][arm] = (good, len(a))
    for crit in crits + ["verdict"]:
        o, n = rows[crit]["old"], rows[crit]["new"]
        label = "SOUND overall" if crit == "verdict" else crit
        op = 100 * o[0] / o[1] if o[1] else 0
        np_ = 100 * n[0] / n[1] if n[1] else 0
        print(f"{label:22}  {o[0]:3}/{o[1]:<3} {op:5.0f}%  "
              f"{n[0]:3}/{n[1]:<3} {np_:5.0f}%   {np_-op:+5.0f}pp")
    errs = [j for j in judged if "judge_error" in j]
    if errs:
        print(f"\njudge errors: {len(errs)}")
    print("->", OUT)


if __name__ == "__main__":
    main()
