"""Probe-replay tests for the silent-failure remediation pass.

Each test simulates the failure shape the corresponding fix was meant to
eliminate. If a fix regresses, the test fails with a clear name pointing
at the original failure class.

These tests exercise the pipeline through the same code path the production
server uses (boot.py module-level functions), not through subprocess Flask
calls, so they run fast and don't require a live server.
"""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKTREE_ROOT = os.path.dirname(HERE)
for p in (HERE, WORKTREE_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import boot


# ---------------------------------------------------------------------------
# Probe 1 — Anti-confab universal: every load_boot_md() carries the directive
# ---------------------------------------------------------------------------

class ProbeUniversalAntiConfab(unittest.TestCase):
    """Failure #5 (substring-confab) was closed in the first pass for the
    CLI path but not the server's _direct_stream / framework / legacy paths.
    The second-pass fix moved the directive into load_boot_md() itself so
    every path inherits it.
    """

    def test_every_load_boot_md_invocation_carries_the_directive(self):
        text = boot.load_boot_md()
        self.assertIn("ANTI-CONFABULATION DISCIPLINE — UNIVERSAL", text)
        self.assertIn("Friday, May 15, 2026 at 10:07:49 AM PDT", text)


# ---------------------------------------------------------------------------
# Probe 2 — Server visual hook
# ---------------------------------------------------------------------------

class ProbeServerVisualHook(unittest.TestCase):
    def test_server_invokes_visual_hook_on_response(self):
        server_text = (Path(WORKTREE_ROOT) / "server" / "app.py").read_text()
        self.assertIn("_server_run_visual_hook(response, context_pkg)",
                      server_text)


# ---------------------------------------------------------------------------
# Probe 3 — Verifier line-anchored verdict (closes substring-false-positive)
# ---------------------------------------------------------------------------

class ProbeVerifierVerdictAnchoring(unittest.TestCase):
    def test_cannot_be_verified_inside_prose_does_not_register_as_pass(self):
        # Original failure shape: "CANNOT be VERIFIED" inside a verifier's
        # prose registered as PASS via substring match.
        self.assertFalse(boot._verifier_passed(
            "Reviewed the analysis. This claim CANNOT be VERIFIED from "
            "the package and the analyst's citation does not support it."
        ))

    def test_structured_verdict_pass_works(self):
        self.assertTrue(boot._verifier_passed(
            "## Verification Status\n\n"
            "All eight universal checks pass.\n\n"
            "VERDICT: PASS"
        ))

    def test_structured_verdict_fail_works(self):
        self.assertFalse(boot._verifier_passed(
            "## Verification Status\n\nClaim 2 missing citation.\n\n"
            "VERDICT: FAIL"
        ))

    def test_structured_verdict_broken_is_not_pass(self):
        out = "Could not complete verification.\n\nVERDICT: BROKEN"
        self.assertFalse(boot._verifier_passed(out))
        self.assertTrue(boot._verifier_broken(out))

    def test_legacy_format_still_accepted(self):
        # Backward compatibility for verifier models that follow the
        # legacy 'VERIFIED' / 'VERIFICATION FAILED' contract.
        self.assertTrue(boot._verifier_passed(
            "All checks pass.\n\nVERIFIED — all checks complete."
        ))
        self.assertFalse(boot._verifier_passed(
            "Claim 2 unsupported.\n\nVERIFICATION FAILED — see above."
        ))

    def test_broken_marker_wins_over_verdict(self):
        # If the legacy auto-pass-on-exception text ever resurfaces, it
        # must still classify as BROKEN, not PASS.
        legacy = "VERIFIED\n[Verification error, auto-pass: ETIMEDOUT]"
        self.assertTrue(boot._verifier_broken(legacy))
        self.assertFalse(boot._verifier_passed(legacy))


# ---------------------------------------------------------------------------
# Probe 4 — Health-check patterns catch API-provider errors
# ---------------------------------------------------------------------------

class ProbeProviderErrorHealthCheck(unittest.TestCase):
    def test_anthropic_overloaded_string_is_unhealthy(self):
        # A 200-OK provider error returned as content; previously slipped
        # through the length-only check.
        out = ("anthropic.ApIStatusError: Error code 529 — "
               "overloaded_error: model is currently overloaded. "
               "Please retry shortly with backoff. " * 4)
        ok, reason = boot._step_output_health(out, step_name="analyst",
                                               min_chars=200)
        self.assertFalse(ok, f"Should detect Anthropic overloaded; got {reason}")

    def test_openai_context_length_exceeded_is_unhealthy(self):
        out = ("openai.BadRequestError: context_length_exceeded — "
               "This model's maximum context length is 8192 tokens. "
               "However, your messages resulted in 12000 tokens. " * 4)
        ok, reason = boot._step_output_health(out, step_name="analyst",
                                               min_chars=200)
        self.assertFalse(ok)

    def test_503_service_unavailable_is_unhealthy(self):
        out = ("HTTP 503 Service Unavailable: upstream model server "
               "returned 502 bad gateway. " * 6)
        ok, reason = boot._step_output_health(out, step_name="analyst",
                                               min_chars=200)
        self.assertFalse(ok)


# ---------------------------------------------------------------------------
# Probe 5 — Phase A parse-failure observability
# ---------------------------------------------------------------------------

class ProbePhaseAParseFailure(unittest.TestCase):
    def test_malformed_response_flag_and_stderr(self):
        # Failure shape: Phase A produced a narrative reply rather than the
        # structured output; the user's prompt was silently replaced.
        narrative = "Sure, happy to help — could you share the draft?"
        buf = io.StringIO()
        with redirect_stderr(buf):
            result = boot.parse_step1_output(narrative)
        self.assertTrue(result.get("phase_a_parse_failed"))
        self.assertIn("Phase A output unparseable", buf.getvalue())


# ---------------------------------------------------------------------------
# Probe 6 — History truncation visible in trace
# ---------------------------------------------------------------------------

class ProbeHistoryTruncationVisible(unittest.TestCase):
    def test_long_message_truncation_flagged(self):
        history = [
            {"role": "user", "content": "x" * 1200},
            {"role": "assistant", "content": "y" * 1200},
        ]
        stats = boot._summarize_history_truncation(history,
                                                    window=6,
                                                    per_message_char_cap=500)
        self.assertTrue(stats["any_truncation"])
        self.assertEqual(stats["messages_truncated_by_cap"], 2)
        self.assertEqual(stats["chars_lost_to_cap_total"], 1400)

    def test_outside_window_messages_flagged(self):
        history = [{"role": "user", "content": "short"}] * 10
        stats = boot._summarize_history_truncation(history,
                                                    window=6,
                                                    per_message_char_cap=500)
        self.assertEqual(stats["messages_outside_window"], 4)
        self.assertTrue(stats["any_truncation"])

    def test_clean_history_not_flagged(self):
        history = [{"role": "user", "content": "short"}] * 3
        stats = boot._summarize_history_truncation(history,
                                                    window=6,
                                                    per_message_char_cap=500)
        self.assertFalse(stats["any_truncation"])


# ---------------------------------------------------------------------------
# Probe 7 — Phase A diff catches fabricated concrete nouns
# ---------------------------------------------------------------------------

class ProbePhaseADiff(unittest.TestCase):
    def test_invented_named_entity_flagged(self):
        raw = "audit this proposal"
        # Phase A's expansion invents "Acme Corp" and a year/statistic.
        op = ("AUDIT: proposal\n"
              "STAKEHOLDERS: Acme Corp, regulators\n"
              "CONTEXT: 47% of submissions in 2024 failed audit\n")
        diff = boot._diff_raw_vs_operational(raw, op)
        self.assertTrue(diff["phase_a_added_concrete_nouns"])
        self.assertIn("Acme", diff["new_capitalised_tokens"])
        self.assertIn("2024", diff["new_year_tokens"])
        self.assertIn("47", diff["new_numeric_tokens"])

    def test_no_concrete_nouns_added_clears_flag(self):
        raw = "audit this proposal"
        op = "AUDIT: proposal\n"  # only Phase A vocab + raw content
        diff = boot._diff_raw_vs_operational(raw, op)
        self.assertFalse(diff["phase_a_added_concrete_nouns"])


# ---------------------------------------------------------------------------
# Probe 8 — Bypass triggers honour close-range negation
# ---------------------------------------------------------------------------

class ProbeBypassNegation(unittest.TestCase):
    def test_close_negation_suppresses_bypass(self):
        self.assertIsNone(boot._check_strong_bypass(
            "Look, I don't need no analysis from you on this."
        ))

    def test_plain_trigger_still_fires(self):
        result = boot._check_strong_bypass("Hi, no analysis needed.")
        self.assertIsNotNone(result)


# ---------------------------------------------------------------------------
# Probe 9 — Oversight events skip persistence under stealth context
# ---------------------------------------------------------------------------

class ProbeOversightStealthContext(unittest.TestCase):
    def test_emit_skips_persistence_when_stealth_set(self):
        # Use a temp event log so the test doesn't write to the real one.
        from orchestrator import oversight_events as oe
        with tempfile.TemporaryDirectory() as tmp:
            tmp_log = os.path.join(tmp, "events.jsonl")
            with mock.patch.object(oe, "EVENT_LOG_PATH", tmp_log):
                oe.clear_stealth_context()
                oe.emit({"event_type": "TestEvent", "project_nexus": "x"})
                self.assertTrue(os.path.exists(tmp_log),
                                "Event should land on disk by default.")
                size_before = os.path.getsize(tmp_log)

                oe.set_stealth_context(True)
                try:
                    out = oe.emit({"event_type": "TestEventStealth",
                                    "project_nexus": "x"})
                finally:
                    oe.clear_stealth_context()
                self.assertTrue(out.get("stealth"))
                size_after = os.path.getsize(tmp_log)
                self.assertEqual(size_after, size_before,
                                 "Stealth event must not land on disk.")


# ---------------------------------------------------------------------------
# Probe 10 — Agentic-loop overrun is recorded
# ---------------------------------------------------------------------------

class ProbeAgenticLoopOverrun(unittest.TestCase):
    def test_overrun_writes_jsonl_and_warns(self):
        with tempfile.TemporaryDirectory() as root:
            trace_dir = os.path.join(root, "overrun-dialogue", "turn")
            os.makedirs(trace_dir)
            # Mock call_model and parse_tool_calls to force a loop.
            with mock.patch.object(boot, "call_model",
                                    return_value="<tool_call>...</tool_call>"), \
                 mock.patch.object(boot, "parse_tool_calls",
                                    return_value=[{"name": "t", "parameters": {}}]), \
                 mock.patch.object(boot, "execute_tool",
                                    return_value="r"), \
                 mock.patch.object(boot, "strip_tool_calls",
                                    return_value=""), \
                 mock.patch.object(boot.pipeline_trace, "TRACE_ROOT", root):
                buf = io.StringIO()
                with redirect_stderr(buf):
                    result = boot._run_model_with_tools(
                        [{"role": "system", "content": "s"}],
                        {"name": "fake"},
                        max_iterations=2,
                        trace_dir=trace_dir,
                        step_name="probe",
                    )
                self.assertEqual(result, "")
                self.assertIn("agentic loop hit max_iterations", buf.getvalue())
                overrun_log = os.path.join(
                    trace_dir, "agentic-loop-overruns.jsonl",
                )
                self.assertTrue(os.path.exists(overrun_log))
                with open(overrun_log) as f:
                    rec = json.loads(f.readline())
                self.assertEqual(rec["max_iterations"], 2)
                self.assertEqual(rec["step"], "probe")


# ---------------------------------------------------------------------------
# Probe 11 — load_framework warns on missing file
# ---------------------------------------------------------------------------

class ProbeLoadFrameworkWarning(unittest.TestCase):
    def test_missing_framework_warns(self):
        buf = io.StringIO()
        with redirect_stderr(buf):
            result = boot.load_framework("nonexistent-framework-xyz.md")
        self.assertIn("[Framework not found:", result)
        self.assertIn("[load_framework]", buf.getvalue())


# ---------------------------------------------------------------------------
# Probe 12 — Stage 2 dual-dispatch audit field is present
# ---------------------------------------------------------------------------

class ProbeDualDispatchAuditField(unittest.TestCase):
    def test_field_threaded_into_trace_payload(self):
        # Inspect source: the trace payload must include the audit dict.
        boot_text = (Path(WORKTREE_ROOT) / "orchestrator" / "boot.py").read_text()
        self.assertIn("dispatch_audit_raw_vs_expanded", boot_text)
        self.assertIn("phase_a_introduced_dispatch", boot_text)


if __name__ == "__main__":
    unittest.main()
