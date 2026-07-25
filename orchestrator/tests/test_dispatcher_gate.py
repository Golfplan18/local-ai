"""Hermetic dispatcher + gate contract tests (Execution Review Phase 1).

Proves the judge-required behaviors at the dispatch() seam:
  - the gate runs BEFORE execution and independently of auto-approve;
  - irreversible / unknown / secret / sensitive actions cannot pass
    auto-approve; approval tokens unlock exactly one re-issue;
  - protected-config writes are gated (the hook-installation attack);
  - model-facing sensitive reads are gated;
  - MCP calls pass the gate + are recorded (bypass closed);
  - every dispatch leaves a machine-readable tool event.

The real matcher, dispatcher, gate, approval, and event pipeline run here.
Host-facing execution is replaced at its boundary: no shell, network, OS
keyring, user hook, external grep, or live-log retirement runs in this suite.
Real code-execute sandbox coverage lives in test_dispatcher_code_execute.py;
the native Windows dispatcher/shell seam lives in
test_dispatcher_windows_live.py.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
import tempfile
import unittest
from unittest import mock

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
import bash_execute  # noqa: E402
import file_ops  # noqa: E402
import search_files  # noqa: E402


def _read_events(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


class DispatchBase(unittest.TestCase):
    def setUp(self):
        # Keep absolute positive-path fixtures under the portable home root.
        # The legacy classifier treats /var and /private as sensitive before
        # consulting the modeled workspace, which would make a default macOS
        # temp directory prompt for the wrong reason.
        self.tmp = tempfile.TemporaryDirectory(dir=str(Path.home()))
        self.workspace = os.path.join(self.tmp.name, "workspace")
        os.makedirs(self.workspace)
        self.sink = os.path.join(self.tmp.name, "tool-events.jsonl")
        self._orig_sink = tool_events.GLOBAL_SINK_DEFAULT
        self._orig_approvals = tool_events.APPROVALS_PATH
        self._orig_queue = oversight_queue.HUMAN_QUEUE_PATH
        self.runtime_workspace = dispatcher.WORKSPACE
        self._orig_permission_mode = dispatcher._permission_mode
        self._orig_approved_categories = set(dispatcher._approved_categories)
        self._orig_consecutive = (dispatcher._consecutive_tool,
                                  dispatcher._consecutive_count)
        self._orig_queued_hashes = set(tool_events._queued_hashes)
        self._orig_mcp_axes_cache = tool_events._mcp_axes_cache
        self._orig_telemetry_health = tool_events.get_telemetry_health()
        tool_events.GLOBAL_SINK_DEFAULT = self.sink
        tool_events.APPROVALS_PATH = os.path.join(self.tmp.name, "appr.json")
        oversight_queue.HUMAN_QUEUE_PATH = os.path.join(self.tmp.name,
                                                        "human-queue.jsonl")
        tool_events.reset_telemetry_health()
        tool_events._queued_hashes.clear()
        self._orig_te_env = os.environ.pop("ORA_TOOL_EVENTS", None)
        self._orig_te_path_env = os.environ.pop("ORA_TOOL_EVENTS_PATH", None)
        self._turn_token = tool_events.set_turn_context()
        dispatcher.reset_consecutive()
        dispatcher.set_permission_mode("auto-approve")  # server reality

        # Give the fixture a private, allowed workspace without mutating the
        # checkout under test. Leave the temp parent unregistered so tests can
        # still exercise a genuinely sensitive/unrecognized path.
        self._private_root = tool_events._cmp_key(self.workspace)
        tool_events._PRIVATE_ROOTS.append(self._private_root)
        dispatcher.ALLOWED_BASES.append(self.workspace)
        file_ops.ALLOWED_BASES.append(self.workspace)

        self.shell_calls = []

        def fake_execute(command, **kwargs):
            self.shell_calls.append((command, kwargs))
            return {
                "stdout": f"[hermetic shell stub] {command}\n",
                "stderr": "",
                "returncode": 0,
                "timed_out": False,
                "truncated": False,
            }

        self._patches = [
            # Exercise POSIX grammar matching even on Windows; real shell
            # availability belongs to the native-Windows live suite.
            mock.patch.object(bash_execute, "_posix_shell_available",
                              return_value=True),
            mock.patch.object(dispatcher, "execute_command",
                              side_effect=fake_execute),
            mock.patch.object(dispatcher, "credential_store",
                              return_value="No credential found: svc-x/u"),
            mock.patch.object(dispatcher, "fire_hooks", return_value=[]),
            mock.patch.object(dispatcher,
                              "_retire_legacy_session_logs_once",
                              return_value=None),
            mock.patch.object(search_files, "_grep_available",
                              return_value=False),
            mock.patch.object(dispatcher, "WORKSPACE", self.workspace),
            mock.patch.object(bash_execute, "WORKSPACE", self.workspace),
        ]
        for patcher in self._patches:
            patcher.start()

    def tearDown(self):
        try:
            for patcher in reversed(self._patches):
                patcher.stop()
            tool_events.GLOBAL_SINK_DEFAULT = self._orig_sink
            tool_events.APPROVALS_PATH = self._orig_approvals
            oversight_queue.HUMAN_QUEUE_PATH = self._orig_queue
            tool_events._queued_hashes.clear()
            tool_events._queued_hashes.update(self._orig_queued_hashes)
            tool_events._mcp_axes_cache = self._orig_mcp_axes_cache
            with tool_events._health_lock:
                tool_events._telemetry_failures = \
                    self._orig_telemetry_health["failures"]
                tool_events._telemetry_last_error = \
                    self._orig_telemetry_health["last_error"]
            tool_events.reset_turn_context(self._turn_token)
            if self._orig_te_env is None:
                os.environ.pop("ORA_TOOL_EVENTS", None)
            else:
                os.environ["ORA_TOOL_EVENTS"] = self._orig_te_env
            if self._orig_te_path_env is None:
                os.environ.pop("ORA_TOOL_EVENTS_PATH", None)
            else:
                os.environ["ORA_TOOL_EVENTS_PATH"] = self._orig_te_path_env
            dispatcher._permission_mode = self._orig_permission_mode
            dispatcher._approved_categories.clear()
            dispatcher._approved_categories.update(
                self._orig_approved_categories)
            (dispatcher._consecutive_tool,
             dispatcher._consecutive_count) = self._orig_consecutive
            dispatcher.ALLOWED_BASES.remove(self.workspace)
            file_ops.ALLOWED_BASES.remove(self.workspace)
            tool_events._PRIVATE_ROOTS.remove(self._private_root)
        finally:
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
        self.assertIn("SYSTEM PROTECTION", result)
        self.assertEqual(self.shell_calls, [])
        recs = self._queue_lines()
        self.assertEqual(recs, [])

    def test_gate_blocks_before_any_execution_side_effect(self):
        marker = os.path.join(self.tmp.name, "should-not-exist")
        result = dispatcher.dispatch(
            "bash_execute", {"command": f"unknowncmd42 && touch {marker}"})
        self.assertIn("SYSTEM PROTECTION", result)
        self.assertEqual(self.shell_calls, [])
        self.assertFalse(os.path.exists(marker))

    def test_git_force_push_blocked(self):
        result = dispatcher.dispatch(
            "bash_execute", {"command": "git push --force origin main"})
        self.assertIn("SYSTEM PROTECTION", result)
        self.assertEqual(self.shell_calls, [])

    def test_profiled_read_command_executes(self):
        result = dispatcher.dispatch("bash_execute", {"command": "pwd"})
        self.assertNotIn("GATED", result)
        self.assertEqual([call[0] for call in self.shell_calls], ["pwd"])
        self.assertEqual(self.shell_calls[0][1], {
            "timeout": 60,
            "cwd": None,
            "background": False,
            "max_output_chars": 10000,
        })
        shell_events = [e for e in self._events() if e["event"] == "shell"]
        self.assertEqual(len(shell_events), 1)
        self.assertEqual(shell_events[0]["mutability"], "read")
        self.assertEqual(shell_events[0]["gate"]["decision"], "allowed")

    def test_blocked_patterns_still_block(self):
        result = dispatcher.dispatch("bash_execute", {"command": "mkfs /dev/sda"})
        self.assertIn("SYSTEM PROTECTION", result)
        self.assertEqual(self.shell_calls, [])

    def test_approval_token_round_trip_through_dispatch(self):
        # Approval unlocks exactly one trip through the hermetic handler.
        # No real rm is run: the contract is the dispatch count 0 -> 1 -> 1.
        victim = os.path.join(self.workspace, "victim.txt")
        with open(victim, "w") as f:
            f.write("x")
        params = {"command": f"rm -f {shlex.quote(victim)}",
                  "cwd": self.workspace}
        r1 = dispatcher.dispatch("bash_execute", params)
        self.assertIn("GATED", r1)
        self.assertEqual(len(self.shell_calls), 0)
        self.assertTrue(os.path.exists(victim))
        queued = self._queue_lines()
        self.assertEqual(len(queued), 1)
        approval = tool_events.resolve_gate_entry(queued[0], approve=True)
        self.assertIn("One-shot token", approval)
        dispatcher.reset_consecutive()
        r2 = dispatcher.dispatch("bash_execute", params)
        self.assertNotIn("GATED", r2)
        self.assertEqual(len(self.shell_calls), 1)
        self.assertTrue(os.path.exists(victim))  # no host process ran
        tool_events._queued_hashes.clear()
        dispatcher.reset_consecutive()
        r3 = dispatcher.dispatch("bash_execute", params)
        self.assertIn("GATED", r3)  # token was one-shot
        self.assertEqual(len(self.shell_calls), 1)

    def test_live_prompt_is_the_gate_approval_channel(self):
        dispatcher.set_permission_mode("approve-each")
        calls = []

        def approver(name, params, classification):
            calls.append(name)
            return True

        result = dispatcher.dispatch(
            "bash_execute", {"command": "rm exact-reviewed-target"},
            permission_callback=approver)
        # One prompt (the gate's), not two — and the command then runs.
        self.assertEqual(calls, ["bash_execute"])
        self.assertNotIn("GATED", result)
        self.assertEqual([call[0] for call in self.shell_calls],
                         ["rm exact-reviewed-target"])


@unittest.skipUnless(dispatcher._TOOLS_LOADED, "dispatcher tools not loaded")
class TestSensitiveAndProtectedPaths(DispatchBase):
    def test_model_facing_sensitive_read_is_gated(self):
        # The temp parent is outside the registered private workspace.
        victim = os.path.join(self.tmp.name, "data.txt")
        with open(victim, "w") as f:
            f.write("payload")
        result = dispatcher.dispatch("file_read", {"path": victim})
        self.assertIn("GATED", result)
        gate = [e for e in self._events() if e.get("event") == "gate"][-1]
        self.assertEqual(gate["sensitivity"], "sensitive")
        self.assertIn("sensitive", gate["gate"]["why"])

    def test_workspace_read_is_allowed_and_recorded_with_hash(self):
        target = os.path.join(self.workspace, "fixture.txt")
        with open(target, "w") as f:
            f.write("fixture payload\n")
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
        protected_dir = os.path.join(self.workspace, "hooks")
        os.makedirs(protected_dir)
        tool_events._PROTECTED_PREFIXES.append(
            tool_events._cmp_key(protected_dir))
        try:
            target = os.path.join(protected_dir, "installed-by-test.json")
            result = dispatcher.dispatch("file_write", {
                "path": target,
                "content": '{"event": "pre_tool", "command": "id"}',
            })
            self.assertIn("GATED", result)
            self.assertFalse(os.path.exists(target))
            gate = [e for e in self._events()
                    if e.get("event") == "gate"][-1]
            self.assertEqual(gate["mutability"], "irreversible")
            self.assertEqual(gate["sensitivity"], "private")
            self.assertIn("irreversible", gate["gate"]["why"])
            # And the checkout's hooks dir is protected by the shipped list.
            self.assertTrue(tool_events.is_protected_config_path(
                os.path.join(self.runtime_workspace, "config", "hooks",
                             "any.json")))
        finally:
            tool_events._PROTECTED_PREFIXES.pop()

    def test_orchestrator_code_write_is_gated(self):
        result = dispatcher.dispatch("file_write", {
            "path": os.path.join(self.runtime_workspace, "orchestrator",
                                 "tool_events.py"),
            "content": "# defanged",
        })
        self.assertIn("SYSTEM PROTECTION", result)

    def test_shell_redirect_into_protected_config_is_gated(self):
        # The critical review finding: 'echo x > config/hooks/y' must gate
        # the same as file_write into that path — a redirect must not be a
        # side door around the protected-config control.
        target = os.path.join(self.runtime_workspace, "config", "hooks",
                              "redirect-probe.json")
        result = dispatcher.dispatch(
            "bash_execute",
            {"command": f'echo pwn > {shlex.quote(target)}',
             "cwd": self.workspace})
        self.assertIn("SYSTEM PROTECTION", result)
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
             "cwd": self.workspace})
        self.assertIn("GATED", result)

    def test_bare_normal_filename_in_private_cwd_allowed(self):
        # A plain filename in a private cwd must NOT over-gate.
        target = os.path.join(self.workspace, "ordinary.txt")
        with open(target, "w") as f:
            f.write("ordinary\n")
        result = dispatcher.dispatch(
            "bash_execute",
            {"command": "cat ordinary.txt", "cwd": self.workspace})
        self.assertNotIn("GATED", result)
        self.assertEqual(self.shell_calls[-1][0], "cat ordinary.txt")

    def test_archive_of_secret_is_gated(self):
        # gzip/tar/pandoc reading a secret must gate (content would otherwise
        # reach the model via stdout).
        archive = shlex.quote(os.path.join(self.workspace, "o.tgz"))
        for cmd in ("gzip -c ~/.aws/credentials",
                    "pandoc ~/.ssh/id_rsa",
                    f"tar czf {archive} ~/.ssh/id_rsa"):
            r = dispatcher.dispatch("bash_execute",
                                    {"command": cmd, "cwd": self.workspace})
            self.assertIn("GATED", r, cmd)
        self.assertEqual(self.shell_calls, [])

    def test_archive_output_into_protected_path_gated(self):
        # An archive/transform command writing its OUTPUT into a protected
        # path must gate — even when path sensitivity is only 'private' (the
        # protected-config escalation, not sensitivity, is what fires). Uses a
        # temp protected prefix inside the private fixture workspace so
        # sensitivity cannot mask the protected-config reason.
        import shutil
        guard = os.path.join(self.workspace, "archive-protected")
        os.makedirs(guard)
        tool_events._PROTECTED_PREFIXES.append(tool_events._cmp_key(guard))
        try:
            qguard = shlex.quote(guard)
            for cmd in (f"tar czf {qguard}/x.tgz data.txt",
                        f"zip {qguard}/x.zip data.txt",
                        f"pandoc data.md -o {qguard}/x.pdf",
                        f"gzip {qguard}/data.txt"):
                r = dispatcher.dispatch(
                    "bash_execute",
                    {"command": cmd, "cwd": self.workspace})
                self.assertIn("GATED", r, cmd)
                self.assertFalse(os.path.exists(f"{guard}/x.tgz"))
                self.assertFalse(os.path.exists(f"{guard}/x.zip"))
                self.assertFalse(os.path.exists(f"{guard}/x.pdf"))
        finally:
            tool_events._PROTECTED_PREFIXES.pop()
            shutil.rmtree(guard, ignore_errors=True)

    def test_archive_within_workspace_not_over_gated(self):
        # A within-workspace archive of a non-secret file must NOT gate.
        output = shlex.quote(os.path.join(self.workspace, "output.tgz"))
        command = f"tar czf {output} ordinary.txt"
        r = dispatcher.dispatch(
            "bash_execute", {"command": command, "cwd": self.workspace})
        self.assertNotIn("GATED", r)
        self.assertEqual(self.shell_calls[-1][0], command)

    def test_download_output_into_protected_path_gated(self):
        # curl/wget download output flags writing into a protected path gate.
        import shutil
        guard = os.path.join(self.workspace, "download-protected")
        os.makedirs(guard)
        tool_events._PROTECTED_PREFIXES.append(tool_events._cmp_key(guard))
        try:
            qguard = shlex.quote(guard)
            for cmd in (f"wget -O {qguard}/x.json http://u",
                        f"wget --output-document {qguard}/x.json http://u",
                        f"wget -P {qguard} http://u",
                        f"curl -O --output-dir {qguard} http://u",
                        f"curl --remote-name --output-dir {qguard} http://u"):
                r = dispatcher.dispatch(
                    "bash_execute",
                    {"command": cmd, "cwd": self.workspace})
                self.assertIn("GATED", r, cmd)
            self.assertEqual(self.shell_calls, [])
        finally:
            tool_events._PROTECTED_PREFIXES.pop()
            shutil.rmtree(guard, ignore_errors=True)

    def test_download_into_workspace_not_protected_gated(self):
        # A download into a normal private path must NOT hit the
        # protected-config gate (external egress is a Phase-2 policy, not a
        # Phase-1 block).
        output = shlex.quote(os.path.join(self.workspace, "download.json"))
        command = f"curl -o {output} http://u"
        r = dispatcher.dispatch(
            "bash_execute", {"command": command, "cwd": self.workspace})
        self.assertNotIn("GATED", r)
        self.assertEqual(self.shell_calls[-1][0], command)

    def test_viewer_of_workspace_file_not_over_gated(self):
        # less/nl/od of a normal workspace file must NOT gate.
        for cmd in ("less ordinary.txt", "nl ordinary.txt",
                    "base64 ordinary.txt"):
            r = dispatcher.dispatch(
                "bash_execute", {"command": cmd, "cwd": self.workspace})
            self.assertNotIn("GATED", r, cmd)
        self.assertEqual([call[0] for call in self.shell_calls],
                         ["less ordinary.txt", "nl ordinary.txt",
                          "base64 ordinary.txt"])

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
                                     "cwd": self.workspace})
            self.assertIn("GATED", r, cmd)

    def test_cd_into_workspace_does_not_over_gate(self):
        nested = os.path.join(self.workspace, "nested")
        os.makedirs(nested)
        commands = (
            f"cd {shlex.quote(self.workspace)} && cat ordinary.txt",
            f"cd {shlex.quote(nested)} && pwd",
        )
        for cmd in commands:
            r = dispatcher.dispatch("bash_execute",
                                    {"command": cmd,
                                     "cwd": self.workspace})
            self.assertNotIn("GATED", r, cmd)
        self.assertEqual([call[0] for call in self.shell_calls],
                         list(commands))

    def test_unmodelable_cd_fails_closed(self):
        # cd $VAR / cd - can't be resolved; a following relative read fails
        # closed (whole command gated).
        for cmd in ("cd $VAR && cat config", "cd - && cat config"):
            r = dispatcher.dispatch("bash_execute",
                                    {"command": cmd,
                                     "cwd": self.workspace})
            self.assertIn("SYSTEM PROTECTION", r, cmd)

    def test_search_files_excludes_secret_descendants(self):
        # A recursive search over an allowed private root must not return the
        # CONTENT of a secret/credential descendant — across the shapes the
        # adversarial pass found (env.local, private_keys/, keys/, *.pem.txt,
        # creds.txt, .ssh2/) — while STILL returning legit secret-NAMED files.
        import shutil
        root = os.path.join(self.workspace, "search-root")
        os.makedirs(root)
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
            "list_directory", {"path": self.tmp.name})
        self.assertIn("GATED", result)

    def test_list_directory_workspace_allowed(self):
        listing = os.path.join(self.workspace, "listing")
        os.makedirs(listing)
        with open(os.path.join(listing, "visible.txt"), "w") as f:
            f.write("visible\n")
        result = dispatcher.dispatch(
            "list_directory", {"path": listing})
        self.assertNotIn("GATED", result)
        self.assertIn("visible.txt", result)

    def test_script_and_package_runners_gated(self):
        # Opaque code execution through a "profiled" command is a side door
        # (the model can edit the script/package then run it). All fail closed.
        for cmd in ("python3 somescript.py", "python3 -m unittest discover",
                    "npm test", "npm run build", "node run.js",
                    "pip install requests", "brew install jq"):
            r = dispatcher.dispatch("bash_execute",
                                    {"command": cmd, "cwd": self.workspace})
            self.assertIn("SYSTEM PROTECTION", r, cmd)
        self.assertEqual(self.shell_calls, [])

        # The limiter is a separate contract. Reset it so these assertions
        # prove the read profiles reached the handler instead of accepting a
        # consecutive-call warning as a false positive.
        dispatcher.reset_consecutive()
        for cmd in ("pip list", "npm ls", "brew list", "python3 --version"):
            r = dispatcher.dispatch("bash_execute",
                                    {"command": cmd, "cwd": self.workspace})
            self.assertNotIn("GATED", r, cmd)
        self.assertEqual([call[0] for call in self.shell_calls],
                         ["pip list", "npm ls", "brew list",
                          "python3 --version"])

    def test_credential_values_are_never_retrievable_by_tool_or_standing_allow(self):
        r1 = dispatcher.dispatch("credential_store",
                                 {"action": "retrieve", "service": "svc-x",
                                  "username": "u"})
        self.assertIn("SYSTEM PROTECTION", r1)
        tool_events.grant_standing_allow("credential_store:svc-x")
        tool_events._queued_hashes.clear()
        dispatcher.reset_consecutive()
        r2 = dispatcher.dispatch("credential_store",
                                 {"action": "retrieve", "service": "svc-x",
                                  "username": "u"})
        self.assertIn("SYSTEM PROTECTION", r2)
        dispatcher.reset_consecutive()
        r3 = dispatcher.dispatch("credential_store",
                                 {"action": "status", "service": "ora",
                                  "username": "openai-api-key"})
        self.assertNotIn("SYSTEM PROTECTION", r3)
        dispatcher.credential_store.assert_called_once_with(
            "status", "ora", "openai-api-key", None)
        # Status is existence-only; no credential value can reach the result.
        ev = [e for e in self._events()
              if e["action"] == "credential_store" and e["event"] != "gate"]
        self.assertTrue(ev)
        self.assertEqual(ev[-1]["sensitivity"], "private")


@unittest.skipUnless(dispatcher._TOOLS_LOADED, "dispatcher tools not loaded")
class TestMCPGateClosure(DispatchBase):
    def test_undeclared_mcp_tool_gated_and_recorded(self):
        tool_events.reset_mcp_axes_cache()
        result = dispatcher.dispatch("mcp_unknownsrv_do_thing", {"a": 1})
        self.assertIn("SYSTEM PROTECTION", result)
        gate_events = [e for e in self._events() if e["event"] == "gate"]
        self.assertTrue(any(e["action"] == "mcp_unknownsrv_do_thing"
                            for e in gate_events))

    def test_gate_ordering_no_mcp_early_return(self):
        # The old bypass returned before the gate; now a gate event exists
        # even though no MCP client is configured in this test process.
        tool_events.reset_mcp_axes_cache()
        dispatcher.dispatch("mcp_unknownsrv_x", {})
        self.assertTrue(any(e.get("event") == "gate" for e in self._events()))


if __name__ == "__main__":
    unittest.main()
