"""Gear 4 analyst recovery: retry the primary model, then the fallback model,
then fall back to Gear 3 — never proceed on one model + an error string.

Two layers:
  * Primitive — `_call_with_retry` retries the SAME model when gear is omitted,
    even when slot metadata is retained, and advances to the fallback model
    when both slot and gear are passed. This is the building block
    `_analyst_stream` relies on for "primary retry, then fallback".
  * Orchestration — `run_gear4`'s step-3 recovery: a stream that fails its
    primary tries the fallback model; a stream that fails BOTH is unrecoverable
    and the pipeline falls back to Gear 3 rather than cross-evaluating on one
    real stream + an error string.
"""

from __future__ import annotations

import contextlib
import sys
import unittest
from pathlib import Path
from unittest import mock

ORCH_DIR = Path(__file__).resolve().parent.parent
if str(ORCH_DIR) not in sys.path:
    sys.path.insert(0, str(ORCH_DIR))

import boot  # noqa: E402

DUMMY_EP = {"id": "ep", "name": "ep", "type": "remote"}
DEPTH_EP = {"id": "depth-primary", "name": "depth-primary", "type": "remote"}
BREADTH_EP = {"id": "breadth-primary", "name": "breadth-primary", "type": "remote"}
GEAR3_SENTINEL = "GEAR3-FALLBACK"


# ───────────────────────── primitive: retry semantics ───────────────────────


class TestRetrySameVsFallback(unittest.TestCase):
    """`_analyst_stream` gets its 'retry primary, then fallback' ordering by
    calling the helper with slot retained but gear omitted (same-model retry)
    and then advancing the endpoint itself. Pin both halves of that contract."""

    def _fail_then_ok(self, seen, metadata=None):
        def fake_model(messages, endpoint, images=None):
            seen.append(endpoint["name"])
            if metadata is not None:
                metadata.append(dict(boot._CALL_METADATA_CV.get() or {}))
            return "short" if len(seen) == 1 else ("substantive output " * 20)
        return fake_model

    def test_slot_set_with_gear_none_retries_the_same_model(self):
        seen = []
        metadata = []
        with mock.patch.object(boot, "_run_model_with_tools",
                               side_effect=self._fail_then_ok(seen, metadata)), \
             mock.patch.object(boot, "_resolve_fallback_endpoint") as resolve:
            text, ok, _ = boot._call_with_retry(
                [{"role": "user", "content": "x"}], dict(DEPTH_EP), "analyst",
                slot="depth", gear=None)
        self.assertEqual(seen, ["depth-primary", "depth-primary"])  # same model
        self.assertEqual(
            [(m["step"], m["slot"], m["gear"]) for m in metadata],
            [("analyst", "depth", None), ("analyst:retry", "depth", None)],
        )
        resolve.assert_not_called()
        self.assertTrue(ok)

    def test_slot_set_advances_to_fallback_on_retry(self):
        seen = []
        fb = {"id": "depth-fallback", "name": "depth-fallback", "type": "remote"}
        with mock.patch.object(boot, "_run_model_with_tools",
                               side_effect=self._fail_then_ok(seen)), \
             mock.patch.object(boot, "_resolve_fallback_endpoint", return_value=fb):
            text, ok, _ = boot._call_with_retry(
                [{"role": "user", "content": "x"}], dict(DEPTH_EP), "analyst",
                slot="depth", gear=4)
        self.assertEqual(seen, ["depth-primary", "depth-fallback"])  # advanced
        self.assertTrue(ok)


# ───────────────────────── orchestration harness ────────────────────────────


class _Harness:
    """`health` maps an analyst endpoint name -> healthy bool. Unlisted
    endpoints are healthy. Non-analyst steps are always healthy (verifier and
    quality-gate return VERDICT: PASS so the pipeline runs to completion)."""

    def __init__(self, health):
        self.health = health
        self.calls = []  # (step_name, endpoint_name)
        self.supp_calls = []  # call metadata passed to _call_with_supplement

    def _name(self, endpoint):
        return endpoint.get("name") if isinstance(endpoint, dict) else str(endpoint)

    def supp(self, messages, endpoint, step_name, *a, **k):
        name = self._name(endpoint)
        self.calls.append((step_name, name))
        self.supp_calls.append({
            "step": step_name,
            "endpoint": name,
            "slot": k.get("slot"),
            "gear": k.get("gear"),
        })
        if step_name == "analyst":
            ok = self.health.get(name, True)
            return ((f"<<analyst:{name}>> " + "x" * 80) if ok
                    else f"[refused by {name}]", ok, "ok" if ok else "refused")
        return (f"<<{step_name}>> " + "x" * 80, True, "ok")

    def retry(self, messages, endpoint, step_name, *a, **k):
        name = self._name(endpoint)
        self.calls.append((step_name, name))
        if step_name == "verifier":
            return ("checks pass\nVERDICT: PASS", True, "ok")
        if step_name == "quality-gate":
            return ("all good\nVERDICT: PASS", True, "ok")
        return (f"<<{step_name}>> " + "x" * 80, True, "ok")

    def analyst_calls(self):
        return [n for s, n in self.calls if s == "analyst"]


def _fb_resolver(mapping):
    """Return a fake `_resolve_fallback_endpoint(slot, gear, current, ...)`.
    `mapping` maps slot -> fallback endpoint dict, or None for 'no fallback'."""
    def resolve(slot, gear, current, *a, **k):
        ep = mapping.get(slot, None)
        return dict(ep) if ep else None
    return resolve


@contextlib.contextmanager
def _patched(h, fb_mapping):
    with contextlib.ExitStack() as es:
        def p(name, **kw):
            es.enter_context(mock.patch.object(boot, name, **kw))
        p("resolve_gear4_endpoints",
          return_value=(dict(DEPTH_EP), dict(BREADTH_EP), True))
        p("get_slot_endpoint", return_value=dict(DUMMY_EP))
        p("_resolve_fallback_endpoint", side_effect=_fb_resolver(fb_mapping))
        p("run_gear3", return_value=GEAR3_SENTINEL)
        p("_assemble_step_prompt", return_value="sys")
        p("_images_for_endpoint", return_value=None)
        p("vision_capable_for_endpoint", return_value=True)
        p("_run_claim_verification_preflight", return_value=("", [], {}, []))
        p("_run_unflagged_claim_scan", return_value=("", {}, []))
        p("_maybe_synthesize_visual", return_value=("", {}))
        p("_maybe_review_and_refine_visual", side_effect=lambda text, *a, **k: text)
        p("_formatter_output_structural_check", return_value=(True, "ok"))
        p("_strip_consolidator_preamble", side_effect=lambda t: t)
        p("_strip_dispatch_noise", side_effect=lambda t: t)
        p("_scrub_pipeline_leaks", side_effect=lambda t: (t, [], None))
        p("_call_with_supplement", side_effect=h.supp)
        p("_call_with_retry", side_effect=h.retry)
        yield


def _ctx():
    return {"cleaned_prompt": "Q", "trace_dir": None, "mode_name": "test-mode"}


def _stream_order(calls, primary, fallback):
    names = [n for s, n in calls if s == "analyst"]
    return names.index(primary) < names.index(fallback)


class TestGear4AnalystRecovery(unittest.TestCase):
    def test_analyst_slot_metadata_reaches_primary_and_explicit_fallback_calls(self):
        h = _Harness(health={
            "depth-primary": False,
            "breadth-primary": False,
        })
        fb = {
            "depth": {"name": "depth-fallback"},
            "breadth": {"name": "breadth-fallback"},
        }
        with _patched(h, fb_mapping=fb):
            result = boot.run_gear4(_ctx(), {}, execution_context="interactive")

        self.assertNotEqual(result, GEAR3_SENTINEL)
        analyst_calls = {
            call["endpoint"]: (call["slot"], call["gear"])
            for call in h.supp_calls
            if call["step"] == "analyst"
        }
        self.assertEqual(analyst_calls, {
            "depth-primary": ("depth", None),
            "depth-fallback": ("depth", None),
            "breadth-primary": ("breadth", None),
            "breadth-fallback": ("breadth", None),
        })

    def test_both_primary_healthy_proceeds_no_fallback(self):
        h = _Harness(health={})
        with _patched(h, fb_mapping={}):
            result = boot.run_gear4(_ctx(), {}, execution_context="interactive")
        self.assertNotEqual(result, GEAR3_SENTINEL)        # proceeded
        self.assertNotIn("depth-fallback", h.analyst_calls())   # no fallback used
        self.assertNotIn("breadth-fallback", h.analyst_calls())

    def test_primary_fails_recovers_on_fallback_and_proceeds(self):
        h = _Harness(health={"depth-primary": False})
        fb = {"depth": {"name": "depth-fallback"}, "breadth": {"name": "breadth-fallback"}}
        with _patched(h, fb_mapping=fb):
            result = boot.run_gear4(_ctx(), {}, execution_context="interactive")
        self.assertNotEqual(result, GEAR3_SENTINEL)        # recovered -> proceeded
        names = h.analyst_calls()
        self.assertIn("depth-primary", names)
        self.assertIn("depth-fallback", names)             # fallback was tried
        self.assertTrue(_stream_order(h.calls, "depth-primary", "depth-fallback"),
                        "primary must be attempted before the fallback")

    def test_primary_and_fallback_both_fail_falls_back_to_gear3(self):
        h = _Harness(health={"depth-primary": False, "depth-fallback": False})
        fb = {"depth": {"name": "depth-fallback"}, "breadth": {"name": "breadth-fallback"}}
        with _patched(h, fb_mapping=fb):
            result = boot.run_gear4(_ctx(), {}, execution_context="interactive")
        self.assertEqual(result, GEAR3_SENTINEL)           # unrecoverable -> Gear 3

    def test_no_fallback_available_falls_back_to_gear3(self):
        h = _Harness(health={"breadth-primary": False})
        with _patched(h, fb_mapping={}):                   # resolver returns None
            result = boot.run_gear4(_ctx(), {}, execution_context="interactive")
        self.assertEqual(result, GEAR3_SENTINEL)
        # the fallback was at least attempted to be resolved (breadth tried once)
        self.assertIn("breadth-primary", h.analyst_calls())

    def test_one_stream_unrecoverable_never_proceeds_on_one_model(self):
        # depth healthy, breadth dead even on fallback -> must NOT proceed with
        # depth alone; falls back to Gear 3.
        h = _Harness(health={"breadth-primary": False, "breadth-fallback": False})
        fb = {"breadth": {"name": "breadth-fallback"}}
        with _patched(h, fb_mapping=fb):
            result = boot.run_gear4(_ctx(), {}, execution_context="interactive")
        self.assertEqual(result, GEAR3_SENTINEL)


class TestRecoveryWiredInSource(unittest.TestCase):
    def test_step3_recovery_present(self):
        text = (ORCH_DIR / "boot.py").read_text(encoding="utf-8")
        self.assertIn("_analyst_stream", text)
        self.assertIn("recovered-on-fallback-model", text)
        self.assertIn("unrecoverable-fallback-to-gear3", text)
        # the old "proceed on the error string" contingency is gone
        self.assertNotIn("degraded-cross-eval-on-error-string", text)


if __name__ == "__main__":
    unittest.main()
