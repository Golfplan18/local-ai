"""Can M3 judge its own output? Same blind benchmark, same criteria as Haiku.

Every unparseable reply is written to disk rather than theorised about — the
single most expensive lesson in this project's history.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, os.path.expanduser("~/ora"))
from orchestrator.historical.cleanup_backends import MiniMaxClient  # noqa: E402

MIG = Path(os.path.expanduser("~/engram-work/.migration"))
BLIND = MIG / "judge_benchmark80_blind.json"
OUT = MIG / "m3-judge"
FAIL = MIG / "m3-judge-failures"

SYSTEM = """\
You judge rewritten knowledge-base notes against the sources they came from.

Call DEFECT only for a REAL defect — something that makes the note untrue,
unsupported, or useless. The kinds that matter:

- fabrication: a name, number, date, example, or evidence claim that appears
  nowhere in the sources
- unsupported_hardening: the sources hedge ("can be", "often") and the note
  states it flatly, or the sources report a tendency and the note asserts cause
- dropped_qualification: a clause the sources make load-bearing ("despite X",
  "even when Y", "without Z") is gone and its absence leaves the claim circular
  or trivially true
- imported_term_of_art: the note names a concept, bias, effect or theory that
  the sources never name
- domain_stripped: the sources are craft knowledge (how to write fiction, a
  physical technique) where the domain IS the subject, and the note restates it
  as a general factual claim
- tautology: the claim is true of almost anything, or restates itself
- overbroad_noun: a noun was generalized so far the claim becomes false of
  things it now covers

Do NOT call DEFECT for: wording you would have chosen differently, a title being
long or short, punctuation, style, or a claim being unsurprising. A note that is
accurate and general but plainly written is SOUND.

Most notes are sound. Flag only what you can point at in the sources. Quote the
specific phrase that fails and what the source actually says.

Return ONLY a JSON object:
{"case_id": "...", "verdict": "SOUND"|"DEFECT",
 "defect_kind": "none"|"fabrication"|"unsupported_hardening"|"dropped_qualification"|"imported_term_of_art"|"domain_stripped"|"tautology"|"overbroad_noun",
 "reason": "..."}
"""

_lock = threading.Lock()
_done = [0]


def build_user(case: dict) -> str:
    srcs = "\n\n".join(f"--- SOURCE {i + 1} ---\n{s}"
                       for i, s in enumerate(case["sources"]))
    return (f'case_id: {case["case_id"]}\n\n'
            f'TITLE: {case["title"]}\n\nBODY:\n{case["body"]}\n\n'
            f'SOURCES THE CLAIM MUST COME FROM:\n{srcs}\n')


def extract(raw: str) -> dict | None:
    """Balanced-brace extraction; a first-to-last slice breaks on trailing text."""
    for i, c in enumerate(raw or ""):
        if c != "{":
            continue
        depth, in_str, esc = 0, False, False
        for j in range(i, len(raw)):
            ch = raw[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        v = json.loads(raw[i:j + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(v, dict) and "verdict" in v:
                        return v
                    break
    return None


def judge(case: dict, client: MiniMaxClient) -> None:
    dest = OUT / (re.sub(r"[^A-Za-z0-9_.-]", "_", case["case_id"]) + ".json")
    if dest.exists():
        return
    res = client.call(system=SYSTEM, user=build_user(case), max_tokens=32768,
                      temperature=0.0)
    rec = None if getattr(res, "error", "") else extract(res.text)
    if rec is None:
        FAIL.mkdir(parents=True, exist_ok=True)
        (FAIL / (dest.stem + ".txt")).write_text(
            (getattr(res, "error", "") or "") + "\n\n" + (res.text or ""),
            encoding="utf-8")
    else:
        rec["case_id"] = case["case_id"]
        dest.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    with _lock:
        _done[0] += 1
        if _done[0] % 10 == 0:
            print(f"  {_done[0]} judged", flush=True)


def main() -> int:
    cases = json.loads(BLIND.read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    client = MiniMaxClient()
    print(f"judging {len(cases)} blind cases on MiniMax-M3", flush=True)
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(judge, c, client) for c in cases]
        for f in as_completed(futs):
            f.result()
    ok = len(list(OUT.glob("*.json")))
    bad = len(list(FAIL.glob("*.txt"))) if FAIL.exists() else 0
    print(f"done — {ok} parsed, {bad} unparseable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
