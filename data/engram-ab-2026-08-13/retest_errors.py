"""Re-run the two failing pairs on both arms, 3 trials each, to tell
'the new prompt broke it' apart from 'the provider flaked'."""
from __future__ import annotations
import ast, json, os, subprocess, sys
sys.path.insert(0, os.environ["ORA_HOME"])
from orchestrator.historical.cleanup_backends import build_client
from orchestrator.historical.cleaned_pair_reader import load_cleaned_pair
from orchestrator.historical import phase5_atomic_extraction as p5
from pathlib import Path

PAIRS = ["2025-04-30_09-28_trump-trying-court-favor.md",
         "2025-04-01_16-25_find-tax-loophole-talking-pair005.md"]

src = subprocess.run(["git", "show", "HEAD:orchestrator/historical/phase5_atomic_extraction.py"],
                     capture_output=True, text=True, cwd=os.environ["ORA_HOME"]).stdout
OLD = next(ast.literal_eval(n.value) for n in ast.walk(ast.parse(src))
           if isinstance(n, ast.Assign)
           for t in n.targets if getattr(t, "id", None) == "_SYSTEM_PROMPT")

for name in PAIRS:
    cp = load_cleaned_pair(str(Path(p5.DEFAULT_ARCHIVE_DIR) / name))
    u, a = cp.cleaned_user_input, cp.cleaned_ai_response
    body = (f"USER MESSAGE:\n<<<\n{u[:3000]}\n>>>\n\n"
            f"AI RESPONSE:\n<<<\n{a[:3000]}\n>>>\n\n"
            f"Extract atomic notes (JSON array):")
    print(f"\n{name}")
    for arm, sysp in (("OLD", OLD), ("NEW", p5._SYSTEM_PROMPT)):
        outcomes = []
        for _ in range(3):
            c = build_client("openrouter")
            r = c.call(system=sysp, user=body, model=p5.EXTRACTION_MODEL,
                       max_tokens=4096, temperature=0.0)
            if r.error:
                outcomes.append(f"api:{r.error[:40]}")
                continue
            try:
                parsed = json.loads(p5._strip_json_fences(r.text))
                outcomes.append(f"ok({len(parsed)})")
            except json.JSONDecodeError:
                tail = r.text[-90:].replace("\n", " ")
                flagged = "high risk" in r.text or "rejected" in r.text
                outcomes.append("FILTERED" if flagged else f"parse|{tail!r}")
        print(f"  {arm}: {outcomes}")
