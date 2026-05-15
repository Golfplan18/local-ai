#!/usr/bin/env python3
"""
gear_test_direct.py — Direct Gear 3 / Gear 4 test harness.

Bypasses the pre-routing pipeline (which is currently routing many
prompts to bypass via the cui-bono substring collision bug) and invokes
``run_gear3`` or ``run_gear4`` directly against a chosen mode. Useful
for testing the gear pipelines in isolation while pre-routing issues
are being resolved.

Usage:
    /opt/homebrew/bin/python3 ~/ora/orchestrator/tests/gear_test_direct.py <gear> <mode> "<prompt>"

Example:
    /opt/homebrew/bin/python3 .../gear_test_direct.py 4 cui-bono \
        "Who benefits from the shift from model-as-product to harness-as-product?"

The mode's actual ``## DEFAULT GEAR`` heading is ignored — the gear is
forced from the CLI argument. The mode file's per-step sections
(DEPTH GUIDANCE / BREADTH GUIDANCE / EVALUATION CRITERIA / etc.) are
still loaded normally.

Produces the full per-turn trace at
``~/ora/data/pipeline-traces/direct-<gear>-<mode>-<ts>/``.
"""

from __future__ import annotations

import os
import sys
import time

WORKSPACE = os.path.expanduser("~/ora/")
sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator"))
sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/tools"))


def main():
    if len(sys.argv) < 4:
        print(__doc__, file=sys.stderr)
        sys.exit(2)

    gear = int(sys.argv[1])
    mode_name = sys.argv[2]
    prompt = sys.argv[3]
    if gear not in (3, 4):
        print("[error] gear must be 3 or 4", file=sys.stderr)
        sys.exit(2)

    import pipeline_trace
    from boot import (
        load_endpoints, load_mode, run_gear3, run_gear4,
    )

    config = load_endpoints()
    mode_text = load_mode(mode_name)
    if not mode_text:
        print(f"[error] mode file empty or missing: {mode_name}", file=sys.stderr)
        sys.exit(2)

    conv_id = f"direct-g{gear}-{mode_name}-{int(time.time())}"
    trace_dir = pipeline_trace.start_trace(
        conversation_id=conv_id,
        raw_input=prompt,
        ambiguity_mode="assume",
    )

    # Build a minimal context_pkg compatible with run_gear3 / run_gear4.
    # Skip Phase A and pre-routing; the operational notation is just the
    # raw prompt for this direct test.
    context_pkg = {
        "cleaned_prompt": prompt,
        "natural_language_prompt": prompt,
        "mode_name": mode_name,
        "mode_text": mode_text,
        "gear": gear,
        "conversation_rag": "",
        "concept_rag": "",
        "relationship_rag": "",
        "triage_tier": 2,
        "rag_signals": [],
        "rag_utilization": "",
        "hardware_tier": 0,
        "territory": None,
        "mode": mode_name,
        "residual_disambiguation_questions": [],
        "completeness_gaps": [],
        "dispatch_announcement": None,
        "pre_routing": {},
        "trace_dir": trace_dir,
    }

    # Write a synthetic step1/step2 trace so the directory layout matches
    # production runs and the trace is comparably structured.
    pipeline_trace.write_step(trace_dir, "step1-phase-a", {
        "status": "skipped_direct_test_harness",
        "raw_prompt": prompt,
    }, markdown=f"# Step 1 — skipped (direct harness)\n\nPrompt: {prompt}\n")
    pipeline_trace.write_step(trace_dir, "step2-context", {
        "status": "skipped_direct_test_harness",
        "mode_name": mode_name,
        "gear": gear,
        "mode_text_chars": len(mode_text),
        "rag_skipped": True,
    }, markdown=(
        f"# Step 2 — skipped (direct harness)\n\n"
        f"Mode: `{mode_name}` ({len(mode_text)} chars)  \n"
        f"Gear: {gear} (forced)  \n"
        f"RAG: skipped — direct harness uses empty RAG to test the gear "
        f"pipeline in isolation.\n"
    ))

    print(f"[direct] gear={gear} mode={mode_name}")
    print(f"[direct] trace_dir: {trace_dir}\n")

    t0 = time.time()
    try:
        if gear == 3:
            response = run_gear3(context_pkg, config, history=None)
        else:
            response = run_gear4(context_pkg, config, history=None)
    except Exception as e:
        response = f"[direct test exception: {e}]"
    elapsed = time.time() - t0

    print(f"[direct] elapsed: {elapsed:.1f}s")
    if trace_dir and os.path.isdir(trace_dir):
        files = sorted(os.listdir(trace_dir))
        print(f"[direct] trace files ({len(files)}):")
        for f in files:
            size = os.path.getsize(os.path.join(trace_dir, f))
            print(f"  - {f} ({size}B)")
    print(f"\n[direct] response first 600 chars:\n{(response or '')[:600]}\n---")


if __name__ == "__main__":
    main()
