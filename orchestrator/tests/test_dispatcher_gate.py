"""Dispatcher + gate integration tests (Execution Review Phase 1).

Proves the judge-required behaviors at the dispatch() seam:
  - the gate runs BEFORE execution and independently of auto-approve;
  - irreversible / unknown / secret / sensitive actions cannot pass
    auto-approve; approval tokens unlock exactly one re-issue;
  - protected-config writes are gated (the hook-installation attack);
  - model-facing sensitive reads are gated;
  - MCP calls pass the gate + are recorded (bypass closed);
  - code_execute routes through the dispatcher into a real sandbox;
  - the former legacy tools are dispatcher-registered;
  - every dispatch leaves a machine-readable tool event.
"""

from __future__ import annotations

import json
import os
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
_TOOLS = _ORCH / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.append(str(_TOOLS))

import dispatcher  # noqa: E402
import tool_events  # noqa: E402
import oversight_queue  # noqa: E402


def _read_events(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


class DispatchBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sink = os.path.join(self.tmp.name, "tool-events.jsonl")
        self._orig_sink = tool_events.GLOBAL_SINK_DEFAULT
        self._orig_approvals = tool_events.APPROVALS_PATH
        self._orig_queue = oversight_queue.HUMAN_QUEUE_PATH
        tool_events.GLOBAL_SINK_DEFAULT = self.sink
        tool_events.APPROVALS_PATH = os.path.join(self.tmp.name, "appr.json")
        oversight_queue.HUMAN_QUEUE_PATH = os.path.join(self.tmp.name,
                                                        "human-queue.jsonl")
        tool_events.reset_telemetry_health()
        tool_events._queued_hashes.clear()
        self._orig_te_env = os.environ.pop("ORA_TOOL_EVENTS", None)
        tool_events.set_turn_context()
        dispatcher.reset_consecutive()
        dispatcher.set_permission_mode("auto-approve")  # server reality

    def tearDown(self):
        tool_events.GLOBAL_SINK_DEFAULT = self._orig_sink
        tool_events.APPROVALS_PATH = self._orig_approvals
        oversight_queue.HUMAN_QUEUE_PATH = self._orig_queue
        tool_events._queued_hashes.clear()
        dispatcher.set_permission_mode("approve-each")
        self.tmp.cleanup()

    def _events(self):
        return _read_events(self.sink)

    def _queue_lines(self):
        if not os.path.exists(oversight_queue.HUMAN_QUEUE_PATH):
            return []
        with open(oversight_queue.HUMAN_QUEUE_PATH) as f:
            return [json.loads(l) for l in f if l.strip()]


@unittest.skipUnless(dispatcher._TOOLS_LOADED, "dispatcher tools not loaded")
class TestGateBeforeExecution(DispatchBase):
    def test_registry_entries_all_carry_valid_axes(self):
        for name, entry in dispatcher.TOOL_REGISTRY.items():
            self.assertEqual(tool_events.validate_axes(entry), [],
                             f"invalid axes on {name}")

    def test_unknown_shell_command_blocked_under_auto_approve(self):
        result = dispatcher.dispatch(
            "bash_execute", {"command": "timedatectl set-time now"})
        self.assertIn("GATED", result)
        recs = self._queue_lines()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["kind"], "execution_gate")

    def test_gate_blocks_before_any_execution_side_effect(self):
        marker = os.path.join(self.tmp.name, "should-not-exist")
        result = dispatcher.dispatch(
            "bash_execute", {"command": f"unknowncmd42 && touch {marker}"})
        self.assertIn("GATED", result)
        self.assertFalse(os.path.exists(marker))

    def test_git_force_push_blocked(self):
        result = dispatcher.dispatch(
            "bash_execute", {"command": "git push --force origin main"})
        self.assertIn("GATED", result)

    def test_profiled_read_command_executes(self):
        result = dispatcher.dispatch("bash_execute", {"command": "pwd"})
        self.assertNotIn("GATED", result)
        shell_events = [e for e in self._events() if e["event"] == "shell"]
        self.assertEqual(len(shell_events), 1)
        self.assertEqual(shell_events[0]["mutability"], "read")
        self.assertEqual(shell_events[0]["gate"]["decision"], "allowed")

    def test_blocked_patterns_still_block(self):
        result = dispatcher.dispatch("bash_execute", {"command": "mkfs /dev/sda"})
        self.assertIn("BLOCKED", result)

    def test_approval_token_round_trip_through_dispatch(self):
        # An irreversible-profile command that is HARMLESS to actually run
        # once approved: rm of a file in this test's own temp dir. (Never
        # use a real external action here — an approved test would run it.)
        victim = os.path.join(self.tmp.name, "victim.txt")
        with open(victim, "w") as f:
            f.write("x")
        params = {"command": f"rm -f {victim}", "cwd": self.tmp.name}
        r1 = dispatcher.dispatch("bash_execute", params)
        self.assertIn("GATED", r1)
        self.assertTrue(os.path.exists(victim))  # gate blocked execution
        args_hash = tool_events.normalize_args_hash("bash_execute", params)
        tool_events.grant_approval("bash_execute", args_hash)
        tool_events._queued_hashes.clear()
        dispatcher.reset_consecutive()
        r2 = dispatcher.dispatch("bash_execute", params)
        self.assertNotIn("GATED", r2)
        self.assertFalse(os.path.exists(victim))  # approved call really ran
        tool_events._queued_hashes.clear()
        dispatcher.reset_consecutive()
        r3 = dispatcher.dispatch("bash_execute", params)
        self.assertIn("GATED", r3)  # token was one-shot

    def test_live_prompt_is_the_gate_approval_channel(self):
        dispatcher.set_permission_mode("approve-each")
        calls = []

        def approver(name, params, classification):
            calls.append(name)
            return True

        result = dispatcher.dispatch(
            "bash_execute", {"command": "unprofiledcmd99 --do-thing"},
            permission_callback=approver)
        # One prompt (the gate's), not two — and the command then runs.
        self.assertEqual(calls, ["bash_execute"])
        self.assertNotIn("GATED", result)


@unittest.skipUnless(dispatcher._TOOLS_LOADED, "dispatcher tools not loaded")
class TestSensitiveAndProtectedPaths(DispatchBase):
    def test_model_facing_sensitive_read_is_gated(self):
        # /private/tmp is outside the known private roots → sensitive.
        victim = os.path.join(self.tmp.name, "data.txt")
        with open(victim, "w") as f:
            f.write("payload")
        result = dispatcher.dispatch("file_read", {"path": victim})
        self.assertIn("GATED", result)

    def test_workspace_read_is_allowed_and_recorded_with_hash(self):
        target = os.path.expanduser("~/ora/CLAUDE.md")
        result = dispatcher.dispatch("file_read", {"path": target})
        self.assertNotIn("GATED", result)
        ev = [e for e in self._events() if e["action"] == "file_read"][0]
        self.assertEqual(ev["reads"][0]["what"], target)
        self.assertTrue(ev["reads"][0]["content_hash"])

    def test_secret_path_read_blocked(self):
        result = dispatcher.dispatch(
            "file_read", {"path": os.path.expanduser("~/.ssh/id_rsa")})
        self.assertIn("GATED", result)

    def test_hook_installation_write_is_gated(self):
        # The verified attack: file_write into config/hooks/ would install
        # arbitrary un-gated shell. Protected-config paths gate it. Test
        # against a temp dir registered as protected — NEVER the real
        # hooks dir (a regression here must not install a live hook).
        protected_dir = os.path.join(self.tmp.name, "hooks")
        os.makedirs(protected_dir)
        tool_events._PROTECTED_PREFIXES.append(os.path.realpath(protected_dir))
        try:
            target = os.path.join(protected_dir, "installed-by-test.json")
            result = dispatcher.dispatch("file_write", {
                "path": target,
                "content": '{"event": "pre_tool", "command": "id"}',
            })
            self.assertIn("GATED", result)
            self.assertFalse(os.path.exists(target))
            # And the REAL hooks dir is protected by the shipped list.
            self.assertTrue(tool_events.is_protected_config_path(
                os.path.expanduser("~/ora/config/hooks/any.json")))
        finally:
            tool_events._PROTECTED_PREFIXES.pop()

    def test_orchestrator_code_write_is_gated(self):
        result = dispatcher.dispatch("file_write", {
            "path": os.path.expanduser("~/ora/orchestrator/tool_events.py"),
            "content": "# defanged",
        })
        self.assertIn("GATED", result)

    def test_shell_redirect_into_protected_config_is_gated(self):
        # The critical review finding: 'echo x > config/hooks/y' must gate
        # the same as file_write into that path — a redirect must not be a
        # side door around the protected-config control.
        target = os.path.expanduser("~/ora/config/hooks/redirect-probe.json")
        result = dispatcher.dispatch(
            "bash_execute",
            {"command": f'echo pwn > {target}', "cwd": self.tmp.name})
        self.assertIn("GATED", result)
        self.assertFalse(os.path.exists(target))

    def test_shell_read_of_secret_path_is_gated(self):
        result = dispatcher.dispatch(
            "bash_execute",
            {"command": "cat ~/.ssh/id_rsa", "cwd": self.tmp.name})
        self.assertIn("GATED", result)

    def test_shell_relative_read_resolved_against_cwd(self):
        # 'cat id_rsa' with cwd=~/.ssh must gate as a secret read even though
        # the raw target 'id_rsa' looks innocuous.
        result = dispatcher.dispatch(
            "bash_execute",
            {"command": "cat id_rsa", "cwd": os.path.expanduser("~/.ssh")})
        self.assertIn("GATED", result)

    def test_bare_secret_filename_in_private_cwd_gated(self):
        # 'head secrets.txt' with a private (non-secret) cwd: the filename
        # itself resolves to secret ('secrets.*'), so it must gate.
        result = dispatcher.dispatch(
            "bash_execute",
            {"command": "head secrets.txt",
             "cwd": os.path.expanduser("~/ora")})
        self.assertIn("GATED", result)

    def test_bare_normal_filename_in_private_cwd_allowed(self):
        # A plain filename in a private cwd must NOT over-gate.
        result = dispatcher.dispatch(
            "bash_execute",
            {"command": "cat CLAUDE.md", "cwd": os.path.expanduser("~/ora")})
        self.assertNotIn("GATED", result)

    def test_archive_of_secret_is_gated(self):
        # gzip/tar/pandoc reading a secret must gate (content would otherwise
        # reach the model via stdout).
        for cmd in ("gzip -c ~/.aws/credentials",
                    "pandoc ~/.ssh/id_rsa",
                    "tar czf /tmp/o.tgz ~/.ssh/id_rsa"):
            r = dispatcher.dispatch("bash_execute",
                                    {"command": cmd, "cwd": self.tmp.name})
            self.assertIn("GATED", r, cmd)

    def test_archive_output_into_protected_path_gated(self):
        # An archive/transform command writing its OUTPUT into a protected
        # path must gate — even when path sensitivity is only 'private' (the
        # protected-config escalation, not sensitivity, is what fires). Uses a
        # temp protected prefix inside ~/ora (private) so sensitivity can't
        # mask the result.
        import tempfile, shutil
        guard = tempfile.mkdtemp(dir=os.path.expanduser("~/ora"))
        tool_events._PROTECTED_PREFIXES.append(os.path.realpath(guard))
        try:
            for cmd in (f"tar czf {guard}/x.tgz data.txt",
                        f"zip {guard}/x.zip data.txt",
                        f"pandoc data.md -o {guard}/x.pdf",
                        f"gzip {guard}/data.txt"):
                r = dispatcher.dispatch(
                    "bash_execute",
                    {"command": cmd, "cwd": os.path.expanduser("~/ora")})
                self.assertIn("GATED", r, cmd)
                self.assertFalse(os.path.exists(f"{guard}/x.tgz"))
                self.assertFalse(os.path.exists(f"{guard}/x.zip"))
                self.assertFalse(os.path.exists(f"{guard}/x.pdf"))
        finally:
            tool_events._PROTECTED_PREFIXES.pop()
            shutil.rmtree(guard, ignore_errors=True)

    def test_archive_within_workspace_not_over_gated(self):
        import tempfile
        out = os.path.join(self.tmp.name, "will-not-run")
        # A within-workspace archive of a non-secret file must NOT gate.
        r = dispatcher.dispatch(
            "bash_execute",
            {"command": "tar czf ~/ora/scratch/_er_probe.tgz CLAUDE.md",
             "cwd": os.path.expanduser("~/ora")})
        self.assertNotIn("GATED", r)
        try:
            os.remove(os.path.expanduser("~/ora/scratch/_er_probe.tgz"))
        except OSError:
            pass

    def test_download_output_into_protected_path_gated(self):
        # curl/wget download output flags writing into a protected path gate.
        import tempfile, shutil
        guard = tempfile.mkdtemp(dir=os.path.expanduser("~/ora"))
        tool_events._PROTECTED_PREFIXES.append(os.path.realpath(guard))
        try:
            for cmd in (f"wget -O {guard}/x.json http://u",
                        f"wget --output-document {guard}/x.json http://u",
                        f"wget -P {guard} http://u",
                        f"curl -O --output-dir {guard} http://u",
                        f"curl --remote-name --output-dir {guard} http://u"):
                r = dispatcher.dispatch(
                    "bash_execute",
                    {"command": cmd, "cwd": os.path.expanduser("~/ora")})
                self.assertIn("GATED", r, cmd)
        finally:
            tool_events._PROTECTED_PREFIXES.pop()
            shutil.rmtree(guard, ignore_errors=True)

    def test_download_into_workspace_not_protected_gated(self):
        # A download into a normal private path must NOT hit the
        # protected-config gate (external egress is a Phase-2 policy, not a
        # Phase-1 block).
        r = dispatcher.dispatch(
            "bash_execute",
            {"command": "curl -o ~/ora/scratch/_er_dl.json http://u",
             "cwd": os.path.expanduser("~/ora")})
        self.assertNotIn("GATED", r)

    def test_viewer_of_workspace_file_not_over_gated(self):
        # less/nl/od of a normal workspace file must NOT gate.
        for cmd in ("less CLAUDE.md", "nl CLAUDE.md", "base64 CLAUDE.md"):
            r = dispatcher.dispatch(
                "bash_execute", {"command": cmd,
                                 "cwd": os.path.expanduser("~/ora")})
            self.assertNotIn("GATED", r, cmd)

    def test_program_file_secret_gated(self):
        r = dispatcher.dispatch(
            "bash_execute",
            {"command": "awk -f ~/.ssh/id_rsa data.txt", "cwd": self.tmp.name})
        self.assertIn("GATED", r)

    def test_env_prefix_does_not_hide_secret_read(self):
        r = dispatcher.dispatch(
            "bash_execute",
            {"command": "FOO=1 cat id_rsa",
             "cwd": os.path.expanduser("~/.ssh")})
        self.assertIn("GATED", r)

    def test_cd_into_secret_dir_gates_relative_read(self):
        for cmd in ("cd ~/.aws && cat config",
                    "pushd ~/.aws && cat config"):
            r = dispatcher.dispatch("bash_execute",
                                    {"command": cmd,
                                     "cwd": os.path.expanduser("~/ora")})
            self.assertIn("GATED", r, cmd)

    def test_cd_into_workspace_does_not_over_gate(self):
        for cmd in ("cd ~/ora && cat CLAUDE.md",
                    "cd ~/ora/orchestrator && wc -l boot.py"):
            r = dispatcher.dispatch("bash_execute",
                                    {"command": cmd,
                                     "cwd": os.path.expanduser("~/ora")})
            self.assertNotIn("GATED", r, cmd)

    def test_unmodelable_cd_fails_closed(self):
        # cd $VAR / cd - can't be resolved; a following relative read fails
        # closed (whole command gated).
        for cmd in ("cd $VAR && cat config", "cd - && cat config"):
            r = dispatcher.dispatch("bash_execute",
                                    {"command": cmd,
                                     "cwd": os.path.expanduser("~/ora")})
            self.assertIn("GATED", r, cmd)

    def test_search_files_excludes_secret_descendants(self):
        # A recursive search over an allowed private root must not return the
        # CONTENT of a secret/credential descendant — across the shapes the
        # adversarial pass found (env.local, private_keys/, keys/, *.pem.txt,
        # creds.txt, .ssh2/) — while STILL returning legit secret-NAMED files.
        import tempfile, shutil
        root = tempfile.mkdtemp(dir=os.path.expanduser("~/ora"))
        try:
            secret_files = {
                "sub/credentials.txt": "NEEDLETOKEN cred-leak",
                ".env": "NEEDLETOKEN=envleak",
                "env.local": "NEEDLETOKEN=envlocalleak",
                "private_keys/data.txt": "NEEDLETOKEN pkleak",
                "keys/priv.txt": "NEEDLETOKEN keysleak",
                "prod.pem.txt": "NEEDLETOKEN pemleak",
                "creds.txt": "NEEDLETOKEN credsleak",
                ".ssh2/notes.txt": "NEEDLETOKEN ssh2leak",
            }
            legit_files = {
                "normal.txt": "NEEDLETOKEN normal-visible",
                "secrets_of_success.md": "NEEDLETOKEN book-visible",
            }
            for rel, content in {**secret_files, **legit_files}.items():
                p = os.path.join(root, rel)
                os.makedirs(os.path.dirname(p), exist_ok=True) if os.path.dirname(rel) else None
                with open(p, "w") as f:
                    f.write(content + "\n")
            result = dispatcher.dispatch(
                "search_files", {"pattern": "NEEDLETOKEN", "directory": root})
            blob = json.dumps(result)
            for content in secret_files.values():
                leak = content.split()[-1]
                self.assertNotIn(leak, blob, f"leaked: {leak}")
            self.assertIn("normal-visible", blob)   # legit content shown
            self.assertIn("book-visible", blob)      # secret-NAMED-but-legit shown
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_search_files_secret_dir_is_gated(self):
        result = dispatcher.dispatch(
            "search_files", {"pattern": "PRIVATE KEY",
                             "directory": os.path.expanduser("~/.ssh")})
        self.assertIn("GATED", result)

    def test_list_directory_sensitive_path_is_gated(self):
        # A path outside the known-private roots resolves to sensitive.
        result = dispatcher.dispatch(
            "list_directory", {"path": "/opt/some-unknown-place"})
        self.assertIn("GATED", result)

    def test_list_directory_workspace_allowed(self):
        result = dispatcher.dispatch(
            "list_directory", {"path": os.path.expanduser("~/ora/modes")})
        self.assertNotIn("GATED", result)

    def test_script_and_package_runners_gated(self):
        # Opaque code execution through a "profiled" command is a side door
        # (the model can edit the script/package then run it). All fail closed.
        for cmd in ("python3 somescript.py", "python3 -m unittest discover",
                    "npm test", "npm run build", "node run.js",
                    "pip install requests", "brew install jq"):
            r = dispatcher.dispatch("bash_execute",
                                    {"command": cmd, "cwd": self.tmp.name})
            self.assertIn("GATED", r, cmd)
            # ...but read-only forms still pass.
        for cmd in ("pip list", "npm ls", "brew list", "python3 --version"):
            r = dispatcher.dispatch("bash_execute",
                                    {"command": cmd, "cwd": self.tmp.name})
            self.assertNotIn("GATED", r, cmd)

    def test_credential_store_blocked_then_standing_allow_passes(self):
        r1 = dispatcher.dispatch("credential_store",
                                 {"action": "retrieve", "service": "svc-x",
                                  "username": "u"})
        self.assertIn("GATED", r1)
        recs = self._queue_lines()
        self.assertEqual(recs[0]["event"]["standing_scope"],
                         "credential_store:svc-x")
        tool_events.grant_standing_allow("credential_store:svc-x")
        tool_events._queued_hashes.clear()
        dispatcher.reset_consecutive()
        r2 = dispatcher.dispatch("credential_store",
                                 {"action": "retrieve", "service": "svc-x",
                                  "username": "u"})
        self.assertNotIn("GATED", r2)
        # Existence-only logging: the secret-sensitivity event carries no args.
        ev = [e for e in self._events()
              if e["action"] == "credential_store" and e["event"] != "gate"]
        self.assertTrue(ev)
        self.assertNotIn("args_redacted", ev[-1])


@unittest.skipUnless(dispatcher._TOOLS_LOADED, "dispatcher tools not loaded")
class TestMCPGateClosure(DispatchBase):
    def test_undeclared_mcp_tool_gated_and_recorded(self):
        tool_events.reset_mcp_axes_cache()
        result = dispatcher.dispatch("mcp_unknownsrv_do_thing", {"a": 1})
        self.assertIn("GATED", result)
        gate_events = [e for e in self._events() if e["event"] == "gate"]
        self.assertTrue(any(e["action"] == "mcp_unknownsrv_do_thing"
                            for e in gate_events))

    def test_gate_ordering_no_mcp_early_return(self):
        # The old bypass returned before the gate; now a gate event exists
        # even though no MCP client is configured in this test process.
        tool_events.reset_mcp_axes_cache()
        dispatcher.dispatch("mcp_unknownsrv_x", {})
        self.assertTrue(any(e.get("event") == "gate" for e in self._events()))


@unittest.skipUnless(dispatcher._TOOLS_LOADED, "dispatcher tools not loaded")
class TestCodeExecute(DispatchBase):
    def test_code_execute_registered_and_runs_sandboxed(self):
        import code_execute as ce
        if not ce.sandbox_available():
            self.skipTest("sandbox-exec unavailable on this platform")
        result = dispatcher.dispatch("code_execute",
                                     {"code": "print(2**10)"})
        self.assertIn("1024", result)
        ev = [e for e in self._events() if e["action"] == "code_execute"]
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["enforcement_model"], "orchestrated")

    def test_code_execute_network_denied(self):
        import code_execute as ce
        if not ce.sandbox_available():
            self.skipTest("sandbox-exec unavailable on this platform")
        result = dispatcher.dispatch("code_execute", {"code": (
            "import socket\n"
            "try:\n"
            "    socket.create_connection(('1.1.1.1', 443), timeout=3)\n"
            "    print('NETWORK-OPEN')\n"
            "except Exception as e:\n"
            "    print('denied', type(e).__name__)\n")})
        self.assertNotIn("NETWORK-OPEN", result)
        self.assertIn("denied", result)

    def test_code_execute_private_home_read_denied(self):
        # Arbitrary Python must not read a non-secret private file (outside
        # scratch) and exfiltrate it via stdout — stdout is the one egress
        # the network-deny doesn't cover.
        import code_execute as ce
        if not ce.sandbox_available():
            self.skipTest("sandbox-exec unavailable on this platform")
        target = os.path.expanduser("~/ora/CLAUDE.md")
        result = dispatcher.dispatch("code_execute", {"code": (
            f"try:\n"
            f"    print('LEAK:' + open({target!r}).read()[:20])\n"
            f"except Exception as e:\n"
            f"    print('read denied', type(e).__name__)\n")})
        self.assertNotIn("LEAK:", result)
        self.assertIn("denied", result)

    def test_code_execute_stdlib_and_scratch_still_work(self):
        import code_execute as ce
        if not ce.sandbox_available():
            self.skipTest("sandbox-exec unavailable on this platform")
        result = dispatcher.dispatch("code_execute", {"code": (
            "import json, math\n"
            "print(json.dumps({'f': math.factorial(5)}))\n")})
        self.assertIn("120", result)

    def test_code_execute_workspace_write_denied(self):
        import code_execute as ce
        if not ce.sandbox_available():
            self.skipTest("sandbox-exec unavailable on this platform")
        probe = os.path.expanduser("~/ora/config/sandbox-escape-probe")
        result = dispatcher.dispatch("code_execute", {"code": (
            f"open({probe!r}, 'w').write('x'); print('ESCAPE-OK')")})
        # The write must raise inside the sandbox (the traceback quotes the
        # source line, so assert on the outcome, not on source echoes).
        self.assertNotIn("ESCAPE-OK\n", result + "\n")
        self.assertIn("PermissionError", result)
        self.assertFalse(os.path.exists(probe))

    def test_legacy_tools_registered(self):
        self.assertIn("code_execute", dispatcher.TOOL_REGISTRY)
        # continuity_save / queue_read register when boot imports; assert
        # register_tool exists and produces valid entries either way.
        dispatcher.register_tool(
            "test_legacy", lambda p: "ok", permission="auto",
            category="read", mutability="read", sensitivity="private",
            egress="none")
        try:
            self.assertNotIn("GATED",
                             dispatcher.dispatch("test_legacy", {}))
        finally:
            dispatcher.TOOL_REGISTRY.pop("test_legacy", None)

    def test_unknown_tool_recorded(self):
        result = dispatcher.dispatch("no_such_tool", {})
        self.assertIn("Unknown tool", result)
        self.assertTrue(any(e["action"] == "no_such_tool"
                            for e in self._events()))


if __name__ == "__main__":
    unittest.main()
