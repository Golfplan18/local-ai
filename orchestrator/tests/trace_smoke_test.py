#!/usr/bin/env python3
"""
trace_smoke_test.py — End-to-end smoke test of the pipeline trace.

Submits three test prompts to ``run_pipeline`` and reports the trace
directory each produced. The point is not to evaluate model output —
it's to confirm the trace machinery captures every step's inputs and
outputs to disk and surfaces silent failures.

Run from anywhere:
    /opt/homebrew/bin/python3 ~/ora/orchestrator/tests/trace_smoke_test.py [prompt-id]

Prompt IDs:
    bypass  — Stage 1 bypass; minimal model load (Phase A + classification slot)
    gear3   — Analytical prompt routing to Gear 3 (sequential adversarial)
    gear4   — Analytical prompt routing to Gear 4 (parallel adversarial)
    all     — run all three (heavy: loads 70B + 72B + 27B + 4B local models)

Default: ``bypass`` — finishes in roughly the time it takes to load the
27B cleanup model + a single 4B classification pass.
"""

from __future__ import annotations

import os
import sys
import time
import json

WORKSPACE = os.path.expanduser("~/ora/")
sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator"))
sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/tools"))


PROMPTS = {
    "bypass": (
        # Should trigger Stage 1 bypass — no analytical pipeline.
        # Tests Phase A cleanup + pre-routing Stage 1.
        "Hello, what time is it right now?"
    ),
    "gear3": (
        # Should route to an analytical mode with DEFAULT GEAR: 3.
        # Tests Phase A + pre-routing + Step 2 context + sequential
        # adversarial Steps 3-6 (no consolidate/format).
        "Quick steelman: is the claim 'remote work raises productivity' "
        "well-supported?"
    ),
    "gear4": (
        # Should route to an analytical mode with DEFAULT GEAR: 4.
        # Tests the full parallel adversarial pipeline Steps 3-8.
        "Analyze the tradeoffs of using a 70B local model vs a commercial "
        "API for adversarial review in a privacy-sensitive workflow."
    ),
}


def run_prompt(prompt_id: str) -> None:
    from boot import run_pipeline
    import pipeline_trace

    if prompt_id not in PROMPTS:
        print(f"[smoke] unknown prompt id: {prompt_id}", file=sys.stderr)
        sys.exit(2)

    conv_id = f"smoke-{prompt_id}-{int(time.time())}"
    print(f"[smoke] starting: conv_id={conv_id}")
    print(f"[smoke] prompt: {PROMPTS[prompt_id]!r}")
    t0 = time.time()
    try:
        response = run_pipeline(
            user_input=PROMPTS[prompt_id],
            conversation_id=conv_id,
            ambiguity_mode="assume",
        )
    except Exception as e:
        print(f"[smoke] pipeline raised: {type(e).__name__}: {e}", file=sys.stderr)
        response = f"[exception: {e}]"
    elapsed = time.time() - t0

    trace_dir = pipeline_trace.latest_trace_dir(conv_id)
    print(f"\n[smoke] elapsed: {elapsed:.1f}s")
    print(f"[smoke] trace_dir: {trace_dir}")
    if trace_dir and os.path.isdir(trace_dir):
        files = sorted(os.listdir(trace_dir))
        print(f"[smoke] trace files ({len(files)}):")
        for f in files:
            size = os.path.getsize(os.path.join(trace_dir, f))
            print(f"  - {f} ({size} bytes)")
    print(f"\n[smoke] response (first 600 chars):")
    print((response or "")[:600])
    print("---")


def summarize_trace(trace_dir: str) -> None:
    """Pretty-print the key observations from a trace directory."""
    if not os.path.isdir(trace_dir):
        print(f"[summary] trace dir not found: {trace_dir}")
        return
    print(f"[summary] {trace_dir}\n")
    for fname in sorted(os.listdir(trace_dir)):
        path = os.path.join(trace_dir, fname)
        size = os.path.getsize(path)
        if fname.endswith(".jsonl"):
            with open(path) as f:
                lines = f.readlines()
            print(f"  {fname}: {size}B, {len(lines)} records")
            for line in lines[:3]:
                rec = json.loads(line)
                print(f"    - {rec.get('query_type', rec.get('step', '?'))}: "
                      f"{rec.get('error', rec.get('gap_statement', ''))[:80]}")
        elif fname.endswith(".json"):
            print(f"  {fname}: {size}B")


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "bypass"
    if arg == "all":
        for pid in ["bypass", "gear3", "gear4"]:
            print(f"\n{'=' * 70}\n[smoke] === {pid.upper()} ===\n{'=' * 70}")
            run_prompt(pid)
    else:
        run_prompt(arg)


if __name__ == "__main__":
    main()
