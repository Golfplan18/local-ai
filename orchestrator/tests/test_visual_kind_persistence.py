"""Real-path regression test for the visual_kind threading drop point.

Bug: a campaign ``fishbone-diagram`` run (mode ``root-cause-analysis``,
``manual_visual_type='fishbone'``) intermittently shipped the SIBLING kind
``causal_loop_diagram``. Root cause: when the threaded ``visual_kind`` was
absent from ``context_pkg`` at synthesis time, ``_maybe_synthesize_visual``
fell back to the mode's full target list ``['fishbone','causal_loop_diagram']``
(2 elements); fishbone exhausted its repair rounds on a weak model and
synthesis ADVANCED to ``causal_loop_diagram`` and shipped it.

The one residual code-level drop point on the real call graph was
``boot.run_pipeline`` (the CLI / Router / run_agentic_loop fallback): it had no
``extra_context`` parameter and never merged ``visual_kind`` onto the context
package, so its tail ``_run_visual_hook`` always saw ``visual_kind`` absent.

These tests drive the REAL ``boot.run_pipeline`` end-to-end — through the REAL
``_run_visual_hook`` → REAL ``_maybe_synthesize_visual`` → REAL
``_mode_target_types`` → REAL ``synthesize_envelope`` — and capture the ACTUAL
``target_types`` the real synthesizer receives. The ONLY things stubbed are the
model transport (no live endpoint in CI) and the gear executor (it produces the
analyst prose and does not touch ``visual_kind``, so stubbing it cannot mask
the bug, which lives in the post-gear hook's target-kind decision). Nothing in
the visual_kind→target_types→synthesis path is mocked.

We assert, on the REAL threading:
  (a) fishbone-diagram → the real synthesizer is handed ``['fishbone']`` only;
      the sibling ``causal_loop_diagram`` is NEVER attempted, and the shipped
      envelope type is ``fishbone``;
  (b) other multi-kind modes still honor their threaded kind (a non-first
      member is targeted single, not the mode default);
  (c) single-kind modes are unaffected (the threaded kind == the lone native
      kind → single target), and a mode with NO threaded kind keeps its full
      default list (no regression to the recovery/no-visual behaviour).
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = os.path.dirname(HERE)
ROOT = os.path.dirname(ORCH)
for p in (ORCH, ROOT, os.path.join(ROOT, "server")):
    if p not in sys.path:
        sys.path.insert(0, p)

# Tracing off so the test never writes into data/ ; synthesis is gated to
# interactive context, which run_pipeline defaults to.
os.environ.setdefault("ORA_PIPELINE_TRACE", "off")

import boot  # noqa: E402


# --- A faithful, deterministic stand-in for the synthesis model call. -------
# It records the ``type`` requested in each synthesis prompt (the real
# _build_prompt embeds ``of type `<vtype>``` ), and returns a minimal valid
# envelope of THAT kind. This lets the REAL synthesize_envelope / autofill /
# validator / adversarial loop run unmodified; we observe which kinds the real
# code actually attempts.
_REQUESTED_KINDS: list[str] = []


def _envelope_for(vtype: str) -> dict:
    """A schema-shaped envelope the real validator accepts for ``vtype``.

    We load the known-good example fixture the synthesizer itself anchors on
    (config/visual-schemas/examples/<vtype>.valid.json) so the returned object
    is a real, valid envelope of the requested kind — no hand-rolled shape that
    could drift from the schema.
    """
    from visual_synthesis import _load_example
    ex = _load_example(vtype)
    if ex is None:
        # Fall back to a tiny shell; autofill + repair_spec will fill the rest.
        return {"type": vtype, "title": f"test {vtype}"}
    return dict(ex)


def _make_synthesis_stub(answer_kind_for):
    """Return a call_model stub.

    ``answer_kind_for(requested_vtype) -> kind_to_emit`` controls what kind the
    'model' actually emits for a given requested kind, so we can simulate a
    weak model that FAILS the requested kind (emitting a structurally-wrong
    object) and would, under the old behaviour, let synthesis advance to a
    sibling.
    """
    def _stub(messages, endpoint, images=None):
        user = ""
        for m in messages:
            if m.get("role") == "user":
                user = m.get("content") or ""
        # The real _build_prompt embeds: of type `<vtype>`.
        import re
        mobj = re.search(r"of type `([a-z0-9_]+)`", user)
        requested = mobj.group(1) if mobj else "unknown"
        _REQUESTED_KINDS.append(requested)
        emit_kind = answer_kind_for(requested)
        if emit_kind is None:
            # Emit garbage so this requested kind FAILS every repair round —
            # this is what forces the OLD code to advance to a sibling.
            return "not json at all"
        return json.dumps(_envelope_for(emit_kind))
    return _stub


def _run(mode, prompt, visual_kind, answer_kind_for, monkeypatch_targets):
    """Drive the REAL run_pipeline; force the synthesis path; capture targets.

    Returns (shipped_response_text, requested_kinds, captured_target_types).
    """
    _REQUESTED_KINDS.clear()
    captured = {}

    # Build a step1 the real Step-2 contract expects, but skip the heavy RAG
    # Step-2 by returning a minimal real context_pkg. context_pkg carries
    # exactly the fields run_pipeline / the hook read. The merge under test is
    # run_pipeline's own (extra_context -> context_pkg), so we let it run.
    def _fake_step1(user_input, conv_context, config, **kw):
        return {"mode": mode, "triage_tier": 1,
                "cleaned_prompt": user_input, "operational_notation": user_input,
                "raw_prompt": user_input, "pre_routing": {}}

    def _fake_step2(step1_result, config, trace_dir=None, config_name=None):
        # The real context package fields the gear + hook consume. gear=4 so
        # run_pipeline dispatches through the gear-4 branch, exactly like a
        # campaign root-cause-analysis run. NO visual_kind here — the whole
        # point is that run_pipeline's extra_context merge must add it.
        return {"mode_name": mode, "cleaned_prompt": step1_result["cleaned_prompt"],
                "gear": 4, "territory": None}

    # Gear executor returns analyst prose with NO recoverable diagram, so the
    # recovery phase (Phase 1a) finds nothing and the SYNTHESIS phase (Phase
    # 1b) — the buggy one — runs. The prose deliberately contains zero
    # ```mermaid``` / ```ora-visual``` / DSL blocks.
    PROSE = ("Deployment failures recur every release. Contributing factors "
             "span people, process, technology, data, and environment. "
             "Hand-offs are unclear, tests are skipped under deadline pressure, "
             "the release tooling is brittle, telemetry is sparse, and staging "
             "diverges from production. These root causes compound each release.")

    def _fake_gear4(context_pkg, config, history=None, images=None,
                    execution_context="interactive", config_name=None):
        return PROSE

    def _fake_gear3(context_pkg, config, history=None, images=None,
                    config_name=None):
        return PROSE

    # Provide a non-None synthesis endpoint so _maybe_synthesize_visual proceeds
    # (the test never reaches a real network — call_model is stubbed).
    def _fake_resolve_endpoint(config_name=None):
        return {"name": "test-endpoint", "id": "test-endpoint"}

    # Wrap the REAL synthesize_envelope to capture the exact target_types the
    # real hook hands it. We call straight through to the real implementation —
    # only observing, not replacing, the decision under test.
    import visual_synthesis as _vs
    _real_synth = _vs.synthesize_envelope

    def _capturing_synth(prose, mode_arg, target_types, call_fn, idx=1):
        captured["target_types"] = list(target_types)
        return _real_synth(prose, mode_arg, target_types, call_fn, idx=idx)

    saved = {}

    def _set(modname, attr, val):
        mod = sys.modules[modname]
        saved[(modname, attr)] = getattr(mod, attr)
        setattr(mod, attr, val)

    try:
        _set("boot", "run_step1_cleanup", _fake_step1)
        _set("boot", "run_step2_context_assembly", _fake_step2)
        _set("boot", "run_gear4", _fake_gear4)
        _set("boot", "run_gear3", _fake_gear3)
        _set("boot", "_resolve_synthesis_endpoint", _fake_resolve_endpoint)
        _set("boot", "call_model", _make_synthesis_stub(answer_kind_for))
        # route_output is the tail; keep it from touching disk/screen oddly.
        _set("boot", "route_output", lambda resp, target, ctx: resp)
        # Capture target_types inside the real synthesizer, in BOTH the module
        # boot imports it from and any alias boot already bound.
        _vs.synthesize_envelope = _capturing_synth
        saved[("visual_synthesis", "synthesize_envelope")] = _real_synth

        extra = {"visual_kind": visual_kind} if visual_kind else None
        resp = boot.run_pipeline(prompt, history=[], output_target="screen",
                                 extra_context=extra)
    finally:
        for (modname, attr), val in saved.items():
            setattr(sys.modules[modname], attr, val)

    return resp, list(_REQUESTED_KINDS), captured.get("target_types")


def _shipped_type(resp):
    """Extract the ora-visual envelope type spliced into the response, if any."""
    import re
    m = re.search(r"```ora-visual\s*\n(.*?)\n```", resp or "", re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1)).get("type")
    except Exception:
        return None


# ── (a) The campaign trigger: fishbone-diagram must NEVER ship the sibling ──

def test_fishbone_threaded_kind_survives_no_sibling_attempt():
    """REAL path: visual_kind='fishbone' on root-cause-analysis →
    synthesizer is handed ['fishbone'] only; causal_loop_diagram is never
    attempted even when fishbone is hard (here the model succeeds round 1)."""
    resp, requested, target_types = _run(
        mode="root-cause-analysis",
        prompt="Why do our deployment failures recur every release? "
               "Draw a fishbone diagram.",
        visual_kind="fishbone",
        answer_kind_for=lambda req: "fishbone",  # honest model
        monkeypatch_targets=None,
    )
    assert target_types == ["fishbone"], (
        f"real synthesizer got {target_types!r}; expected single ['fishbone'] "
        f"(sibling must never be in the target list)")
    assert "causal_loop_diagram" not in requested, (
        f"sibling was attempted: requested kinds = {requested!r}")
    assert _shipped_type(resp) == "fishbone", (
        f"shipped envelope type = {_shipped_type(resp)!r}, expected fishbone")


def test_fishbone_hard_model_fails_to_no_visual_never_sibling():
    """The decisive case: a model that CANNOT produce a valid fishbone must
    yield NO visual — never the sibling. Under the old 2-element target list a
    failed fishbone advanced to causal_loop_diagram; with the kind threaded the
    target list is single, so a fishbone failure is terminal (no sibling)."""
    resp, requested, target_types = _run(
        mode="root-cause-analysis",
        prompt="Why do our deployment failures recur every release?",
        visual_kind="fishbone",
        # Model fails fishbone every round (emits garbage); if the target list
        # had a sibling, synthesis would advance and the stub would be asked
        # for 'causal_loop_diagram'. It must NOT be.
        answer_kind_for=lambda req: None,
        monkeypatch_targets=None,
    )
    assert target_types == ["fishbone"], (
        f"real synthesizer got {target_types!r}; expected ['fishbone']")
    assert set(requested) == {"fishbone"}, (
        f"a non-fishbone kind was attempted: {requested!r} — the sibling leaked")
    assert "causal_loop_diagram" not in requested
    assert _shipped_type(resp) in (None, "fishbone"), (
        f"on fishbone failure the shipped type must be no-visual or fishbone, "
        f"got {_shipped_type(resp)!r}")


# ── (b) Other multi-kind modes still honor their threaded kind ──────────────

def test_multikind_mode_honors_threaded_nonfirst_kind():
    """decision-under-uncertainty natively lists
    ['decision_tree','influence_diagram','tornado']. Threading 'tornado'
    (a NON-first member) must target ['tornado'] alone — proof the threading
    works generally, not just for fishbone, and that the kind beats the
    mode-default ordering."""
    resp, requested, target_types = _run(
        mode="decision-under-uncertainty",
        prompt="Lay out the decision under uncertainty with a tornado of the "
               "biggest sensitivities.",
        visual_kind="tornado",
        answer_kind_for=lambda req: "tornado",
        monkeypatch_targets=None,
    )
    assert target_types == ["tornado"], (
        f"real synthesizer got {target_types!r}; expected ['tornado']")
    assert "decision_tree" not in requested and "influence_diagram" not in requested, (
        f"a sibling of the multi-kind mode was attempted: {requested!r}")
    assert _shipped_type(resp) == "tornado"


# ── (c) Single-kind modes / no-threaded-kind: no regression ─────────────────

def test_single_kind_mode_unaffected():
    """competing-hypotheses natively lists ['ach_matrix']. Threading the same
    kind keeps a single target (the threaded kind == the lone native kind);
    nothing else is attempted."""
    resp, requested, target_types = _run(
        mode="competing-hypotheses",
        prompt="Build an ACH matrix for the three hypotheses.",
        visual_kind="ach_matrix",
        answer_kind_for=lambda req: "ach_matrix",
        monkeypatch_targets=None,
    )
    assert target_types == ["ach_matrix"], (
        f"real synthesizer got {target_types!r}; expected ['ach_matrix']")
    assert set(requested) <= {"ach_matrix"}
    assert _shipped_type(resp) == "ach_matrix"


def test_no_threaded_kind_keeps_full_mode_default():
    """When NO kind is threaded (extra_context is None — e.g. a non-campaign
    interactive turn), the mode's full default list is preserved. This guards
    the fix from over-reaching: multi-kind graceful degradation still works
    when the user did not pin a kind. root-cause-analysis with no threaded kind
    must still offer ['fishbone','causal_loop_diagram'] so a fishbone miss can
    fall back to the sibling — the LEGAL multi-kind behaviour."""
    resp, requested, target_types = _run(
        mode="root-cause-analysis",
        prompt="Why do our deployment failures recur every release?",
        visual_kind=None,  # no thread → no extra_context merge
        answer_kind_for=lambda req: "fishbone",  # succeeds first kind
        monkeypatch_targets=None,
    )
    assert target_types == ["fishbone", "causal_loop_diagram"], (
        f"with no threaded kind, expected the full default list, got "
        f"{target_types!r}")
    # First kind succeeds, so only fishbone is attempted, but the LIST offered
    # to the synthesizer must retain the sibling for graceful degradation.
    assert _shipped_type(resp) == "fishbone"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failures = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            import traceback
            print(f"ERROR {fn.__name__}: {e}")
            traceback.print_exc()
    print(f"\n{len(fns) - failures}/{len(fns)} passed")
    sys.exit(1 if failures else 0)
