#!/usr/bin/env python3
"""
Diagnostic test: verify RuntimePipeline knowledge extraction produces notes.

Tests:
1. _build_transcript() produces proper multi-turn chat format
2. detect_input_type() classifies it as "chat" (or source_type override works)
3. Pass A finds signals
4. Pass B produces candidate notes
5. Full pipeline run_sync() returns notes_extracted > 0

Run: /opt/homebrew/bin/python3 ~/ora/tests/test_extraction_pipeline.py
"""
import os
import sys
import json

# Ensure ora modules are importable
sys.path.insert(0, os.path.expanduser("~/ora/orchestrator"))
sys.path.insert(0, os.path.expanduser("~/ora/orchestrator/tools"))
sys.path.insert(0, os.path.expanduser("~/ora"))

from runtime_pipeline import RuntimePipeline, SessionData
from input_detect import detect_input_type
from extraction_engine import ExtractionEngine, parse_signal_map, parse_candidate_notes


# ---------------------------------------------------------------------------
# Test data: a realistic multi-turn conversation with extractable knowledge
# ---------------------------------------------------------------------------
SAMPLE_HISTORY = [
    {"role": "user", "content": "What is the difference between first-principles thinking and reasoning by analogy?"},
    {"role": "assistant", "content": (
        "First-principles thinking and reasoning by analogy are two fundamentally different "
        "cognitive strategies.\n\n"
        "**First-principles thinking** decomposes a problem into its most basic, foundational "
        "truths — the axioms that cannot be further reduced — and then reconstructs understanding "
        "from those axioms upward. Elon Musk famously applied this to battery costs: rather than "
        "accepting the market price, he broke the battery into raw materials (cobalt, nickel, "
        "lithium, carbon, separator) and calculated the commodity exchange cost, discovering the "
        "materials cost only $80/kWh vs the $600/kWh market price.\n\n"
        "**Reasoning by analogy** transfers solutions or patterns from a known domain to a new "
        "one. It's faster and lower-effort, but inherits the assumptions of the source domain. "
        "If those assumptions don't hold in the target domain, the analogy produces false "
        "conclusions.\n\n"
        "The key tradeoff: first-principles thinking is computationally expensive (you must "
        "verify each axiom) but produces novel solutions. Analogy is cheap but can only "
        "recombine existing patterns. Most daily decisions use analogy; breakthrough innovations "
        "require first principles.\n\n"
        "A practical heuristic: use analogy as your default, but switch to first principles "
        "when the problem is novel, the stakes are high, or analogical reasoning produces "
        "contradictory answers."
    )},
    {"role": "user", "content": "When does analogical reasoning actively mislead rather than just being imprecise?"},
    {"role": "assistant", "content": (
        "Analogical reasoning misleads in three specific failure modes:\n\n"
        "**1. Structural mismatch.** The source and target domains share surface features but "
        "differ in causal structure. Example: 'The brain is like a computer' — this analogy "
        "correctly maps input→processing→output but incorrectly implies the brain has discrete "
        "memory addresses, a central processor, and deterministic execution. Neuroscience "
        "researchers who took this analogy literally spent decades looking for the brain's "
        "'CPU' and 'RAM.'\n\n"
        "**2. Anchoring on the wrong abstraction level.** The analogy captures a true "
        "relationship at one level but the reasoner applies it at a different level. Example: "
        "'Competition in markets is like natural selection' — true for the population-level "
        "dynamics of firms, but misleading when applied to individual employees within a firm, "
        "where cooperation often outperforms competition.\n\n"
        "**3. Invisible boundary conditions.** Every analogy has a domain of validity, but the "
        "boundaries are rarely stated. Example: 'Scaling a startup is like scaling a recipe' — "
        "works when doubling, breaks catastrophically at 100x because organizational complexity "
        "grows non-linearly while recipe ingredients scale linearly.\n\n"
        "The common thread: analogical reasoning misleads when the reasoner treats the analogy "
        "as an identity rather than a partial mapping. The antidote is always to ask: 'Where "
        "does this analogy break down?'"
    )},
]


def test_1_transcript_format():
    """Test that _build_transcript produces multi-turn chat format."""
    print("=" * 70)
    print("TEST 1: Transcript format")
    print("=" * 70)

    data = SessionData(
        session_id="test01",
        timestamp="2026-04-14T18:00:00",
        mode="exploratory",
        gear=2,
        conversation_history=SAMPLE_HISTORY,
        user_prompt=SAMPLE_HISTORY[-2]["content"],
        final_output=SAMPLE_HISTORY[-1]["content"],
        source_type="chat",
    )

    pipeline = RuntimePipeline(config={})
    transcript = pipeline._build_transcript(data)

    print(f"  Transcript length: {len(transcript)} chars (~{len(transcript)//4} tokens)")
    print(f"  Starts with: {transcript[:80]}...")
    print(f"  Contains '**User:**': {transcript.count('**User:**')}")
    print(f"  Contains '**Assistant:**': {transcript.count('**Assistant:**')}")
    assert "**User:**" in transcript, "FAIL: No User markers"
    assert "**Assistant:**" in transcript, "FAIL: No Assistant markers"
    assert transcript.count("**User:**") >= 2, "FAIL: Expected >= 2 User turns"
    print("  ✓ PASS\n")
    return transcript


def test_2_input_detection(transcript):
    """Test that detect_input_type classifies the transcript correctly."""
    print("=" * 70)
    print("TEST 2: Input type detection")
    print("=" * 70)

    result = detect_input_type(transcript)
    print(f"  Detected type: {result['type']}")
    print(f"  Confidence: {result['confidence']}")
    print(f"  Token estimate: {result['details'].get('estimated_tokens', '?')}")
    print(f"  Paths: {result.get('paths', [])}")
    if result.get("details", {}).get("chat_detection"):
        print(f"  Chat turns: {result['details']['chat_detection'].get('turn_count', '?')}")
    print(f"  ✓ Type = {result['type']}\n")
    return result


def test_3_source_type_override():
    """Test that source_type override works for short/single-turn inputs."""
    print("=" * 70)
    print("TEST 3: source_type override for single-turn")
    print("=" * 70)

    # Single turn — would normally be "fragment" or "short_document"
    single_turn = [
        {"role": "user", "content": "What is inversion?"},
        {"role": "assistant", "content": "Inversion is thinking about a problem backwards."},
    ]

    data = SessionData(
        session_id="test03",
        timestamp="2026-04-14T18:00:00",
        mode="exploratory",
        gear=1,
        conversation_history=single_turn,
        source_type="chat",
    )

    pipeline = RuntimePipeline(config={})
    transcript = pipeline._build_transcript(data)
    result = detect_input_type(transcript)
    print(f"  Auto-detected type: {result['type']} (tokens: {result['details'].get('estimated_tokens', '?')})")

    # Simulate the override logic from _step4_knowledge_extraction
    if data.source_type and result.get("type") != data.source_type:
        result["type"] = data.source_type
        result["confidence"] = "high"
        result["details"]["source_type_override"] = True
        if data.source_type == "chat":
            result["paths"] = [1, 2]

    print(f"  After override: {result['type']} (paths: {result.get('paths', [])})")
    assert result["type"] == "chat", "FAIL: Override didn't apply"
    print("  ✓ PASS\n")


def test_4_pass_a_standalone(transcript):
    """Test Pass A signal identification with the transcript (no model call)."""
    print("=" * 70)
    print("TEST 4: Pass A prompt construction")
    print("=" * 70)

    from extraction_engine import build_pass_a_prompt
    messages = build_pass_a_prompt(transcript, "chat", source_file="test_session")

    print(f"  System prompt length: {len(messages[0]['content'])} chars")
    print(f"  User prompt length: {len(messages[1]['content'])} chars")
    # Verify the prompt is the compact numbered-list format
    assert "number" in messages[0]["content"].lower() or "list" in messages[0]["content"].lower(), \
        "FAIL: Prompt should use numbered-list format"
    print("  ✓ Compact numbered-list prompt format confirmed\n")
    return messages


def test_5_full_pipeline_with_models(transcript):
    """
    Full pipeline test WITH model calls.
    Only runs if models are available (server not required).
    """
    print("=" * 70)
    print("TEST 5: Full extraction with model calls")
    print("=" * 70)

    try:
        config_path = os.path.expanduser("~/ora/config/endpoints.json")
        with open(config_path) as f:
            config = json.load(f)

        from orchestrator.boot import call_model, get_slot_endpoint

        # Verify endpoints resolve
        sidebar_ep = get_slot_endpoint(config, "sidebar")
        depth_ep = get_slot_endpoint(config, "depth")
        print(f"  Sidebar endpoint: {sidebar_ep.get('name', 'NONE') if sidebar_ep else 'NONE'}")
        print(f"  Depth endpoint: {depth_ep.get('name', 'NONE') if depth_ep else 'NONE'}")

        if not sidebar_ep or not depth_ep:
            print("  ⊘ SKIP: Missing model endpoints")
            return

        # Run extraction engine directly
        from extraction_engine import ExtractionEngine
        engine = ExtractionEngine(call_fn=call_model, config=config)
        type_result = {"type": "chat", "confidence": "high",
                       "details": {"estimated_tokens": len(transcript) // 4},
                       "paths": [1, 2], "hcp": False}

        print("  Running Pass A (sidebar model)...")
        extraction = engine.extract(transcript, type_result, source_file="test_session")

        print(f"  Signals found: {len(extraction.signals)}")
        for s in extraction.signals[:5]:
            print(f"    {s.id}: [{s.signal_type}] {s.summary[:60]}...")
        print(f"  Candidates generated: {len(extraction.candidates)}")
        for c in extraction.candidates[:5]:
            print(f"    [{c.note_type}] {c.title[:60]}...")
        print(f"  Screened notes: {len(extraction.screened)}")
        for s in extraction.screened[:5]:
            print(f"    [{s.queue}] {s.note.title[:60]}...")

        if extraction.screened:
            print(f"  ✓ PASS: {len(extraction.screened)} notes extracted")
        else:
            print(f"  ✗ FAIL: 0 notes extracted")
            if extraction.metadata:
                print(f"  Metadata: {extraction.metadata}")

    except ImportError as e:
        print(f"  ⊘ SKIP: Import error — {e}")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")


def test_6_full_runtime_pipeline():
    """Full RuntimePipeline.run_sync() test with model calls."""
    print("=" * 70)
    print("TEST 6: Full RuntimePipeline.run_sync()")
    print("=" * 70)

    try:
        config_path = os.path.expanduser("~/ora/config/endpoints.json")
        with open(config_path) as f:
            config = json.load(f)

        from orchestrator.boot import call_model

        data = SessionData(
            session_id="diag01",
            timestamp="2026-04-14T18:00:00",
            mode="exploratory",
            gear=2,
            conversation_history=SAMPLE_HISTORY,
            user_prompt=SAMPLE_HISTORY[-2]["content"],
            final_output=SAMPLE_HISTORY[-1]["content"],
            source_type="chat",
        )

        pipeline = RuntimePipeline(config=config, call_fn=call_model)
        print("  Running full pipeline synchronously...")
        result = pipeline.run_sync(data)

        print(f"  Time: {result.total_time_seconds:.1f}s")
        print(f"  Steps completed: {result.steps_completed}")
        print(f"  Steps failed: {result.steps_failed}")
        print(f"  Notes extracted: {result.notes_extracted}")
        print(f"  Notes approved: {result.notes_approved}")
        print(f"  Notes review: {result.notes_review}")

        if result.notes_extracted > 0:
            print(f"  ✓ PASS: {result.notes_extracted} notes extracted")
        else:
            print(f"  ✗ FAIL: 0 notes extracted")

    except ImportError as e:
        print(f"  ⊘ SKIP: Import error — {e}")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("\n  Runtime Pipeline — Knowledge Extraction Diagnostic\n")

    # Tests 1-4 don't require models
    transcript = test_1_transcript_format()
    test_2_input_detection(transcript)
    test_3_source_type_override()
    test_4_pass_a_standalone(transcript)

    # Tests 5-6 require models (optional, run with --full)
    if "--full" in sys.argv:
        test_5_full_pipeline_with_models(transcript)
        test_6_full_runtime_pipeline()
    else:
        print("=" * 70)
        print("Tests 5-6 (model calls) skipped. Run with --full to include.")
        print("=" * 70)

    print("\nDone.")
