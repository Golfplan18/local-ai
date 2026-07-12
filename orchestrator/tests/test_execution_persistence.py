"""Execution Review Phase 7 — tiered persistence (spec §14), per the design packet §10 test plan.

Hermetic: the operational store is redirected to a tempdir via ORA_EXECUTION_RECORDS_DIR /
ORA_EXECUTION_LEDGER_PATH so nothing touches the real ~/ora/data/execution-records/. Covers the
decide_tier truth table, the three-layer sensitivity redaction, the ledger + durable-note writers, the
stealth zero-residue guarantee + the closeout purge backstop, never-raises, the flag-OFF parity of the
common self-evidencing path, the .gitignore effective-ignore guard (Rev-3 P2), and cross-platform
path handling.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_ORCH = Path(__file__).resolve().parent.parent
if str(_ORCH) not in sys.path:
    sys.path.insert(0, str(_ORCH))
_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
import live_guard  # noqa: E402,F401 — quarantines durable oversight/telemetry writes

import execution_persistence as epx  # noqa: E402
import execution_packet as ep  # noqa: E402
import tool_events as te  # noqa: E402


def _pkt(**kw):
    """Build an ExecutionPacket with §14-relevant defaults, overridable per test."""
    base = dict(
        task_id=kw.pop("task_id", "task-1"),
        status=kw.pop("status", "in_progress"),
        risk_tier=kw.pop("risk_tier", "standard"),
        task={"instruction": kw.pop("instruction", "do the thing"),
              "constraints": None, "non_goals": None},
        execution={"producer_claim": {"summary": kw.pop("summary", "a clean deliverable"),
                                       "known_limitations": None},
                   "delta": {"any_mutation": kw.pop("any_mutation", False),
                             "max_mutability": "read", "ref": kw.pop("delta_ref", None)},
                   "source_reads": kw.pop("source_reads", [])},
        verification={"findings": kw.pop("findings", [])},
        observed={"any_mutation": kw.pop("observed_mutation", kw.get("any_mutation", False))},
        loop=kw.pop("loop", None),
    )
    base.update(kw)
    return ep.ExecutionPacket(**base)


class _StoreTempMixin:
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="er-persist-")
        self._prev = {k: os.environ.get(k) for k in
                      ("ORA_EXECUTION_RECORDS_DIR", "ORA_EXECUTION_LEDGER_PATH")}
        os.environ["ORA_EXECUTION_RECORDS_DIR"] = self._tmp
        os.environ["ORA_EXECUTION_LEDGER_PATH"] = os.path.join(self._tmp, "execution-ledger.jsonl")
        te.set_turn_context(conversation_id="conv-123", trace_dir=None, stealth=False)

    def tearDown(self):
        for k, v in self._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        te.set_turn_context()
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _ledger_lines(self):
        path = epx.ledger_sink_path()
        if not os.path.exists(path):
            return []
        with open(path) as f:
            return [json.loads(l) for l in f if l.strip()]


# ── decide_tier truth table (§3.5) ────────────────────────────────────────────
class TestDecideTier(unittest.TestCase):
    def test_self_evidencing_is_git_only(self):
        self.assertEqual(epx.decide_tier(_pkt()), epx.TIER_GIT_ONLY)

    def test_source_read_only_owed_is_git_only(self):
        # any_mutation False, stop_condition None (owed provenance) → routine research → git_only
        p = _pkt(observed_mutation=False, loop={"stop_condition": None, "iteration": 0})
        self.assertEqual(epx.decide_tier(p), epx.TIER_GIT_ONLY)

    def test_converged_clean_is_git_only(self):
        p = _pkt(status="converged", observed_mutation=True,
                 loop={"stop_condition": "criteria_met", "iteration": 1})
        self.assertEqual(epx.decide_tier(p), epx.TIER_GIT_ONLY)

    def test_converged_with_plan_level_finding_is_durable(self):
        p = _pkt(status="converged", observed_mutation=True,
                 loop={"stop_condition": "criteria_met"},
                 findings=[{"class": "plan_level", "severity": "medium", "description": "x"}])
        self.assertEqual(epx.decide_tier(p), epx.TIER_DURABLE_NOTE)

    def test_converged_with_exec_level_finding_only_is_git_only(self):
        p = _pkt(status="converged", observed_mutation=True,
                 loop={"stop_condition": "criteria_met"},
                 findings=[{"class": "execution_level", "severity": "low", "description": "x"}])
        self.assertEqual(epx.decide_tier(p), epx.TIER_GIT_ONLY)

    def test_escalated_is_durable(self):
        p = _pkt(status="escalated", observed_mutation=True,
                 loop={"stop_condition": "max_iterations_escalated",
                       "escalation": {"reason": "did not converge"}})
        self.assertEqual(epx.decide_tier(p), epx.TIER_DURABLE_NOTE)

    def test_escalation_withheld_is_durable(self):
        p = _pkt(status="in_progress", observed_mutation=True,
                 loop={"stop_condition": None, "escalation": None, "escalation_withheld": True})
        self.assertEqual(epx.decide_tier(p), epx.TIER_DURABLE_NOTE)

    def test_mutation_degrade_to_text_is_ledger_line(self):
        p = _pkt(status="in_progress", observed_mutation=True,
                 loop={"stop_condition": None, "note": "degraded to text review"})
        self.assertEqual(epx.decide_tier(p), epx.TIER_LEDGER_LINE)

    def test_none_packet_is_git_only(self):
        self.assertEqual(epx.decide_tier(None), epx.TIER_GIT_ONLY)

    def test_malformed_packet_degrades_to_git_only(self):
        class Bad:
            @property
            def status(self):
                raise RuntimeError("boom")
        self.assertEqual(epx.decide_tier(Bad()), epx.TIER_GIT_ONLY)


# ── Three-layer sensitivity redaction (§5, Rev-1 folds #1/#2/#5) ──────────────
class TestRedaction(unittest.TestCase):
    SECRET_TEXT = "here is the key sk-ABCDEFGHIJKLMNOP1234 and password=hunter2xyz done"

    def test_public_scrubs_inline_secret_but_keeps_text(self):
        p = _pkt(summary=self.SECRET_TEXT, instruction=self.SECRET_TEXT)
        red = epx.redact_for_durable(p, max_sensitivity="public")
        s = red.execution["producer_claim"]["summary"]
        self.assertIn("[SCRUBBED]", s)
        self.assertNotIn("sk-ABCDEFGHIJKLMNOP1234", s)
        self.assertNotIn("hunter2xyz", s)
        # non-secret words survive (scrub-and-keep, not descriptor)
        self.assertIn("done", s)

    def test_sensitive_replaces_freetext_with_descriptor(self):
        # PII/regulated content the secret-regex can't see must NOT be written in the clear.
        pii = "patient John Doe SSN 123-45-6789 diagnosed with condition X"
        p = _pkt(summary=pii, instruction=pii,
                 findings=[{"class": "execution_level", "severity": "low", "description": pii}])
        red = epx.redact_for_durable(p, max_sensitivity="sensitive")
        s = red.execution["producer_claim"]["summary"]
        self.assertIn("[SENSITIVE", s)
        self.assertNotIn("123-45-6789", s)
        self.assertNotIn("John Doe", red.task["instruction"])
        self.assertNotIn("123-45-6789", red.verification["findings"][0]["description"])

    def test_secret_drops_freetext_to_existence_only(self):
        p = _pkt(summary=self.SECRET_TEXT)
        red = epx.redact_for_durable(p, max_sensitivity="secret")
        self.assertEqual(red.execution["producer_claim"]["summary"], epx._SECRET_DESCRIPTOR)

    def test_unknown_level_is_conservative_sensitive(self):
        p = _pkt(summary="patient data 123-45-6789")
        red = epx.redact_for_durable(p, max_sensitivity=None)
        self.assertIn("[SENSITIVE", red.execution["producer_claim"]["summary"])

    def test_original_packet_is_not_mutated(self):
        p = _pkt(summary=self.SECRET_TEXT)
        _ = epx.redact_for_durable(p, max_sensitivity="secret")
        self.assertEqual(p.execution["producer_claim"]["summary"], self.SECRET_TEXT)

    def test_sensitive_delta_path_becomes_descriptor(self):
        # Fixture paths built via tempfile + a Windows-shaped literal — no hardcoded /Users//tmp
        # (portability rule); the point here IS path sensitivity, so cover both path shapes.
        posix_fix = os.path.join(tempfile.gettempdir(), "er-fixture-home", ".ssh", "id_rsa")
        red = epx.redact_for_durable(_pkt(delta_ref=posix_fix), max_sensitivity="public")
        self.assertIn("withheld", red.execution["delta"]["ref"])
        # A Windows-shaped secret path classifies identically (resolve_path_sensitivity
        # normalizes backslashes before its boundary-anchored regexes).
        red2 = epx.redact_for_durable(_pkt(delta_ref=r"C:\Users\x\.ssh\id_rsa"),
                                      max_sensitivity="public")
        self.assertIn("withheld", red2.execution["delta"]["ref"])

    def test_redacted_descriptor_recorded(self):
        p = _pkt(summary="x")
        red = epx.redact_for_durable(p, max_sensitivity="sensitive")
        self.assertIn("descriptors", red.persistence["redacted"])
        self.assertIn("secret=none", red.persistence["redacted"])

    def test_sensitive_scrubs_planning_acceptance_criteria(self):
        # Pre-check blocker fold: acceptance_criteria is instruction-derived model prose that
        # render_for_review emits into the note — it must be scrubbed like the instruction. Covers
        # both the str and list-of-bullets shapes.
        pii = "ship for patient SSN 123-45-6789"
        p = _pkt(planning={"converged_brief": {"acceptance_criteria": [pii, "and be correct"],
                                               "approach": pii, "known_risks": None}})
        red = epx.redact_for_durable(p, max_sensitivity="sensitive")
        ac = red.planning["converged_brief"]["acceptance_criteria"]
        self.assertTrue(all("[SENSITIVE" in x for x in ac))
        self.assertNotIn("123-45-6789", json.dumps(red.planning))
        self.assertIn("planning", red.persistence["redacted"])
        # the ORIGINAL packet's planning is untouched (copy semantics)
        self.assertIn("123-45-6789", json.dumps(p.planning))


# ── Ledger + durable note writers ─────────────────────────────────────────────
class TestWriters(_StoreTempMixin, unittest.TestCase):
    def test_append_ledger_line_stamps_conversation_id(self):
        ok = epx.append_ledger_line({"tier": "ledger_line", "summary": "s"},
                                    conversation_id="conv-xyz")
        self.assertTrue(ok)
        lines = self._ledger_lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["conversation_id"], "conv-xyz")

    def test_append_ledger_line_stealth_writes_nothing(self):
        ok = epx.append_ledger_line({"tier": "ledger_line"}, conversation_id="c", stealth=True)
        self.assertFalse(ok)
        self.assertEqual(self._ledger_lines(), [])

    def test_write_durable_note_renders_scrubbed_copy(self):
        p = _pkt(status="escalated", summary=TestRedaction.SECRET_TEXT)
        red = epx.redact_for_durable(p, max_sensitivity="public")
        path = epx.write_durable_note(red, conversation_id="conv-note")
        self.assertIsNotNone(path)
        body = Path(path).read_text()
        self.assertNotIn("sk-ABCDEFGHIJKLMNOP1234", body)      # scrubbed
        self.assertIn("UNVERIFIED PRODUCER CLAIM", body)        # §16-3 label preserved
        # written into a per-conversation subdir (rmtree-purgeable)
        self.assertEqual(Path(path).parent.name, epx._fs_safe("conv-note"))

    def test_write_durable_note_stealth_writes_nothing(self):
        red = epx.redact_for_durable(_pkt(status="escalated"), max_sensitivity="public")
        self.assertIsNone(epx.write_durable_note(red, conversation_id="c", stealth=True))


# ── persist_packet end-to-end (decide → set tier → redact → write) ────────────
class TestPersistPacket(_StoreTempMixin, unittest.TestCase):
    def test_git_only_writes_nothing_but_sets_tier(self):
        p = _pkt()
        tier = epx.persist_packet(p, sig={}, trace_dir=None)
        self.assertEqual(tier, epx.TIER_GIT_ONLY)
        self.assertEqual(p.persistence["tier"], epx.TIER_GIT_ONLY)
        self.assertEqual(self._ledger_lines(), [])
        self.assertFalse(os.path.isdir(os.path.join(self._tmp, "conv-123")))

    def test_ledger_line_appends_one_line_no_note(self):
        p = _pkt(status="in_progress", observed_mutation=True, any_mutation=True,
                 loop={"stop_condition": None, "iteration": 1})
        tier = epx.persist_packet(p, sig={"max_sensitivity": "public"}, trace_dir="/traces/conv-123/1")
        self.assertEqual(tier, epx.TIER_LEDGER_LINE)
        lines = self._ledger_lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["tier"], "ledger_line")
        self.assertIsNone(lines[0]["note_ref"])
        self.assertEqual(lines[0]["conversation_id"], "conv-123")
        # trace_ref is the deterministic packet path
        self.assertTrue(str(lines[0]["trace_ref"]).endswith("execution-packet.json"))

    def test_durable_note_writes_note_and_ledger_index(self):
        p = _pkt(status="escalated", observed_mutation=True, any_mutation=True,
                 summary="the risky change", risk_tier="high-risk",
                 loop={"stop_condition": "max_iterations_escalated",
                       "escalation": {"reason": "did not converge"}})
        tier = epx.persist_packet(p, sig={"max_sensitivity": "private"}, trace_dir="/t/conv-123/1")
        self.assertEqual(tier, epx.TIER_DURABLE_NOTE)
        lines = self._ledger_lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["tier"], "durable_note")
        self.assertIsNotNone(lines[0]["note_ref"])
        self.assertTrue(os.path.exists(lines[0]["note_ref"]))

    def test_stealth_persist_writes_nothing_durable(self):
        p = _pkt(status="escalated", observed_mutation=True, any_mutation=True,
                 loop={"stop_condition": "max_iterations_escalated",
                       "escalation": {"reason": "x"}})
        tier = epx.persist_packet(p, sig={}, trace_dir=None, stealth=True)
        self.assertEqual(tier, epx.TIER_DURABLE_NOTE)   # tier still computed
        self.assertEqual(self._ledger_lines(), [])       # but nothing written
        self.assertFalse(os.path.isdir(os.path.join(self._tmp, "conv-123")))

    def test_persist_never_raises_on_bad_packet(self):
        class Bad:
            persistence = {}
            @property
            def status(self):
                raise RuntimeError("boom")
        # must not raise; degrades to git_only
        self.assertEqual(epx.persist_packet(Bad(), sig={}), epx.TIER_GIT_ONLY)

    def test_true_max_sensitivity_from_sig_drives_redaction(self):
        # A sensitive-max turn must descriptor-ize the free text even though the summary itself
        # has no regex-catchable secret — proves max_sensitivity is read from sig, not the packet.
        p = _pkt(status="escalated", observed_mutation=True, any_mutation=True,
                 summary="ordinary looking prose with PII inside",
                 loop={"stop_condition": "max_iterations_escalated",
                       "escalation": {"reason": "x"}})
        epx.persist_packet(p, sig={"max_sensitivity": "sensitive"}, trace_dir="/t/conv-123/1")
        note_ref = self._ledger_lines()[0]["note_ref"]
        body = Path(note_ref).read_text()
        self.assertIn("[SENSITIVE", body)
        self.assertNotIn("ordinary looking prose with PII inside", body)

    def test_sensitive_planning_criteria_absent_from_note_body(self):
        # The exact leak the adversarial pre-check caught: a sensitive turn whose acceptance_criteria
        # (rendered into the note's ACCEPTANCE CRITERIA fence) carries PII must NOT appear in the note.
        pii = "patient SSN 123-45-6789 must be migrated"
        p = _pkt(status="escalated", observed_mutation=True, any_mutation=True, instruction=pii,
                 planning={"converged_brief": {"acceptance_criteria": pii}},
                 loop={"stop_condition": "max_iterations_escalated", "escalation": {"reason": "x"}})
        epx.persist_packet(p, sig={"max_sensitivity": "sensitive"}, trace_dir="/t/conv-123/1")
        body = Path(self._ledger_lines()[0]["note_ref"]).read_text()
        self.assertNotIn("123-45-6789", body)   # the leak — now sealed
        self.assertIn("ACCEPTANCE CRITERIA", body)
        self.assertIn("[SENSITIVE", body)        # descriptor present in the criteria fence


# ── Fail-closed redaction (judge P1 fold) ─────────────────────────────────────
class _BombDict(dict):
    """A dict whose deepcopy raises — the judge's exact P1 repro (a packet whose execution block
    fails during copy.deepcopy inside redact_for_durable)."""
    def __deepcopy__(self, memo):
        raise RuntimeError("deepcopy bomb")


class TestFailClosedRedaction(_StoreTempMixin, unittest.TestCase):
    PII = "patient SSN 123-45-6789 in the durable path"

    def _bombed_escalated_pkt(self):
        p = _pkt(status="escalated", observed_mutation=True, any_mutation=True,
                 instruction=self.PII, summary=self.PII,
                 loop={"stop_condition": "max_iterations_escalated",
                       "escalation": {"reason": "x"}})
        p.execution = _BombDict(p.execution)   # deepcopy raises inside redact_for_durable
        return p

    def test_redactor_failure_returns_none_never_the_original(self):
        # Judge P1: the old behavior returned the ORIGINAL unredacted packet on failure.
        self.assertIsNone(
            epx.redact_for_durable(self._bombed_escalated_pkt(), max_sensitivity="sensitive"))

    def test_redaction_failure_fails_closed_no_sensitive_text_on_disk(self):
        # Judge P1 end-to-end repro: a durable_note turn whose redaction fails must write NO note
        # and NO ledger line — a persistence failure may skip durable writes, never fail open.
        p = self._bombed_escalated_pkt()
        tier = epx.persist_packet(p, sig={"max_sensitivity": "sensitive"},
                                  trace_dir="/t/conv-123/1")
        self.assertEqual(tier, epx.TIER_DURABLE_NOTE)   # tier still computed + stamped
        self.assertIn("REDACTION FAILED", p.persistence["redacted"])
        self.assertEqual(self._ledger_lines(), [])       # no ledger line
        leaked = []
        for root, _dirs, files in os.walk(self._tmp):    # no PII anywhere in the store
            for fn in files:
                if self.PII.split()[2] in Path(root, fn).read_text():
                    leaked.append(os.path.join(root, fn))
        self.assertEqual(leaked, [])

    def test_broken_scrub_content_withholds_rather_than_keeps_raw(self):
        # The second fail-open of the same class (self-found): scrub_content raising must not
        # leave raw text in the private/public layer — the field is withheld instead.
        secret_text = "deploy with key sk-ABCDEFGHIJKLMNOP1234 now"
        orig = te.scrub_content
        te.scrub_content = lambda s: (_ for _ in ()).throw(RuntimeError("scrub down"))
        try:
            out = epx._scrub_free_text(secret_text, "public")
        finally:
            te.scrub_content = orig
        self.assertNotIn("sk-ABCDEFGHIJKLMNOP1234", out)
        self.assertIn("withheld", out)


# ── Stealth purge backstop (Rev-1 folds #4/#6/#8) ─────────────────────────────
class TestPurgeConversation(_StoreTempMixin, unittest.TestCase):
    def _seed(self, conversation_id):
        p = _pkt(status="escalated", observed_mutation=True, any_mutation=True,
                 loop={"stop_condition": "max_iterations_escalated", "escalation": {"reason": "x"}})
        te.set_turn_context(conversation_id=conversation_id, stealth=False)
        epx.persist_packet(p, sig={"max_sensitivity": "public"}, trace_dir=f"/t/{conversation_id}/1")

    def test_purge_removes_note_subdir_and_ledger_lines(self):
        self._seed("conv-A")
        self._seed("conv-B")
        self.assertEqual(len(self._ledger_lines()), 2)
        res = epx.purge_conversation("conv-A")
        self.assertTrue(res["note_dir_removed"])
        self.assertEqual(res["ledger_lines_removed"], 1)
        # conv-A gone, conv-B intact
        remaining = self._ledger_lines()
        self.assertEqual([l["conversation_id"] for l in remaining], ["conv-B"])
        self.assertFalse(os.path.isdir(os.path.join(self._tmp, epx._fs_safe("conv-A"))))
        self.assertTrue(os.path.isdir(os.path.join(self._tmp, epx._fs_safe("conv-B"))))

    def test_purge_matches_write_transform_for_fs_unsafe_id(self):
        # A Windows-invalid ':' in the id must be handled by the SAME transform on write + purge,
        # so the backstop still reaches the note (Rev-1 fold #8).
        cid = "panel:AB12/x"
        self._seed(cid)
        subdir = os.path.join(self._tmp, epx._fs_safe(cid))
        self.assertTrue(os.path.isdir(subdir))
        res = epx.purge_conversation(cid)
        self.assertTrue(res["note_dir_removed"])
        self.assertFalse(os.path.isdir(subdir))

    def test_purge_of_absent_conversation_is_noop(self):
        res = epx.purge_conversation("never-seen")
        self.assertFalse(res["note_dir_removed"])
        self.assertEqual(res["ledger_lines_removed"], 0)
        self.assertEqual(res["errors"], [])


# ── Common self-evidencing path stays git_only (parity, §7) ───────────────────
class TestCommonPathParity(_StoreTempMixin, unittest.TestCase):
    def test_construct_and_write_self_evidencing_is_git_only_no_durable(self):
        with tempfile.TemporaryDirectory() as td:
            path = ep.construct_and_write(
                signals={"any_mutation": False, "source_read_suspected": False},
                context_pkg={"raw_prompt": "hi"}, output_text="a plain answer",
                risk_tier="light", trace_dir=td)
            self.assertIsNotNone(path)
            with open(path) as f:
                pkt = json.load(f)
            self.assertEqual(pkt["persistence"]["tier"], "git_only")   # not the old "trace_local"
        # construct_and_write does NOT persist durably (loop-only): no ledger, no note dir
        self.assertEqual(self._ledger_lines(), [])


# ── Portability: fs_safe + the .gitignore effective-ignore guard (Rev-3 P2) ───
class TestPortability(unittest.TestCase):
    def test_fs_safe_maps_unsafe_chars_deterministically(self):
        self.assertEqual(epx._fs_safe("a:b/c\\d e"), "a_b_c_d_e")
        self.assertEqual(epx._fs_safe(""), "unknown")
        self.assertEqual(epx._fs_safe("UUID-hex_123.ok"), "UUID-hex_123.ok")  # already safe
        self.assertEqual(epx._fs_safe("CON"), "_CON")
        self.assertEqual(epx._fs_safe("con.txt"), "_con.txt")
        self.assertEqual(epx._fs_safe("COM1"), "_COM1")
        self.assertEqual(epx._fs_safe("LPT9.log"), "_LPT9.log")
        self.assertEqual(epx._fs_safe("."), "unknown")
        self.assertEqual(epx._fs_safe(".."), "unknown")
        self.assertEqual(epx._fs_safe("name. "), "name")
        self.assertLessEqual(len(epx._fs_safe("x" * 300)), 160)

    def test_store_path_derives_from_runtime_paths(self):
        # No hardcoded mac/user path; env override respected. Fixture root is tempfile-derived
        # (portability rule — no /tmp literal). Hermetic (judge P3): save/clear/restore BOTH store
        # env vars — a caller-set ORA_EXECUTION_LEDGER_PATH would otherwise mask the ledger-path
        # derivation under test.
        prev = {k: os.environ.get(k) for k in
                ("ORA_EXECUTION_RECORDS_DIR", "ORA_EXECUTION_LEDGER_PATH")}
        with tempfile.TemporaryDirectory() as td:
            relocated = os.path.join(td, "relocated-store")
            os.environ["ORA_EXECUTION_RECORDS_DIR"] = relocated
            os.environ.pop("ORA_EXECUTION_LEDGER_PATH", None)
            try:
                self.assertEqual(epx.execution_records_dir(), relocated)
                self.assertTrue(epx.ledger_sink_path().startswith(relocated))
            finally:
                for k, v in prev.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v

    def test_gitignore_effectively_ignores_store(self):
        # Rev-3 P2: assert git ACTUALLY ignores the store paths (behavior, not text presence) —
        # both the ledger and a nested note path.
        repo = Path(__file__).resolve().parents[2]
        try:
            inside = subprocess.run(["git", "-C", str(repo), "rev-parse", "--is-inside-work-tree"],
                                    capture_output=True, text=True)
            if inside.returncode != 0:
                self.skipTest("not a git work tree")
        except FileNotFoundError:
            self.skipTest("git not available")
        for rel in ("data/execution-records/execution-ledger.jsonl",
                    "data/execution-records/conv-123/task-1__20260101.md"):
            r = subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", rel])
            self.assertEqual(r.returncode, 0, f"git does not ignore {rel}")


if __name__ == "__main__":
    unittest.main()
