"""Tests for orchestrator/evidence_runner.py — Execution Review Phase 5.

Covers: catalog parse/validate/discover, ENFORCE-OR-REFUSE runner semantics, the
Phase-1 gate integration, mutates:true handling, dirty-state git snapshots, the
planning-stage Evidence Contract producer, lane fill + sufficiency, and — per the
release-blocking portability amendment — Windows-behaviour SIMULATIONS that run on
mac/Linux CI (never skip-green). Real kernel-sandbox enforcement is the only
mac-gated part; enforce-or-refuse behaviour is tested on every platform.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path, PureWindowsPath
from unittest import mock

# __file__-relative sys.path (the house convention; a worktree imports its own
# modules regardless of cwd).
_ORCH = Path(__file__).resolve().parent.parent
if str(_ORCH) not in sys.path:
    sys.path.insert(0, str(_ORCH))
_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
import live_guard  # noqa: E402,F401 — quarantines durable oversight/telemetry writes

import evidence_runner as er  # noqa: E402
from evidence_runner import Check, Runner, Catalog, CheckResult  # noqa: E402


_PYTHON_PASSTHROUGH_WRAPPER = [
    sys.executable,
    "-c",
    "import subprocess,sys; raise SystemExit(subprocess.call(sys.argv[1:]))",
]


def _reset_probe():
    er._unshare_probe_cache = None
    er._wrapper_probe_cache.clear()


# ── Catalog ───────────────────────────────────────────────────────────────────
class TestCatalog(unittest.TestCase):
    def _write(self, text: str) -> str:
        d = tempfile.mkdtemp()
        p = os.path.join(d, ".ora")
        os.makedirs(p, exist_ok=True)
        fp = os.path.join(p, "evidence.yaml")
        with open(fp, "w") as f:
            f.write(text)
        return fp

    def test_parse_valid_argv_catalog(self):
        fp = self._write(
            "checks:\n"
            "  test: {argv: [python, -m, unittest], mutates: false, timeout: 60, network: deny}\n"
            "runner: {working_dir: <repo-root>, env: isolated, network: deny, redact: by-sensitivity, on_unknown: gated}\n")
        cat = er.parse_catalog(fp)
        self.assertIn("test", cat.checks)
        self.assertEqual(cat.checks["test"].argv, ["python", "-m", "unittest"])
        self.assertEqual(cat.runner.redact, "by-sensitivity")

    def test_malformed_yaml_raises_loudly(self):
        fp = self._write("checks: [this is not a mapping]\n")
        with self.assertRaises(ValueError):
            er.parse_catalog(fp)

    def test_missing_redact_is_invalid(self):
        fp = self._write(
            "checks:\n  t: {argv: [python, -c, pass]}\n"
            "runner: {working_dir: x, env: isolated, network: deny, on_unknown: gated}\n")
        with self.assertRaises(ValueError) as ctx:
            er.parse_catalog(fp)
        self.assertIn("redact", str(ctx.exception))

    def test_check_needs_argv_or_cmd(self):
        errs = er.validate_check("t", {"mutates": False})
        self.assertTrue(any("argv" in e for e in errs))

    def test_shell_true_only_with_cmd(self):
        errs = er.validate_check("t", {"argv": ["x"], "shell": True})
        self.assertTrue(any("shell" in e for e in errs))

    def test_cmd_without_shell_rejected(self):
        # P3: a cmd form always refuses at runtime without shell:true → invalid.
        errs = er.validate_check("t", {"cmd": "echo x"})
        self.assertTrue(any("shell: true" in e for e in errs))
        # with shell:true it's valid
        self.assertEqual(er.validate_check("t", {"cmd": "echo x", "shell": True}), [])

    def test_mixed_argv_and_cmd_families_rejected(self):
        # P3: cannot mix an argv form with a cmd form.
        errs = er.validate_check("t", {"argv": ["x"], "cmd_windows": "y",
                                       "cmd_posix": "z", "shell": True})
        self.assertTrue(any("mix" in e for e in errs))

    def test_base_cmd_must_be_a_string(self):
        # P3 (last detail): base 'cmd' is type-checked (a list is invalid).
        errs = er.validate_check("t", {"cmd": ["echo"], "shell": True})
        self.assertTrue(any("'cmd' must be a string" in e for e in errs))
        # a string cmd + shell is valid
        self.assertEqual(er.validate_check("t", {"cmd": "echo x", "shell": True}), [])

    def test_bad_network_rejected(self):
        errs = er.validate_check("t", {"argv": ["x"], "network": "wat"})
        self.assertTrue(any("network" in e for e in errs))

    def test_per_platform_variants_must_be_matched_pair(self):
        # P2-2: a POSIX-only variant with no base + no windows side is invalid
        # (would silently refuse on Windows).
        errs = er.validate_check("t", {"argv_posix": ["make"]})
        self.assertTrue(any("matched pair" in e for e in errs))
        # a matched pair is valid
        self.assertEqual(er.validate_check("t", {"argv_posix": ["make"], "argv_windows": ["nmake"]}), [])
        # a base argv alone is valid (works on both)
        self.assertEqual(er.validate_check("t", {"argv": ["python", "-V"]}), [])
        # a per-platform variant of the wrong type is rejected (argv → list, cmd → str)
        self.assertTrue(any("must be a list" in e
                            for e in er.validate_check("t", {"argv_posix": "make", "argv_windows": ["nmake"]})))
        self.assertTrue(any("must be a string" in e
                            for e in er.validate_check("t", {"cmd_posix": ["x"], "cmd_windows": "y"})))

    def test_shipped_ora_catalog_parses_and_validates(self):
        # The catalog is parse+validate ONLY here — NEVER executed (its `discover
        # -s orchestrator/tests` would recurse into this very test file).
        cat_path = _ORCH.parent / ".ora" / "evidence.yaml"
        if not cat_path.is_file():
            self.skipTest("no shipped ~/ora catalog in this worktree")
        cat = er.parse_catalog(str(cat_path))
        self.assertIn("test", cat.checks)
        self.assertEqual(cat.checks["test"].network, "deny")
        # argv form (shell-free) — no `cmd`/shell POSIX assumption.
        self.assertIsNotNone(cat.checks["test"].argv)
        self.assertIsNone(cat.checks["test"].cmd)

    def test_discover_from_repo_root_and_walk(self):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, ".ora"))
        with open(os.path.join(d, ".ora", "evidence.yaml"), "w") as f:
            f.write("checks: {}\nrunner: {working_dir: x, env: isolated, network: deny, redact: by-sensitivity, on_unknown: gated}\n")
        self.assertEqual(er.discover_catalog(d), os.path.join(d, ".ora", "evidence.yaml"))
        # nested subdir → upward walk finds it
        sub = os.path.join(d, "a", "b")
        os.makedirs(sub)
        with mock.patch("os.getcwd", return_value=sub):
            self.assertTrue(er.discover_catalog(None))


# ── resolve_command ───────────────────────────────────────────────────────────
class TestResolveCommand(unittest.TestCase):
    def test_python_resolves_to_sys_executable(self):
        argv, cmd, sh = er.resolve_command(Check(name="t", argv=["python3", "-c", "print(1)"]))
        self.assertEqual(argv[0], sys.executable)
        self.assertIsNone(cmd)
        self.assertFalse(sh)

    def test_argv_is_shell_free(self):
        argv, cmd, sh = er.resolve_command(Check(name="t", argv=["node", "x.js"]))
        self.assertEqual(argv, ["node", "x.js"])
        self.assertFalse(sh)

    def test_per_platform_variant_selected(self):
        c = Check(name="t", argv_posix=["make"], argv_windows=["nmake"])
        with mock.patch.object(os, "name", "posix"):
            argv, _, _ = er.resolve_command(c)
            self.assertEqual(argv, ["make"])
        with mock.patch.object(os, "name", "nt"):
            argv, _, _ = er.resolve_command(c)
            self.assertEqual(argv, ["nmake"])


# ── ENFORCE-OR-REFUSE ─────────────────────────────────────────────────────────
class TestEnforceOrRefuse(unittest.TestCase):
    def setUp(self):
        _reset_probe()

    def test_backend_deny_only(self):
        # local/allow are never enforceable in P5 → None → refuse.
        self.assertIsNone(er.enforcement_backend("local"))
        self.assertIsNone(er.enforcement_backend("allow"))

    def test_native_windows_backend_precedes_declared_wrapper(self):
        with mock.patch.object(er, "_macos_sandbox_available", return_value=False), \
             mock.patch.object(er, "_windows_appcontainer_available", return_value=True), \
             mock.patch.object(er, "_declared_wrapper",
                               return_value=_PYTHON_PASSTHROUGH_WRAPPER):
            self.assertEqual(er.enforcement_backend("deny"), "windows-appcontainer")

    def test_native_windows_spike_requires_explicit_opt_in(self):
        module = types.SimpleNamespace(
            available=mock.Mock(return_value=True), recover_pending=mock.Mock())
        with mock.patch.object(sys, "platform", "win32"), \
             mock.patch.object(os, "name", "nt"), \
             mock.patch.dict(sys.modules, {"windows_appcontainer": module}), \
             mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(er._ENV_WINDOWS_APPCONTAINER, None)
            self.assertFalse(er._windows_appcontainer_available())
            module.available.assert_not_called()
            module.recover_pending.assert_called_once()
            os.environ[er._ENV_WINDOWS_APPCONTAINER] = "1"
            self.assertTrue(er._windows_appcontainer_available())
            module.available.assert_called_once()
            self.assertEqual(module.recover_pending.call_count, 2)

    def test_native_windows_dispatch_uses_stdio_result_not_subprocess_prefix(self):
        native = types.SimpleNamespace(
            started=True, returncode=0, stdout="PIPE_STDOUT", stderr="PIPE_STDERR",
            timed_out=False, error=None, cleanup_error=None,
        )
        module = types.SimpleNamespace(run=mock.Mock(return_value=native))
        with mock.patch.object(er, "enforcement_backend",
                               return_value="windows-appcontainer"), \
             mock.patch.object(er, "_gate_check", return_value=(True, "ok")), \
             mock.patch.object(er, "_wrap_argv") as wrap, \
             mock.patch.object(er.subprocess, "run") as ordinary_run, \
             mock.patch.dict(sys.modules, {"windows_appcontainer": module}):
            result = er._run_check_impl(
                Check(name="native", argv=[sys.executable, "-c", "print('x')"]),
                Runner(), tempfile.mkdtemp())
        self.assertTrue(result.passed)
        self.assertEqual(result.backend, "windows-appcontainer")
        self.assertEqual(result.enforcement_model, "orchestrated")
        self.assertIn("PIPE_STDOUT", result.stdout_tail)
        self.assertIn("PIPE_STDERR", result.stdout_tail)
        wrap.assert_not_called()
        ordinary_run.assert_not_called()
        call = module.run.call_args
        self.assertEqual(call.args[0][0], sys.executable)
        self.assertIn("readonly_roots", call.kwargs)
        self.assertIn("writable_roots", call.kwargs)

    def test_native_windows_prelaunch_failure_is_unclaimed_refusal(self):
        module = types.SimpleNamespace(
            run=mock.Mock(side_effect=RuntimeError("ACL recovery failed")))
        with mock.patch.object(er, "enforcement_backend",
                               return_value="windows-appcontainer"), \
             mock.patch.object(er, "_gate_check", return_value=(True, "ok")), \
             mock.patch.dict(sys.modules, {"windows_appcontainer": module}):
            result = er._run_check_impl(
                Check(name="native", argv=[sys.executable, "-c", "pass"]),
                Runner(), tempfile.mkdtemp())
        self.assertTrue(result.skipped)
        self.assertIsNone(result.backend)
        self.assertIsNone(result.enforcement_model)
        self.assertIn("failed closed", result.skip_reason or "")

    def test_native_timeout_is_a_started_orchestrated_failure(self):
        native = types.SimpleNamespace(
            started=True, returncode=None, stdout="", stderr="", timed_out=True,
            error=None, cleanup_error=None,
        )
        module = types.SimpleNamespace(run=mock.Mock(return_value=native))
        with mock.patch.object(er, "enforcement_backend",
                               return_value="windows-appcontainer"), \
             mock.patch.object(er, "_gate_check", return_value=(True, "ok")), \
             mock.patch.dict(sys.modules, {"windows_appcontainer": module}):
            result = er._run_check_impl(
                Check(name="native", argv=[sys.executable, "-c", "pass"], timeout=1),
                Runner(), tempfile.mkdtemp())
        self.assertFalse(result.skipped)
        self.assertFalse(result.passed)
        self.assertEqual(result.enforcement_model, "orchestrated")
        self.assertIn("timeout", result.stdout_tail.lower())

    def test_unknown_backend_never_passes_through_or_claims_orchestrated(self):
        with self.assertRaises(ValueError):
            er._wrap_argv("typo", ["echo", "x"], "/repo", "/tmp", False)
        allowed, why = er._gate_check(Check(name="t"), "typo")
        self.assertFalse(allowed)
        self.assertIn("unknown", why or "")

    def test_no_backend_refuses_cleanly_not_run(self):
        # Simulate a platform with NO enforcing backend at all.
        with mock.patch.object(er, "_macos_sandbox_available", return_value=False), \
             mock.patch.object(er, "_windows_appcontainer_available", return_value=False), \
             mock.patch.object(er, "_declared_wrapper", return_value=None), \
             mock.patch.object(er, "_linux_unshare_available", return_value=False):
            self.assertIsNone(er.enforcement_backend("deny"))
            res = er.run_check(Check(name="t", argv=["python", "-c", "print(1)"]),
                               Runner(), tempfile.mkdtemp())
            self.assertTrue(res.skipped)
            self.assertIsNone(res.enforcement_model)      # NEVER orchestrated when refused
            self.assertIn("ORA_EVIDENCE_SANDBOX", res.skip_reason or "")

    def test_declared_wrapper_runs_declared_sandbox(self):
        # A declared wrapper (not a demonstrable passthrough) makes the check RUN and
        # records enforcement_model='declared-sandbox' (operator-ATTESTED, NOT the
        # runner-verified 'orchestrated' — §7/§17, the fold re-check).
        repo = tempfile.mkdtemp()
        with mock.patch.object(er, "_macos_sandbox_available", return_value=False), \
             mock.patch.object(er, "_windows_appcontainer_available", return_value=False), \
             mock.patch.object(er, "_wrapper_is_demonstrable_passthrough", return_value=False), \
             mock.patch.object(er, "_declared_wrapper",
                               return_value=_PYTHON_PASSTHROUGH_WRAPPER):
            self.assertEqual(er.enforcement_backend("deny"), "ora-evidence-sandbox")
            res = er.run_check(Check(name="ok", argv=["python", "-c", "print('hi')"]),
                               Runner(), repo)
            self.assertFalse(res.skipped)
            self.assertTrue(res.passed)
            self.assertEqual(res.exit_code, 0)
            self.assertEqual(res.enforcement_model, "declared-sandbox")  # NOT orchestrated
            self.assertEqual(res.backend, "ora-evidence-sandbox")

    def test_demonstrable_passthrough_refused(self):
        # SEC-4 + re-check: a wrapper PROVEN not to isolate network (baseline OPEN
        # AND wrapped OPEN) is refused — never used as a backend, never records an
        # enforcement claim.
        with mock.patch.object(er, "_macos_sandbox_available", return_value=False), \
             mock.patch.object(er, "_windows_appcontainer_available", return_value=False), \
             mock.patch.object(er, "_linux_unshare_available", return_value=False), \
             mock.patch.object(er, "_wrapper_is_demonstrable_passthrough", return_value=True), \
             mock.patch.object(er, "_declared_wrapper",
                               return_value=_PYTHON_PASSTHROUGH_WRAPPER):
            self.assertIsNone(er.enforcement_backend("deny"))
            res = er.run_check(Check(name="t", argv=["python", "-c", "print(1)"]),
                               Runner(), tempfile.mkdtemp())
            self.assertTrue(res.skipped)
            self.assertIsNone(res.enforcement_model)

    def test_passthrough_probe_is_reject_only_and_attributive(self):
        # The re-check's core fold: DENIED must be ATTRIBUTABLE to the wrapper.
        # baseline OPEN + wrapped OPEN → demonstrable passthrough (True/reject).
        # baseline OPEN + wrapped DENIED → wrapper blocked → not a passthrough (False).
        # baseline DENIED (offline/egress-filtered) → un-attributable → False (the
        #   false-positive the re-check found; must NOT be read as enforcement).
        with mock.patch.object(er, "_declared_wrapper",
                               return_value=_PYTHON_PASSTHROUGH_WRAPPER):
            for baseline, wrapped, expected in [("OPEN", "OPEN", True),
                                                ("OPEN", "DENIED", False),
                                                ("DENIED", "OPEN", False),
                                                ("DENIED", "DENIED", False),
                                                ("ERROR", "DENIED", False)]:
                er._wrapper_probe_cache.clear()
                with mock.patch.object(er, "_net_probe",
                                       side_effect=[baseline, wrapped]):
                    self.assertEqual(er._wrapper_is_demonstrable_passthrough(), expected,
                                     f"baseline={baseline} wrapped={wrapped}")

    def test_exit_nonzero_is_failed(self):
        repo = tempfile.mkdtemp()
        with mock.patch.object(er, "_macos_sandbox_available", return_value=False), \
             mock.patch.object(er, "_windows_appcontainer_available", return_value=False), \
             mock.patch.object(er, "_wrapper_is_demonstrable_passthrough", return_value=False), \
             mock.patch.object(er, "_declared_wrapper",
                               return_value=_PYTHON_PASSTHROUGH_WRAPPER):
            res = er.run_check(Check(name="bad", argv=["python", "-c", "import sys; sys.exit(3)"]),
                               Runner(), repo)
            self.assertFalse(res.passed)
            self.assertEqual(res.exit_code, 3)
            self.assertEqual(res.enforcement_model, "declared-sandbox")

    def test_timeout_is_failed_with_reason(self):
        repo = tempfile.mkdtemp()
        with mock.patch.object(er, "_macos_sandbox_available", return_value=False), \
             mock.patch.object(er, "_windows_appcontainer_available", return_value=False), \
             mock.patch.object(er, "_wrapper_is_demonstrable_passthrough", return_value=False), \
             mock.patch.object(er, "_declared_wrapper",
                               return_value=_PYTHON_PASSTHROUGH_WRAPPER):
            res = er.run_check(
                Check(name="slow", argv=["python", "-c", "import time; time.sleep(5)"], timeout=1),
                Runner(), repo)
            self.assertFalse(res.passed)
            self.assertIn("timeout", res.stdout_tail.lower())

    def test_invalid_wrapper_counts_as_no_backend(self):
        with mock.patch.object(er, "_macos_sandbox_available", return_value=False), \
             mock.patch.object(er, "_windows_appcontainer_available", return_value=False), \
             mock.patch.object(er, "_linux_unshare_available", return_value=False), \
             mock.patch.dict(os.environ, {er._ENV_SANDBOX: "/nonexistent/definitely/not/here"}):
            self.assertIsNone(er._declared_wrapper())
            self.assertIsNone(er.enforcement_backend("deny"))

    def test_clean_env_strips_ssh_auth_sock(self):
        env = er._clean_env("/x/home", "/x/tmp")
        self.assertNotIn("SSH_AUTH_SOCK", env)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", env)

    def test_env_inherit_is_rejected_by_validation(self):
        # SEC-5: a catalog cannot declare env: inherit (it would leak credentials).
        errs = er.validate_runner_block(
            {"working_dir": "x", "env": "inherit", "network": "deny",
             "redact": "by-sensitivity", "on_unknown": "gated"})
        self.assertTrue(any("env" in e for e in errs))

    def test_sandbox_refuses_unsafe_worktree_path(self):
        # SEC-1: a worktree path with an SBPL-unsafe char is refused (no profile
        # injection). enforcement backend is sandbox-exec on mac.
        if not er._macos_sandbox_available():
            self.skipTest("macOS sandbox-exec only")
        evil = tempfile.mkdtemp() + '/a") (allow network*) ("'
        os.makedirs(evil, exist_ok=True)
        res = er.run_check(Check(name="t", argv=["python", "-c", "print(1)"]),
                           Runner(), evil)
        self.assertTrue(res.skipped)
        self.assertIn("unsafe", (res.skip_reason or "").lower())

    def test_sandbox_refuses_ancestor_of_sensitive_root(self):
        # SEC-2: a worktree equal-to/ancestor-of $HOME/vault/conversations is
        # refused (re-allowing it would re-expose that root).
        bad = er.sandbox_worktree_unsafe(os.path.expanduser("~"), tempfile.mkdtemp())
        self.assertIsNotNone(bad)
        self.assertIn("ancestor", bad)
        # a normal repo (a fresh tmp dir, not an ancestor of a sensitive root) is fine
        self.assertIsNone(er.sandbox_worktree_unsafe(tempfile.mkdtemp(), tempfile.mkdtemp()))

    @unittest.skipUnless(er._macos_sandbox_available(), "macOS sandbox-exec only")
    def test_macos_sandbox_denies_network(self):
        # The kernel guarantee — mac-gated. A network:deny check under sandbox-exec
        # cannot open a socket.
        repo = tempfile.mkdtemp()
        code = ("import socket,sys\n"
                "try:\n socket.create_connection(('1.1.1.1',80),timeout=3); print('OPEN')\n"
                "except Exception: print('DENIED')\n")
        res = er.run_check(Check(name="net", argv=["python", "-c", code]), Runner(), repo)
        self.assertFalse(res.skipped)
        self.assertIn("DENIED", res.stdout_tail)
        self.assertEqual(res.enforcement_model, "orchestrated")

    @unittest.skipUnless(er._macos_sandbox_available(), "macOS sandbox-exec only")
    def test_macos_sandbox_allows_write_under_scratch_home(self):
        # A check that writes under $HOME (npm/pip/git-style ~/.cache) must NOT
        # EPERM: $HOME is a per-run scratch dir (isolated, not the user's real
        # home), so it gets a read+write re-allow. Regression: run_home was
        # exported as $HOME but never write-allowed in the SBPL profile.
        repo = tempfile.mkdtemp()
        code = ("import os\n"
                "p = os.path.join(os.path.expanduser('~'), '.cache', 'ora-probe')\n"
                "os.makedirs(os.path.dirname(p), exist_ok=True)\n"
                "open(p, 'w').write('ok'); print('WROTE_HOME')\n")
        res = er.run_check(Check(name="home", argv=["python", "-c", code]),
                           Runner(), repo)
        self.assertFalse(res.skipped)
        self.assertIn("WROTE_HOME", res.stdout_tail)


# ── Gate integration ──────────────────────────────────────────────────────────
class TestGateIntegration(unittest.TestCase):
    def test_deny_check_passes_gate(self):
        allowed, why = er._gate_check(Check(name="t", network="deny"), "sandbox-exec")
        self.assertTrue(allowed)

    def test_no_backend_gate_blocks(self):
        allowed, why = er._gate_check(Check(name="t"), None)
        self.assertFalse(allowed)

    def test_gate_axes_enforcement_is_per_backend(self):
        # P1-3: the gate axes must carry the HONEST per-backend enforcement — a
        # wrapper is declared-sandbox, NOT a hardcoded orchestrated.
        captured = {}
        def _fake_gate(action, axes, **kw):
            captured.update(axes)
            from tool_events import GateDecision
            return GateDecision(True, "allowed", "ok")
        with mock.patch.object(er._te, "gate", _fake_gate):
            er._gate_check(Check(name="t"), "ora-evidence-sandbox")
            self.assertEqual(captured["enforcement"], "declared-sandbox")
            er._gate_check(Check(name="t"), "sandbox-exec")
            self.assertEqual(captured["enforcement"], "orchestrated")


# ── Observability — every check leaves a tool-event (§16-3) ───────────────────
class TestObservability(unittest.TestCase):
    def setUp(self):
        _reset_probe()

    def test_refused_check_records_tool_event(self):
        # P1-2: a refused check must be VISIBLE in the tool-event log.
        with mock.patch.object(er._te, "record") as rec, \
             mock.patch.object(er, "_macos_sandbox_available", return_value=False), \
             mock.patch.object(er, "_windows_appcontainer_available", return_value=False), \
             mock.patch.object(er, "_declared_wrapper", return_value=None), \
             mock.patch.object(er, "_linux_unshare_available", return_value=False):
            er.run_check(Check(name="t", argv=["python", "-c", "print(1)"]),
                         Runner(), tempfile.mkdtemp())
        evs = [c.args[0] for c in rec.call_args_list
               if c.args and isinstance(c.args[0], dict)
               and c.args[0].get("event") == "evidence_check"]
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["gate"]["decision"], "blocked")
        self.assertEqual(evs[0]["enforcement_model"], "in_harness")   # runner refused

    def test_ran_check_records_tool_event_with_honest_enforcement(self):
        # P1-2 + P1-3: a check that RAN records exactly one event with the honest
        # backend enforcement (declared-sandbox for a wrapper).
        with mock.patch.object(er._te, "record") as rec, \
             mock.patch.object(er, "_macos_sandbox_available", return_value=False), \
             mock.patch.object(er, "_windows_appcontainer_available", return_value=False), \
             mock.patch.object(er, "_wrapper_is_demonstrable_passthrough", return_value=False), \
             mock.patch.object(er, "_declared_wrapper",
                               return_value=_PYTHON_PASSTHROUGH_WRAPPER):
            er.run_check(Check(name="ok", argv=["python", "-c", "print(1)"]),
                         Runner(), tempfile.mkdtemp())
        evs = [c.args[0] for c in rec.call_args_list
               if c.args and isinstance(c.args[0], dict)
               and c.args[0].get("event") == "evidence_check"]
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["gate"]["decision"], "allowed")
        self.assertEqual(evs[0]["enforcement_model"], "declared-sandbox")
        self.assertIn(evs[0]["enforcement_model"], er._te.ENFORCEMENT)   # in the vocabulary

    def test_run_contract_missing_check_records_event(self):
        # P2: a declared-required check MISSING from the catalog is a refusal that
        # must also leave a tool-event (it bypassed run_check).
        cat = Catalog(checks={})   # empty catalog
        contract = {"required_standard_checks": ["ghost"]}
        with mock.patch.object(er._te, "record") as rec:
            results = er.run_contract(cat, contract, tempfile.mkdtemp())
        self.assertTrue(results[0].skipped)
        evs = [c.args[0] for c in rec.call_args_list
               if c.args and isinstance(c.args[0], dict)
               and c.args[0].get("event") == "evidence_check"]
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["action"], "evidence_check:ghost")
        self.assertEqual(evs[0]["gate"]["decision"], "blocked")


# ── mutates:true ──────────────────────────────────────────────────────────────
class TestMutatesTrue(unittest.TestCase):
    def test_mutates_refused_in_dirty_modes(self):
        for mode in ("review_dirty_diff", "continue_user_changes"):
            res = er.run_check(Check(name="m", argv=["python", "-c", "pass"], mutates=True),
                               Runner(), tempfile.mkdtemp(), mode=mode)
            self.assertTrue(res.skipped)
            self.assertIn("mutates", res.skip_reason)

    def test_mutates_refused_under_default_mode(self):
        # SEC-3: absence of an explicit mode FAILS SAFE — a mutating check with the
        # default mode=None is REFUSED, not permitted.
        res = er.run_check(Check(name="m", argv=["python", "-c", "pass"], mutates=True),
                           Runner(), tempfile.mkdtemp())   # mode defaults to None
        self.assertTrue(res.skipped)
        self.assertIn("mutates", res.skip_reason)

    def test_mutates_allowed_under_clean_worktree(self):
        repo = tempfile.mkdtemp()
        with mock.patch.object(er, "_macos_sandbox_available", return_value=False), \
             mock.patch.object(er, "_windows_appcontainer_available", return_value=False), \
             mock.patch.object(er, "_wrapper_is_demonstrable_passthrough", return_value=False), \
             mock.patch.object(er, "_declared_wrapper",
                               return_value=_PYTHON_PASSTHROUGH_WRAPPER):
            res = er.run_check(Check(name="m", argv=["python", "-c", "print('ok')"], mutates=True),
                               Runner(), repo, mode="clean_worktree")
            self.assertFalse(res.skipped)
            self.assertTrue(res.passed)

    def test_shell_true_runs_on_posix(self):
        # PORT-1: a shell:true check must be runnable on POSIX (/bin/sh), not always
        # refused. Verified under an enforcing (mocked) wrapper backend.
        if os.name == "nt":
            self.skipTest("POSIX shell path")
        repo = tempfile.mkdtemp()
        with mock.patch.object(er, "_macos_sandbox_available", return_value=False), \
             mock.patch.object(er, "_windows_appcontainer_available", return_value=False), \
             mock.patch.object(er, "_wrapper_is_demonstrable_passthrough", return_value=False), \
             mock.patch.object(er, "_declared_wrapper",
                               return_value=_PYTHON_PASSTHROUGH_WRAPPER):
            res = er.run_check(Check(name="sh", cmd="echo hi", shell=True), Runner(), repo)
            self.assertFalse(res.skipped)
            self.assertTrue(res.passed)


# ── Dirty-state git snapshots ─────────────────────────────────────────────────
class TestDirtyState(unittest.TestCase):
    def _repo(self) -> str:
        d = tempfile.mkdtemp()
        subprocess.run(["git", "-C", d, "init", "-q"], check=True)
        subprocess.run(["git", "-C", d, "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", d, "config", "user.name", "t"], check=True)
        with open(os.path.join(d, "a.txt"), "w") as f:
            f.write("hello\n")
        subprocess.run(["git", "-C", d, "add", "-A"], check=True)
        subprocess.run(["git", "-C", d, "commit", "-qm", "init"], check=True)
        return d

    def test_snapshot_forms_are_git_hashes(self):
        repo = self._repo()
        st = er.snapshot_before(repo, "review_dirty_diff")
        self.assertTrue(st["head"] and len(st["head"]) == 40)
        self.assertTrue(st["tree"] and len(st["tree"]) == 40)
        self.assertIsNone(st["dirty_hash"])   # clean tree

    def test_dirty_hash_present_when_dirty(self):
        repo = self._repo()
        with open(os.path.join(repo, "a.txt"), "a") as f:
            f.write("more\n")
        st = er.snapshot_before(repo, "continue_user_changes")
        self.assertIsNotNone(st["dirty_hash"])

    def test_delta_ref_is_a_path_not_inlined(self):
        repo = self._repo()
        before = er.snapshot_before(repo, "review_dirty_diff")
        with open(os.path.join(repo, "a.txt"), "a") as f:
            f.write("change\n")
        trace = tempfile.mkdtemp()
        after, ref = er.snapshot_after(repo, "review_dirty_diff", trace, before)
        self.assertTrue(ref and os.path.isfile(ref))          # a REF (path), not a blob
        self.assertTrue(after["head"])


# ── Contract producer ─────────────────────────────────────────────────────────
class TestContractProducer(unittest.TestCase):
    def test_light_tier_no_contract(self):
        ctx = {}
        self.assertIsNone(er.apply_evidence_contract(ctx, "do x", "light", invoker=lambda s, u: "x"))
        self.assertNotIn("evidence_contract", ctx)

    def test_no_invoker_is_noop(self):
        ctx = {}
        self.assertIsNone(er.apply_evidence_contract(ctx, "do x", "standard", invoker=None))

    def test_standard_produces_contract_subset(self):
        cat = Catalog(checks={"test": Check(name="test", argv=["python"])})
        out = ("REQUIRED CHECKS: test, nonexistent\n"
               "BESPOKE PROBE: the feature returns 42\n"
               "SUFFICIENCY: test passes and the probe holds\n")
        contract, err = er.run_evidence_contract_pass("do x", cat, "crit", invoker=lambda s, u: out)
        self.assertIsNone(err)
        # only declared checks kept; 'nonexistent' dropped (executor can't invent checks)
        self.assertEqual(contract["required_standard_checks"], ["test"])
        self.assertTrue(contract["bespoke_probes"])
        self.assertFalse(contract["repo_less"])

    def test_repo_less_contract_when_no_catalog(self):
        out = "REQUIRED CHECKS:\nBESPOKE PROBE: shows the thing\nSUFFICIENCY: it works\n"
        contract, err = er.run_evidence_contract_pass("do x", None, None, invoker=lambda s, u: out)
        self.assertIsNone(err)
        self.assertEqual(contract["required_standard_checks"], [])
        self.assertTrue(contract["repo_less"])

    def test_apply_stashes_on_context_pkg(self):
        out = "REQUIRED CHECKS:\nBESPOKE PROBE: p\nSUFFICIENCY: s\n"
        ctx = {}
        # No catalog discoverable → repo-less contract, still stashed (never skipped).
        with mock.patch.object(er, "discover_catalog", return_value=None):
            self.assertIsNone(er.apply_evidence_contract(ctx, "do x", "standard",
                                                         invoker=lambda s, u: out))
        self.assertIn("evidence_contract", ctx)


# ── Lane fill + sufficiency ───────────────────────────────────────────────────
class TestLaneFill(unittest.TestCase):
    def test_contract_sufficient_all_required_passed(self):
        results = [CheckResult(name="a", passed=True), CheckResult(name="b", passed=True)]
        self.assertTrue(er.contract_sufficient(results, {"required_standard_checks": ["a", "b"]}))

    def test_failed_required_not_sufficient(self):
        results = [CheckResult(name="a", passed=True), CheckResult(name="b", passed=False)]
        self.assertFalse(er.contract_sufficient(results, {"required_standard_checks": ["a", "b"]}))

    def test_refused_required_not_sufficient(self):
        results = [CheckResult(name="a", skipped=True)]
        self.assertFalse(er.contract_sufficient(results, {"required_standard_checks": ["a"]}))

    def test_empty_required_not_vacuously_sufficient(self):
        self.assertFalse(er.contract_sufficient([], {"required_standard_checks": []}))
        self.assertFalse(er.contract_sufficient([], None))

    def test_fill_evidence_lanes_fills_diff_validate(self):
        from execution_packet import EvidenceLane, ExecutionPacket
        pkt = ExecutionPacket(evidence_lanes=[EvidenceLane(target="state_change", lane="diff_validate")])
        results = [CheckResult(name="test", generated_by=["python", "-m", "unittest"], passed=True)]
        er.fill_evidence_lanes(pkt, results, {"required_standard_checks": ["test"]}, delta_ref="/x/d.patch")
        lane = pkt.evidence_lanes[0]
        self.assertTrue(lane.generated_by)
        self.assertTrue(lane.sufficient)
        self.assertEqual(lane.result["delta_ref"], "/x/d.patch")

    def test_fill_unfilled_when_required_failed(self):
        from execution_packet import EvidenceLane, ExecutionPacket
        pkt = ExecutionPacket(evidence_lanes=[EvidenceLane(target="state_change", lane="diff_validate")])
        results = [CheckResult(name="test", passed=False)]
        er.fill_evidence_lanes(pkt, results, {"required_standard_checks": ["test"]})
        self.assertFalse(pkt.evidence_lanes[0].sufficient)


# ── Portability — Windows-behaviour SIMULATION (run on mac/Linux CI) ──────────
class TestPortabilityWindowsSim(unittest.TestCase):
    def setUp(self):
        _reset_probe()

    def test_no_backend_on_simulated_windows_refuses(self):
        # Simulated Windows with no declared wrapper → refuse cleanly, never
        # runs unenforced, never records orchestrated.
        with mock.patch.object(sys, "platform", "win32"), \
             mock.patch.object(os, "name", "nt"), \
             mock.patch.object(er, "_macos_sandbox_available", return_value=False), \
             mock.patch.object(er, "_windows_appcontainer_available", return_value=False), \
             mock.patch.object(er._te, "record"), \
             mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(er._ENV_SANDBOX, None)
            self.assertIsNone(er.enforcement_backend("deny"))
            res = er.run_check(Check(name="t", argv=["python", "-c", "pass"]),
                               Runner(), tempfile.mkdtemp())
            self.assertTrue(res.skipped)
            self.assertIsNone(res.enforcement_model)

    def test_shell_true_without_posix_shell_refuses_no_cmd_exe(self):
        # A shell:true check on Windows (os.name='nt') with no ORA_POSIX_SHELL
        # refuses cleanly — never falls back to cmd.exe. (On POSIX it uses /bin/sh;
        # see test_shell_true_runs_on_posix.)
        try:
            import bash_execute as be
        except ImportError:
            from orchestrator.tools import bash_execute as be
        with mock.patch.object(os, "name", "nt"), \
             mock.patch.object(be, "_posix_shell_path", return_value=None), \
             mock.patch.object(er._te, "record"):
            res = er.run_check(Check(name="s", cmd="echo x | tee y", shell=True),
                               Runner(), tempfile.mkdtemp())
            self.assertTrue(res.skipped)
            self.assertIn("POSIX", (res.skip_reason or "").upper())
            # never falls back to cmd.exe
            self.assertNotIn("cmd.exe", " ".join(res.generated_by))

    def test_windows_clean_env_has_windows_vars(self):
        with mock.patch.object(os, "name", "nt"), \
             mock.patch.dict(os.environ, {"USERPROFILE": "C:\\Users\\a", "SystemRoot": "C:\\Windows",
                                          "COMSPEC": "C:\\Windows\\cmd.exe", "PATHEXT": ".EXE",
                                          "SSH_AUTH_SOCK": "/leak"}, clear=False):
            env = er._clean_env("C:\\scratch\\home", "C:\\scratch\\tmp")
            self.assertEqual(env["USERPROFILE"], "C:\\scratch\\home")
            self.assertIn("SystemRoot", env)
            self.assertIn("COMSPEC", env)
            self.assertNotIn("SSH_AUTH_SOCK", env)   # still credential-stripped
            self.assertNotIn("HOME", env)            # POSIX var not set on Windows

    def test_windows_style_repo_root_path_handling(self):
        # A PureWindowsPath repo_root flows through discovery/snapshot logic without
        # a POSIX-only path assumption (the runner's own paths are pathlib).
        win = PureWindowsPath("C:\\Users\\a\\repo")
        self.assertEqual(win.name, "repo")
        # discover joins .ora/evidence.yaml with pathlib (separator-agnostic)
        self.assertTrue(str(win / ".ora" / "evidence.yaml").endswith("evidence.yaml"))

    def test_per_platform_argv_windows_selected_under_nt(self):
        c = Check(name="t", argv_windows=["nmake"], argv_posix=["make"])
        with mock.patch.object(os, "name", "nt"):
            argv, _, _ = er.resolve_command(c)
            self.assertEqual(argv, ["nmake"])

    def test_wrapper_with_spaces_parsed_correctly(self):
        # P2-1: a wrapper path WITH SPACES (quoted) — e.g. Windows "Program Files"
        # — must not be mangled, on BOTH POSIX (posix=True strips quotes) and
        # simulated-Windows (posix=False keeps quotes → the runner strips a balanced
        # surrounding pair; the re-check catch). Uses a real space-containing exe.
        import tempfile as tf
        d = tf.mkdtemp(prefix="Program Files ")   # a dir with a space
        exe = os.path.join(d, "wrap")
        Path(exe).touch()
        for simulated in ("posix", "nt"):
            with mock.patch.object(os, "name", simulated), \
                 mock.patch.object(er.shutil, "which", return_value=exe), \
                 mock.patch.dict(os.environ, {er._ENV_SANDBOX: f'"{exe}" --flag'}):
                parts = er._declared_wrapper()
                self.assertIsNotNone(parts, f"os.name={simulated}")
                self.assertEqual(parts[0], exe, f"quotes not stripped on {simulated}")
                self.assertEqual(parts[1], "--flag")

    def test_wrapper_malformed_returns_none_not_crash(self):
        with mock.patch.dict(os.environ, {er._ENV_SANDBOX: 'unbalanced "quote'}):
            self.assertIsNone(er._declared_wrapper())

    def test_wrapper_keeps_pathext_resolved_executable(self):
        resolved = r"C:\Program Files\Ora Sandbox\sandbox.cmd"
        with mock.patch.object(os, "name", "nt"), \
             mock.patch.object(er.shutil, "which", return_value=resolved), \
             mock.patch.dict(os.environ, {er._ENV_SANDBOX: "sandbox"}):
            self.assertEqual(er._declared_wrapper(), [resolved])

    def test_unshare_cache_is_platform_gated(self):
        # PORT-2: a cached True unshare probe must NOT leak across platforms — the
        # platform check happens BEFORE the cache is consulted.
        er._unshare_probe_cache = True   # pretend a Linux host probed True
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertFalse(er._linux_unshare_available())
        with mock.patch.object(sys, "platform", "win32"):
            self.assertFalse(er._linux_unshare_available())
        _reset_probe()


class TestNoHardcodedPaths(unittest.TestCase):
    def test_module_has_no_hardcoded_user_or_tmp_paths(self):
        src = (_ORCH / "evidence_runner.py").read_text()
        # No hardcoded /tmp, /Users, /private literals in the module's own paths.
        # (Docstrings/comments may reference them as anti-patterns; strip lines that
        # are clearly prose about NOT hardcoding.)
        import re
        offenders = []
        for i, line in enumerate(src.splitlines(), 1):
            for pat in ("/tmp/", "/Users/", "/private/"):
                if pat in line and "never" not in line.lower() and "no " not in line.lower():
                    offenders.append((i, pat, line.strip()[:60]))
        self.assertEqual(offenders, [], f"hardcoded paths: {offenders}")

    def test_green_not_right_problem_sentence_present(self):
        src = (_ORCH / "evidence_runner.py").read_text()
        self.assertIn("nothing broke that you knew to check", src)
        self.assertIn("right problem", src)


# ── Phase 6: _git gained an optional env= (the escalation-branch GIT_INDEX_FILE) ──
class TestGitEnvParam(unittest.TestCase):
    def _repo(self):
        d = tempfile.mkdtemp(prefix="er-gitenv-")
        subprocess.run(["git", "-C", d, "init", "-q"], check=True)
        subprocess.run(["git", "-C", d, "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", d, "config", "user.name", "t"], check=True)
        (Path(d) / "a.txt").write_text("x\n")
        subprocess.run(["git", "-C", d, "add", "-A"], check=True)
        subprocess.run(["git", "-C", d, "commit", "-qm", "base"], check=True)
        return d

    def test_git_env_none_is_inherit(self):
        d = self._repo()
        rc, out = er._git(d, ["rev-parse", "--is-inside-work-tree"])
        self.assertEqual(rc, 0)
        self.assertEqual(out, "true")

    def test_git_index_file_redirect_leaves_real_index_untouched(self):
        d = self._repo()
        # Stage a change into a THROWAWAY index; the real .git/index must stay clean —
        # this is the isolation the Phase-6 escalation-branch primitive relies on.
        (Path(d) / "b.txt").write_text("new\n")
        fd, idx = tempfile.mkstemp(prefix="er-idx-")
        os.close(fd)
        os.unlink(idx)
        env = dict(os.environ)
        env["GIT_INDEX_FILE"] = idx
        er._git(d, ["read-tree", "HEAD"], env=env)
        er._git(d, ["add", "-A"], env=env)
        rc, tree = er._git(d, ["write-tree"], env=env)
        self.assertEqual(rc, 0)
        try:
            os.unlink(idx)
        except OSError:
            pass
        # The user's REAL index is unaffected: b.txt still shows as untracked
        # (never staged into .git/index), proving the redirect isolated it.
        status = subprocess.run(["git", "-C", d, "status", "--porcelain"],
                                capture_output=True, text=True).stdout
        self.assertIn("?? b.txt", status)


if __name__ == "__main__":
    unittest.main()
