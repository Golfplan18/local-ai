"""Tests for the silent-failure remediation pass (2026-05-15 second sweep).

Covers nine fixes:
1. Universal anti-confab actually universal — load_boot_md() carries it.
2. Server-side visual hook — verified by inspecting server.py source.
3. Stealth manifest sidecar — write site + Layer 8 purge.
4. Phase A parse-failure observability — stderr + trace field.
5. load_framework stderr warning on missing file.
6. Verifier case-insensitive verdict matching.
7. Gear 4 single-stream-degraded contingency naming.
8. Bypass triggers honour negation.
9. Zero-strong-signal high-confidence audit flag.
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

# Ensure the worktree's orchestrator/ is importable as both a module path
# (so `import boot` works) and as a package (so `from orchestrator....`
# works for files using relative imports like conversation_closeout).
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKTREE_ROOT = os.path.dirname(HERE)
for p in (HERE, WORKTREE_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import boot
from boot import (
    _UNIVERSAL_ANTI_CONFABULATION,
    _check_strong_bypass,
    _check_weak_bypass,
    _verifier_broken,
    _verifier_passed,
    load_boot_md,
    load_framework,
    parse_step1_output,
    pre_phase_a_bypass_check,
)


class TestUniversalAntiConfabIsUniversal(unittest.TestCase):
    """Fix 1: load_boot_md() now carries the universal directive so every
    caller (including _direct_stream / framework dispatch / legacy /direct)
    gets it, not only build_system_prompt_for_gear callers.
    """

    def test_load_boot_md_appends_universal_directive(self):
        content = load_boot_md()
        self.assertIn("ANTI-CONFABULATION DISCIPLINE — UNIVERSAL", content)
        self.assertIn("Never invent specific facts you cannot verify", content)

    def test_directive_text_unchanged(self):
        # Directive constant itself shouldn't have been mutated.
        self.assertIn("Friday, May 15, 2026 at 10:07:49 AM PDT",
                      _UNIVERSAL_ANTI_CONFABULATION)

    def test_no_double_injection_in_build_system_prompt(self):
        # build_system_prompt_for_gear should NOT inject the directive a
        # second time when load_boot_md already carries it.
        context_pkg = {
            "mode_text": "## DEPTH ANALYSIS GUIDANCE\nTest guidance.\n",
            "mode_name": "test-mode",
            "conversation_rag": "",
            "concept_rag": "",
            "relationship_rag": "",
            "inferred_items": "",
        }
        sp = boot.build_system_prompt_for_gear(context_pkg, slot="breadth",
                                                step="analyst")
        # Universal directive must appear EXACTLY ONCE.
        marker = "ANTI-CONFABULATION DISCIPLINE — UNIVERSAL"
        self.assertEqual(sp.count(marker), 1,
                         "Universal anti-confab directive duplicated in "
                         "system prompt — load_boot_md and "
                         "build_system_prompt_for_gear are both injecting it.")


class TestServerSideVisualHook(unittest.TestCase):
    """Fix 2: server.py::_run_pipeline_from_step2 now invokes _run_visual_hook
    on the gear-pipeline response. Verified by source inspection because
    end-to-end server testing requires a Flask context.
    """

    def test_server_runs_visual_hook_after_gear_pipeline(self):
        server_py = Path(HERE).parent / "server" / "server.py"
        text = server_py.read_text()
        # The hook must be invoked inside _run_pipeline_from_step2 before
        # the final SSE emission.
        self.assertIn("from boot import _run_visual_hook as _server_run_visual_hook",
                      text)
        self.assertIn("_server_run_visual_hook(response, context_pkg)", text)


class TestStealthManifestSidecar(unittest.TestCase):
    """Fix 3: server.py writes a manifest entry at chunk-file-write time;
    conversation_closeout._purge_stealth Layer 8 reads the manifest to
    find chunk_path / raw_path even when ChromaDB indexing failed.
    """

    def test_manifest_write_site_exists_in_server(self):
        server_py = Path(HERE).parent / "server" / "server.py"
        text = server_py.read_text()
        self.assertIn("conversation-manifest.jsonl", text)
        # The write must record the four required fields.
        self.assertIn('"conversation_id": panel_id', text)
        self.assertIn('"chunk_path": chunk_path', text)
        self.assertIn('"raw_path": sess["raw_path"]', text)
        self.assertIn('"tag": tag', text)

    def test_purge_stealth_layer_8_reads_manifest(self):
        closeout_py = Path(HERE) / "conversation_closeout.py"
        text = closeout_py.read_text()
        self.assertIn("Layer 8: Manifest-driven orphan recovery", text)
        self.assertIn("conversation-manifest.jsonl", text)
        self.assertIn("manifest_orphans_removed", text)

    def test_purge_strips_matching_entries_atomically(self):
        # End-to-end: write a manifest with mixed conv_ids, run the purge
        # for one conv_id, verify only matching entries are removed and
        # the others survive.
        #
        # Closeout imports conversation_memory at module-load time; if
        # the HEAD commit doesn't have every symbol it expects, the
        # import chain fails. Inject stubs so the test runs against
        # whatever HEAD is checked out.
        if "orchestrator.conversation_memory" not in sys.modules:
            import types
            stub = types.ModuleType("orchestrator.conversation_memory")
            stub.get_conversation_tag = lambda *a, **kw: "stealth"
            stub.set_conversation_closed = lambda *a, **kw: None
            sys.modules["orchestrator.conversation_memory"] = stub
        else:
            cm = sys.modules["orchestrator.conversation_memory"]
            if not hasattr(cm, "set_conversation_closed"):
                cm.set_conversation_closed = lambda *a, **kw: None
            if not hasattr(cm, "get_conversation_tag"):
                cm.get_conversation_tag = lambda *a, **kw: "stealth"

        from orchestrator.conversation_closeout import _purge_stealth

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sessions_root = tmp_path / "sessions"
            conv_dir = tmp_path / "conversations"
            raw_dir = tmp_path / "raw"
            chroma = tmp_path / "chromadb"
            vault = tmp_path / "vault"

            # Override the manifest root by patching runtime_paths at the
            # attribute Layer 8 reads at call time (the path flows from
            # runtime_paths since Execution Review Phase 2, so patching
            # os.path.expanduser no longer redirects it).
            manifest = tmp_path / "conversation-manifest.jsonl"
            target_chunk = conv_dir / "target_chunk.md"
            target_raw = raw_dir / "target_raw.md"
            other_chunk = conv_dir / "other_chunk.md"

            conv_dir.mkdir()
            raw_dir.mkdir()
            target_chunk.write_text("stealth content")
            target_raw.write_text("raw stealth content")
            other_chunk.write_text("unrelated content")

            manifest.write_text(
                json.dumps({
                    "conversation_id": "stealth-target",
                    "chunk_id": "c1",
                    "chunk_path": str(target_chunk),
                    "raw_path": str(target_raw),
                    "tag": "stealth",
                }) + "\n" +
                json.dumps({
                    "conversation_id": "other-conv",
                    "chunk_id": "c2",
                    "chunk_path": str(other_chunk),
                    "raw_path": "",
                    "tag": "",
                }) + "\n"
            )

            from orchestrator import runtime_paths as _orp
            with mock.patch.object(_orp, "DATA_DIR_STR", str(tmp_path)):
                result = _purge_stealth(
                    "stealth-target",
                    sessions_root=sessions_root,
                    conversations_dir=conv_dir,
                    conversations_raw=raw_dir,
                    chromadb_path=chroma,
                    vault_sessions=vault,
                )

            # Target's chunk + raw deleted; other conversation's chunk
            # untouched; manifest stripped of one entry.
            self.assertFalse(target_chunk.exists(),
                             "Target chunk not deleted by Layer 8")
            self.assertFalse(target_raw.exists(),
                             "Target raw log not deleted by Layer 8")
            self.assertTrue(other_chunk.exists(),
                            "Other conversation's chunk wrongly deleted")
            self.assertEqual(result["deleted"]["manifest_orphans_removed"], 1)

            remaining = manifest.read_text().splitlines()
            remaining_records = [json.loads(line) for line in remaining
                                 if line.strip()]
            self.assertEqual(len(remaining_records), 1)
            self.assertEqual(remaining_records[0]["conversation_id"],
                             "other-conv")


class TestPhaseAParseFailureObservability(unittest.TestCase):
    """Fix 4: parse_step1_output sets phase_a_parse_failed=True AND prints
    a stderr warning when neither cleaned-prompt heading was found.
    """

    def test_malformed_response_sets_phase_a_parse_failed(self):
        narrative = ("Sure, I'd be happy to help. "
                     "Could you share the draft you'd like me to clean up?")
        buf = io.StringIO()
        with redirect_stderr(buf):
            result = parse_step1_output(narrative)
        self.assertTrue(result.get("phase_a_parse_failed"))
        self.assertEqual(result["cleaned_prompt"], narrative)
        self.assertIn("Phase A output unparseable", buf.getvalue())

    def test_well_formed_response_does_not_flag(self):
        well_formed = (
            "### CLEANED PROMPT (Operational Notation)\n"
            "AUDIT: argument-structure(claim)\n"
            "\n### CLEANED PROMPT (Natural Language)\n"
            "Audit my argument's structure.\n"
        )
        buf = io.StringIO()
        with redirect_stderr(buf):
            result = parse_step1_output(well_formed)
        self.assertFalse(result.get("phase_a_parse_failed", False))
        self.assertNotIn("unparseable", buf.getvalue())


class TestLoadFrameworkWarning(unittest.TestCase):
    """Fix 5: load_framework prints stderr on missing file (parity with
    load_mode's behaviour).
    """

    def test_missing_framework_warns(self):
        buf = io.StringIO()
        with redirect_stderr(buf):
            result = load_framework("definitely-does-not-exist.md")
        self.assertIn("[Framework not found:", result)
        self.assertIn("[load_framework]", buf.getvalue())
        self.assertIn("definitely-does-not-exist.md", buf.getvalue())

    def test_existing_framework_no_warning(self):
        # f-verify.md is part of the canonical pipeline scaffolding.
        buf = io.StringIO()
        with redirect_stderr(buf):
            result = load_framework("f-verify.md")
        self.assertTrue(len(result) > 100, "f-verify.md should have substantive content")
        self.assertNotIn("[load_framework]", buf.getvalue())


class TestVerifierCaseInsensitive(unittest.TestCase):
    """Fix 6: _verifier_passed now matches case-insensitively, symmetric
    with _verifier_broken's lowercasing.
    """

    def test_uppercase_verified_passes(self):
        self.assertTrue(_verifier_passed("VERIFIED. All checks pass."))

    def test_lowercase_verdict_line_passes(self):
        # Case-insensitive on the line-anchored verdict.
        self.assertTrue(_verifier_passed(
            "Analysis complete. All checks pass.\n\nverdict: pass"
        ))

    def test_mixed_case_verdict_line_passes(self):
        self.assertTrue(_verifier_passed(
            "Reviewed.\n\nVerdict: Verified with corrections"
        ))

    def test_substring_verified_inside_prose_no_longer_passes(self):
        # Stricter contract (2026-05-15 second-pass fix): a free-form
        # "VERIFIED" inside prose without a line-anchored verdict no
        # longer triggers PASS. This closes the "CANNOT be VERIFIED"
        # substring-false-positive class.
        self.assertFalse(_verifier_passed(
            "This analysis is verified. All checks pass."
        ))
        self.assertFalse(_verifier_passed(
            "This claim CANNOT be VERIFIED yet from the package."
        ))

    def test_verification_failed_still_blocks(self):
        self.assertFalse(_verifier_passed(
            "VERIFICATION FAILED — coverage gap on claim 2."
        ))

    def test_lowercase_failed_blocks(self):
        self.assertFalse(_verifier_passed(
            "verification failed — see below for details on the issue."
        ))

    def test_broken_marker_still_wins(self):
        # Backwards-compat: legacy auto-pass-on-exception text contains
        # "VERIFIED" but should classify as BROKEN.
        legacy = "VERIFIED\n[Verification error, auto-pass: timeout]"
        self.assertTrue(_verifier_broken(legacy))
        self.assertFalse(_verifier_passed(legacy))


class TestGear4SingleStreamContingency(unittest.TestCase):
    """Fix 7: Gear 4 records a contingency when exactly one analyst stream
    is degraded (rather than silently proceeding to step 4 with an error
    string as one of the analysts' outputs).
    """

    def test_contingency_name_recorded_in_source(self):
        boot_py = Path(HERE) / "boot.py"
        text = boot_py.read_text()
        self.assertIn(
            "step3-breadth-analyst-degraded-cross-eval-on-error-string", text
        )
        self.assertIn(
            "step3-depth-analyst-degraded-cross-eval-on-error-string", text
        )


class TestBypassNegationAware(unittest.TestCase):
    """Fix 8: _check_strong_bypass / _check_weak_bypass call _is_negated
    so quoted or negated mentions of trigger phrases don't fire bypass.
    """

    def test_strong_bypass_fires_on_plain_phrase(self):
        result = _check_strong_bypass("Hi, no analysis needed for this.")
        self.assertIsNotNone(result)
        self.assertTrue(result["bypass_to_direct_response"])

    def test_strong_bypass_skips_double_negation(self):
        # "I don't want no analysis" — colloquial double negative meaning
        # the user DOES want analysis. The bypass shouldn't fire.
        result = _check_strong_bypass("I don't want no analysis on this.")
        self.assertIsNone(result,
                          "Bypass should not fire under negation context.")

    def test_strong_bypass_skips_close_negation(self):
        # "don't need no analysis" — "don't" is 2 tokens before the trigger,
        # within the existing ±3-token negation window.
        result = _check_strong_bypass(
            "Look, I don't need no analysis from you on this."
        )
        self.assertIsNone(result,
                          "Close-range negation should suppress bypass.")

    def test_weak_bypass_skips_close_negated_greeting(self):
        # "don't just say hi" — "don't" is 2 tokens before "hi ".
        result = _check_weak_bypass(
            "Please don't just say hi to me — engage with the question."
        )
        self.assertIsNone(result)

    def test_distant_negation_window_limitation_documented(self):
        # KNOWN LIMITATION: the ±3-token window doesn't catch distant
        # negation. This test documents the boundary explicitly so it
        # surfaces if someone widens or narrows the window later.
        # The phrasing has "don't" 5 tokens before the trigger — outside
        # window. Bypass currently fires; widening the window is a
        # separate decision (risks new false positives in other contexts).
        result = _check_strong_bypass(
            "I don't really need to bother checking what time it is now."
        )
        self.assertIsNotNone(result,
                             "Distant negation is documented as not "
                             "suppressed by the ±3-token window; if this "
                             "starts passing, the negation window was "
                             "widened — update this test accordingly.")


class TestZeroStrongSignalFlag(unittest.TestCase):
    """Fix 9: signal_strength_summary carries a zero_strong_signal_high_confidence
    flag for high-confidence dispatches with zero supporting strong signals.
    Verified by source inspection — the trace-write path requires a full
    pipeline mock that's out of scope for a unit test.
    """

    def test_flag_present_in_source(self):
        boot_py = Path(HERE) / "boot.py"
        text = boot_py.read_text()
        self.assertIn("zero_strong_signal_high_confidence", text)
        self.assertIn(
            "Zero-strong-signal high-confidence dispatch", text
        )


if __name__ == "__main__":
    unittest.main()
