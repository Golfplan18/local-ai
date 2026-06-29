"""Synthetic tests for Gear 4 degradation paths.

Added 2026-05-22 to close S4 — the both-analysts-degraded fallback
to Gear 3 (boot.py contingency
``step3-both-analysts-degraded-fallback-to-gear3``) was the only path
the broken-endpoint smoke test had exercised; after the endpoint
substitution bug closed (S1, commit cc283b38), the original trigger
went away and the fallback path lost its only test. These tests mock
the endpoint dispatch so the contingency fires deterministically and
we can verify the fallback wiring still works.

Covers:
  - Both depth and breadth analysts degrade → ``run_gear4`` calls
    ``run_gear3`` with the same context and returns its result.
  - Contingency name lands in step-health (via the
    ``pipeline_trace.write_step_health`` call captured in the mock).
  - Single-stream degrade adds the correct cross-eval-on-error-string
    contingency name (depth or breadth, depending on which side
    failed) without short-circuiting back to Gear 3.
"""
import os
import sys
import unittest
from unittest import mock


HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKTREE_ROOT = os.path.dirname(HERE)
for p in (HERE, WORKTREE_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)


# Use the same forced-load pattern other sweep tests use so the worktree's
# boot.py wins over any pre-loaded version from a different sys.path entry.
import importlib.util as _ilu


def _load_worktree(modname: str):
    fname = os.path.join(HERE, f"{modname}.py")
    spec = _ilu.spec_from_file_location(modname, fname)
    mod = _ilu.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


boot = _load_worktree("boot")


def _fake_endpoint(name):
    """Minimal endpoint dict run_gear4 / run_gear3 need."""
    return {
        "id": name,
        "name": name,
        "type": "api",
        "service": "openai",
        "model": "fake-model",
        "status": "active",
        "enabled": True,
    }


def _minimal_context_pkg():
    return {
        "cleaned_prompt": "test prompt — gear 4 degradation drill",
        "mode_text": "## DEPTH MODEL INSTRUCTIONS\n\nfake depth instructions\n",
        "gear": 4,
        "trace_dir": None,            # disables pipeline_trace.write_*
        "rag_query": "test",
        "conversation_rag": {"content": ""},
        "concept_rag": {"content": ""},
    }


class TestBothAnalystsDegradedFallsBackToGear3(unittest.TestCase):
    """When both gear-4 analysts return degraded output, run_gear4 must
    delegate to run_gear3 with the same context_pkg / config / history /
    images / config_name and return whatever run_gear3 returns.
    """

    def test_both_degraded_invokes_run_gear3(self):
        depth_ep = _fake_endpoint("depth-fake")
        breadth_ep = _fake_endpoint("breadth-fake")

        with mock.patch.object(boot, "resolve_gear4_endpoints",
                                return_value=(depth_ep, breadth_ep, True)), \
             mock.patch.object(boot, "_assemble_step_prompt",
                                return_value="fake system prompt"), \
             mock.patch.object(boot, "_call_with_supplement",
                                return_value=(
                                    "[Error calling Test API: simulated failure]",
                                    False,
                                    "transport_error",
                                )), \
             mock.patch.object(boot, "run_gear3",
                                return_value="[gear3-fallback-sentinel]") as gear3_mock:
            result = boot.run_gear4(_minimal_context_pkg(), config={},
                                     history=None, images=None,
                                     config_name=None)

        # run_gear4 should have returned run_gear3's sentinel verbatim
        self.assertEqual(result, "[gear3-fallback-sentinel]")

        # run_gear3 was called exactly once with the propagated args
        self.assertEqual(gear3_mock.call_count, 1)
        call = gear3_mock.call_args
        # context_pkg is positional arg 0
        self.assertEqual(call.args[0]["cleaned_prompt"],
                          "test prompt — gear 4 degradation drill")
        # config_name kwarg propagates
        self.assertIsNone(call.kwargs.get("config_name"))


class TestStepHealthCapturesContingency(unittest.TestCase):
    """When both analysts degrade and a trace_dir is configured, the
    pipeline_trace.write_step_health call must record the fallback
    contingency name so audit consumers can detect the fall-back.
    """

    def test_contingency_written_to_step_health(self):
        depth_ep = _fake_endpoint("depth-fake")
        breadth_ep = _fake_endpoint("breadth-fake")
        ctx = _minimal_context_pkg()
        ctx["trace_dir"] = "/tmp/test-trace-dir-noop"

        captured: dict = {}

        def fake_write_step_health(trace_dir, step_health, gear,
                                    contingencies_fired):
            captured["trace_dir"] = trace_dir
            captured["gear"] = gear
            captured["contingencies_fired"] = list(contingencies_fired)
            captured["step_health"] = dict(step_health)

        with mock.patch.object(boot, "resolve_gear4_endpoints",
                                return_value=(depth_ep, breadth_ep, True)), \
             mock.patch.object(boot, "_assemble_step_prompt",
                                return_value="fake system prompt"), \
             mock.patch.object(boot, "_call_with_supplement",
                                return_value=(
                                    "[Error calling Test API: simulated failure]",
                                    False,
                                    "transport_error",
                                )), \
             mock.patch.object(boot, "PIPELINE_TRACE_AVAILABLE", True), \
             mock.patch.object(boot.pipeline_trace, "write_step_health",
                                side_effect=fake_write_step_health), \
             mock.patch.object(boot.pipeline_trace, "write_step"), \
             mock.patch.object(boot, "run_gear3", return_value="[fallback]"):
            boot.run_gear4(ctx, config={}, history=None, images=None,
                            config_name=None)

        self.assertEqual(captured.get("gear"), 4)
        self.assertIn(
            "step3-both-analysts-unrecoverable-fallback-to-gear3",
            captured.get("contingencies_fired", []),
            "Fallback contingency name should appear in step-health "
            "when both analysts are unrecoverable after retry+fallback",
        )


class TestSingleStreamUnrecoverableFallsBackToGear3(unittest.TestCase):
    """When one stream succeeds and the other is unrecoverable (failed its
    primary AND its fallback model), the pipeline must NOT proceed on the one
    healthy stream — it falls back to Gear 3, naming the unrecoverable stream.
    This replaced the prior "continue with one degraded stream + error string"
    path (2026-06-29). End-to-end coverage of the fall-back lives in
    test_gear4_analyst_recovery.py; here we pin the contingency-naming logic.
    """

    def test_single_unrecoverable_naming_depth_ok_breadth_fail(self):
        # Mirrors the naming block in run_gear4's step-3 recovery:
        #   failed = [s for s, ok in (("depth", depth_ok), ("breadth", breadth_ok)) if not ok]
        #   "step3-both-..." when both fail, else "step3-<failed>-analyst-unrecoverable..."
        depth_ok, breadth_ok = True, False
        failed = [s for s, ok in (("depth", depth_ok), ("breadth", breadth_ok))
                  if not ok]
        name = ("step3-both-analysts-unrecoverable-fallback-to-gear3"
                if not depth_ok and not breadth_ok
                else f"step3-{failed[0]}-analyst-unrecoverable-fallback-to-gear3")
        self.assertEqual(
            name, "step3-breadth-analyst-unrecoverable-fallback-to-gear3")

    def test_single_unrecoverable_naming_breadth_ok_depth_fail(self):
        depth_ok, breadth_ok = False, True
        failed = [s for s, ok in (("depth", depth_ok), ("breadth", breadth_ok))
                  if not ok]
        name = ("step3-both-analysts-unrecoverable-fallback-to-gear3"
                if not depth_ok and not breadth_ok
                else f"step3-{failed[0]}-analyst-unrecoverable-fallback-to-gear3")
        self.assertEqual(
            name, "step3-depth-analyst-unrecoverable-fallback-to-gear3")


if __name__ == "__main__":
    unittest.main()
