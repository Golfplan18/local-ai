"""A/B the permanent-note prompt port on real conversation pairs.

Arm OLD = the prompt as it stands at HEAD. Arm NEW = the ported standard.
Same model, same pairs, same user-message format, temperature 0.

Writes ab_results.json. Excludes pairs tagged `private`.
"""
from __future__ import annotations

import ast
import json
import os
import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, os.environ["ORA_HOME"])

from orchestrator.historical.cleanup_backends import build_client  # noqa: E402
from orchestrator.historical.cleaned_pair_reader import load_cleaned_pair  # noqa: E402
from orchestrator.historical import phase5_atomic_extraction as p5  # noqa: E402

OUT = Path(__file__).parent / "ab_results.json"
N_PAIRS = int(os.environ.get("N_PAIRS", "16"))


def old_system_prompt() -> str:
    src = subprocess.run(
        ["git", "show", "HEAD:orchestrator/historical/phase5_atomic_extraction.py"],
        capture_output=True, text=True, cwd=os.environ["ORA_HOME"],
    ).stdout
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if getattr(t, "id", None) == "_SYSTEM_PROMPT":
                    return ast.literal_eval(node.value)
    raise SystemExit("could not extract OLD prompt")


def pick_pairs() -> list:
    archive = Path(p5.DEFAULT_ARCHIVE_DIR)
    files = sorted(archive.glob("*.md"))
    random.Random(20260813).shuffle(files)
    chosen = []
    for f in files:
        if len(chosen) >= N_PAIRS:
            break
        try:
            cp = load_cleaned_pair(str(f))
        except Exception:
            continue
        if "private" in (cp.tags or []):
            continue
        user, ai = cp.cleaned_user_input or "", cp.cleaned_ai_response or ""
        if len(user) + len(ai) < 1200:      # substantive pairs only
            continue
        chosen.append((f.name, user, ai))
    return chosen


def run_arm(client, system: str, user: str, ai: str):
    body = (
        f"USER MESSAGE:\n<<<\n{user[:p5.MAX_PAIR_CHARS_FOR_EXTRACTION // 2]}\n>>>\n\n"
        f"AI RESPONSE:\n<<<\n{ai[:p5.MAX_PAIR_CHARS_FOR_EXTRACTION // 2]}\n>>>\n\n"
        f"Extract atomic notes (JSON array):"
    )
    r = client.call(system=system, user=body, model=p5.EXTRACTION_MODEL,
                    max_tokens=4096, temperature=0.0)
    if r.error:
        return {"error": r.error, "notes": []}
    try:
        parsed = json.loads(p5._strip_json_fences(r.text))
        if not isinstance(parsed, list):
            return {"error": "not a list", "raw": r.text[:400], "notes": []}
    except json.JSONDecodeError as e:
        return {"error": f"json: {e}", "raw": r.text[:400], "notes": []}
    return {"error": "", "notes": parsed, "out_tokens": r.output_tokens,
            "in_tokens": r.input_tokens, "cost": r.cost_usd}


def main():
    OLD, NEW = old_system_prompt(), p5._SYSTEM_PROMPT
    assert OLD != NEW, "prompts identical — nothing to compare"
    pairs = pick_pairs()
    print(f"{len(pairs)} pairs | OLD {len(OLD)}c  NEW {len(NEW)}c", flush=True)

    def work(item):
        name, user, ai = item
        c = build_client(os.environ.get("BACKEND", "openrouter"))
        return {"pair": name,
                "source": {"user": user[:3000], "ai": ai[:3000]},
                "old": run_arm(c, OLD, user, ai),
                "new": run_arm(c, NEW, user, ai)}

    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(work, pairs))

    OUT.write_text(json.dumps(results, indent=1))
    for tag in ("old", "new"):
        notes = sum(len(r[tag]["notes"]) for r in results)
        errs = sum(1 for r in results if r[tag]["error"])
        cost = sum(r[tag].get("cost", 0) or 0 for r in results)
        print(f"{tag.upper():4} notes={notes:3}  errors={errs}  cost=${cost:.4f}")
    print("->", OUT)


if __name__ == "__main__":
    main()
