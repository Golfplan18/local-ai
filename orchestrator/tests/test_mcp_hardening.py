"""Focused, hermetic acceptance tests for the G1.22 MCP boundary."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock


_ORCHESTRATOR = Path(__file__).resolve().parent.parent
_REPO = _ORCHESTRATOR.parent
if str(_ORCHESTRATOR) not in sys.path:
    sys.path.insert(0, str(_ORCHESTRATOR))

import mcp_client  # noqa: E402
import network_policy  # noqa: E402
import system_protection  # noqa: E402
import tool_events  # noqa: E402


def _decision(namespaced_tool: str, parameters: dict):
    resolved = tool_events.mcp_policy(namespaced_tool, parameters)
    axes = dict(resolved["axes"])
    axes.update({
        "_mcp_action": resolved["action"],
        "_mcp_selectors": resolved["selectors"],
        "_mcp_destructive": resolved["destructive"],
    })
    decision = system_protection.classify_tool_call(
        namespaced_tool, resolved["parameters"], axes,
    )
    return resolved, decision


class MCPPolicyTests(unittest.TestCase):
    def setUp(self):
        tool_events.reset_mcp_axes_cache()

    def tearDown(self):
        tool_events.reset_mcp_axes_cache()

    def test_registry_is_exact_pinned_local_and_keeps_all_families(self):
        registry = json.loads(
            (_REPO / "config" / "mcp-servers.json").read_text(encoding="utf-8")
        )
        package = json.loads(
            (_REPO / "mcp-runtime" / "package.json").read_text(encoding="utf-8")
        )
        lock = json.loads(
            (_REPO / "mcp-runtime" / "package-lock.json").read_text(encoding="utf-8")
        )
        expected = {
            "vault-fs": (14, "@modelcontextprotocol/server-filesystem", "2026.7.10"),
            "playwright": (24, "@playwright/mcp", "0.0.79"),
            "github": (26, "@modelcontextprotocol/server-github", "2025.4.8"),
        }
        self.assertEqual({item["name"] for item in registry["servers"]}, set(expected))
        for server in registry["servers"]:
            count, dependency, version = expected[server["name"]]
            self.assertEqual(len(server["tools"]), count)
            self.assertEqual(server["command"], "${ORA_NODE}")
            self.assertTrue(server["args"][0].startswith("${ORA_HOME}/mcp-runtime/node_modules/"))
            self.assertFalse({"mutability", "sensitivity", "egress"}.intersection(server))
            self.assertEqual(package["dependencies"][dependency], version)
            self.assertEqual(lock["packages"][f"node_modules/{dependency}"]["version"], version)
        playwright = next(item for item in registry["servers"] if item["name"] == "playwright")
        self.assertEqual(playwright["args"][1:3], ["--browser", "chromium"])
        self.assertEqual(playwright["env"]["PLAYWRIGHT_BROWSERS_PATH"], "0")
        launch_text = json.dumps(registry, separators=(",", ":"))
        for floating in ('"npx"', '"-y"', "@latest"):
            self.assertNotIn(floating, launch_text)

    def test_fresh_child_environments_strip_credentials_proxies_and_loaders(self):
        ambient = {
            "PATH": "/safe/bin",
            "TMPDIR": "/safe/tmp",
            "AWS_SECRET_ACCESS_KEY": "do-not-pass",
            "OPENAI_API_KEY": "do-not-pass",
            "HTTP_PROXY": "http://proxy.invalid",
            "https_proxy": "http://proxy.invalid",
            "NODE_OPTIONS": "--require=/tmp/evil.js",
            "NODE_PATH": "/tmp/evil-modules",
            "GITHUB_PERSONAL_ACCESS_TOKEN": "test-token",
        }
        with mock.patch.dict(os.environ, ambient, clear=True):
            vault = mcp_client.MCPConnection(
                "vault-fs", "/node", env_allowlist=["PATH", "TMPDIR"],
            )._fresh_environment()
            github = mcp_client.MCPConnection(
                "github", "/node", env_allowlist=["PATH"],
                env_from_parent=["GITHUB_PERSONAL_ACCESS_TOKEN"],
            )._fresh_environment()
        self.assertEqual(vault, {"PATH": "/safe/bin", "TMPDIR": "/safe/tmp"})
        self.assertEqual(
            github,
            {"PATH": "/safe/bin", "GITHUB_PERSONAL_ACCESS_TOKEN": "test-token"},
        )

    def test_vault_paths_are_transmitted_canonically_and_symlink_escapes_fail(self):
        with tempfile.TemporaryDirectory() as vault_dir, tempfile.TemporaryDirectory() as outside:
            vault = Path(vault_dir)
            (vault / "source.md").write_text("source", encoding="utf-8")
            (vault / "escape").symlink_to(Path(outside), target_is_directory=True)
            with mock.patch.object(tool_events._rp, "VAULT_STR", str(vault)):
                canonical_vault = vault.resolve()
                read, read_decision = _decision(
                    "mcp_vault-fs_read_file", {"path": "source.md"},
                )
                self.assertEqual(read["parameters"]["path"], str(canonical_vault / "source.md"))
                self.assertEqual(read_decision.outcome, "allow")

                move, move_decision = _decision(
                    "mcp_vault-fs_move_file",
                    {"source": "source.md", "destination": "moved.md"},
                )
                self.assertEqual(move["parameters"]["source"], str(canonical_vault / "source.md"))
                self.assertEqual(move["parameters"]["destination"], str(canonical_vault / "moved.md"))
                self.assertEqual(move_decision.outcome, "review")
                self.assertEqual(len(move_decision.selectors), 2)

                for bad in ("../outside", str(Path(outside) / "x"), "escape/not-yet-created.md"):
                    with self.subTest(path=bad), self.assertRaises(tool_events.MCPPolicyError):
                        tool_events.mcp_policy("mcp_vault-fs_write_file", {"path": bad})

    def test_vault_write_uses_existing_one_shot_review_path(self):
        with tempfile.TemporaryDirectory() as vault_dir:
            with mock.patch.object(tool_events._rp, "VAULT_STR", vault_dir):
                resolved, decision = _decision(
                    "mcp_vault-fs_write_file",
                    {"path": "note.md", "content": "complete bound arguments"},
                )
        self.assertEqual(decision.outcome, "review")
        self.assertEqual(decision.policy_code, "review-required")
        self.assertEqual(decision.action, "mcp_vault-fs_write_file")
        self.assertEqual(decision.selectors, resolved["selectors"])
        self.assertTrue(resolved["destructive"])

    def test_github_read_write_and_irreversible_selectors_are_exact(self):
        read, read_decision = _decision(
            "mcp_github_get_file_contents",
            {"owner": "ora", "repo": "runtime", "path": "src/a.py", "branch": "main"},
        )
        self.assertEqual(read_decision.outcome, "allow")
        self.assertIn("github:repo/ora/runtime", read["selectors"])
        self.assertIn("github:ref/ora/runtime/main", read["selectors"])
        self.assertIn("github:path/ora/runtime/src%2Fa.py", read["selectors"])

        write, write_decision = _decision(
            "mcp_github_create_issue",
            {"owner": "ora", "repo": "runtime", "title": "Bound title", "body": "Bound body"},
        )
        self.assertEqual(write_decision.outcome, "review")
        self.assertEqual(write["parameters"]["body"], "Bound body")

        pushed, push_decision = _decision(
            "mcp_github_push_files",
            {
                "owner": "ora", "repo": "runtime", "branch": "main", "message": "two files",
                "files": [{"path": "a.txt", "content": "a"}, {"path": "dir/b.txt", "content": "b"}],
            },
        )
        self.assertEqual(push_decision.outcome, "review")
        self.assertTrue(pushed["destructive"])
        self.assertIn("github:path/ora/runtime/a.txt", pushed["selectors"])
        self.assertIn("github:path/ora/runtime/dir%2Fb.txt", pushed["selectors"])

        merged, merge_decision = _decision(
            "mcp_github_merge_pull_request",
            {"owner": "ora", "repo": "runtime", "pull_number": 12, "merge_method": "squash"},
        )
        self.assertTrue(merged["destructive"])
        self.assertEqual(merge_decision.outcome, "review")
        self.assertIn("github:pull/ora/runtime/12", merged["selectors"])

    def test_github_search_uses_each_locked_schema_query_field(self):
        cases = {
            "search_code": {},
            "search_issues": {"sort": "updated"},
            "search_users": {"sort": "followers"},
        }
        for tool, extra in cases.items():
            parameters = {
                "q": "schema needle", "order": "desc", "page": 2,
                "per_page": 25, **extra,
            }
            with self.subTest(tool=tool):
                resolved, decision = _decision(f"mcp_github_{tool}", parameters)
                self.assertEqual(decision.outcome, "allow")
                self.assertEqual(resolved["parameters"], parameters)
                self.assertIn(
                    f"github:search/{tool}/schema%20needle", resolved["selectors"],
                )
                with self.assertRaisesRegex(tool_events.MCPPolicyError, "query"):
                    tool_events.mcp_policy(
                        f"mcp_github_{tool}", {"query": "wrong schema field"},
                    )

        repositories = tool_events.mcp_policy(
            "mcp_github_search_repositories",
            {"query": "still repository-shaped", "page": 3, "perPage": 10},
        )
        self.assertEqual(repositories["parameters"]["query"], "still repository-shaped")

    def test_playwright_navigation_interaction_and_opaque_code_policy(self):
        fake_dns = [(2, 1, 6, "", ("93.184.216.34", 443))]
        with mock.patch.object(network_policy.socket, "getaddrinfo", return_value=fake_dns):
            navigation, navigation_decision = _decision(
                "mcp_playwright_browser_navigate", {"url": "https://example.test/start"},
            )
        self.assertEqual(navigation_decision.outcome, "allow")
        self.assertEqual(navigation["selectors"], ("network-read:https://example.test/start",))

        interaction, interaction_decision = _decision(
            "mcp_playwright_browser_type",
            {"target": "e12", "text": "all arguments stay bound", "submit": True},
        )
        self.assertEqual(interaction_decision.outcome, "review")
        self.assertEqual(interaction["parameters"]["text"], "all arguments stay bound")
        self.assertIn("playwright:call/target/e12", interaction["selectors"])
        self.assertIn("playwright:page/active", interaction["selectors"])
        self.assertNotEqual(
            system_protection.params_digest(interaction["parameters"]),
            system_protection.params_digest({**interaction["parameters"], "text": "changed"}),
        )

        for tool in ("browser_evaluate", "browser_run_code_unsafe"):
            with self.subTest(tool=tool), self.assertRaisesRegex(
                tool_events.MCPPolicyError, "arbitrary-code",
            ):
                tool_events.mcp_policy(f"mcp_playwright_{tool}", {"function": "() => 1"})

    def test_playwright_locked_targets_paths_tabs_and_upload_cancellation(self):
        drag, drag_decision = _decision(
            "mcp_playwright_browser_drag",
            {"startTarget": "e1", "endTarget": "e2"},
        )
        self.assertEqual(drag_decision.outcome, "review")
        self.assertIn("playwright:call/startTarget/e1", drag["selectors"])
        self.assertIn("playwright:call/endTarget/e2", drag["selectors"])

        fake_dns = [(2, 1, 6, "", ("93.184.216.34", 443))]
        with mock.patch.object(network_policy.socket, "getaddrinfo", return_value=fake_dns):
            new_tab, new_tab_decision = _decision(
                "mcp_playwright_browser_tabs",
                {"action": "new", "url": "https://example.test/new"},
            )
        self.assertEqual(new_tab["axes"]["egress"], "external")
        self.assertIn("network-read:https://example.test/new", new_tab["selectors"])
        self.assertEqual(new_tab_decision.outcome, "review")

        with tempfile.TemporaryDirectory() as directory:
            dropped_file = Path(directory, "drop.txt")
            dropped_file.write_text("drop", encoding="utf-8")
            dropped, drop_decision = _decision(
                "mcp_playwright_browser_drop",
                {"target": "e7", "paths": [str(dropped_file)]},
            )
            uploaded, upload_decision = _decision(
                "mcp_playwright_browser_file_upload",
                {"paths": [str(dropped_file)]},
            )
        self.assertEqual(dropped["parameters"]["paths"], [str(dropped_file.resolve())])
        self.assertIn("path:" + str(dropped_file.resolve()), dropped["selectors"])
        self.assertIn("playwright:call/target/e7", dropped["selectors"])
        self.assertEqual(drop_decision.outcome, "review")
        self.assertEqual(uploaded["parameters"]["paths"], [str(dropped_file.resolve())])
        self.assertEqual(upload_decision.outcome, "review")

        for parameters in ({}, {"paths": []}):
            with self.subTest(cancellation=parameters):
                cancelled, cancellation_decision = _decision(
                    "mcp_playwright_browser_file_upload", parameters,
                )
                self.assertEqual(cancelled["parameters"], parameters)
                self.assertEqual(cancelled["axes"]["mutability"], "reversible_write")
                self.assertEqual(cancelled["axes"]["egress"], "local")
                self.assertEqual(cancellation_decision.outcome, "allow")


class MCPProtocolTests(unittest.TestCase):
    _SERVER = r"""
import json, sys
def send(value):
    sys.stdout.write(json.dumps(value, separators=(',', ':')) + '\n')
    sys.stdout.flush()
for raw in sys.stdin:
    message = json.loads(raw)
    method = message.get('method')
    if method == 'initialize':
        send({'jsonrpc':'2.0','method':'notifications/progress','params':{}})
        send({'jsonrpc':'2.0','id':900,'method':'roots/list','params':{}})
        refusal = json.loads(sys.stdin.readline())
        assert refusal['id'] == 900 and refusal['error']['code'] == -32601
        send({'jsonrpc':'2.0','id':message['id'],'result':{'protocolVersion':'2024-11-05','capabilities':{}}})
    elif method == 'notifications/initialized':
        continue
    elif method == 'tools/list':
        send({'jsonrpc':'2.0','id':message['id'],'result':{'tools':[{'name':'read_file','description':'read','inputSchema':{'type':'object'}}]}})
    elif method == 'tools/call':
        send({'jsonrpc':'2.0','id':message['id'],'result':{'content':[{'type':'text','text':'ok'}]}})
"""

    def test_local_stdio_requests_are_serialized_and_cleanup_is_idempotent(self):
        conn = mcp_client.MCPConnection(
            "fake", sys.executable, ["-u", "-c", self._SERVER], env={},
        )
        self.assertTrue(conn.connect())
        self.assertEqual([tool["name"] for tool in conn.discover_tools()], ["read_file"])
        self.assertEqual(conn.call_tool("read_file", {"path": "x"})["content"][0]["text"], "ok")
        stdout_thread = conn._reader_thread
        stderr_thread = conn._stderr_thread
        conn.shutdown()
        conn.shutdown()
        self.assertIsNone(conn.process)
        self.assertFalse(stdout_thread.is_alive())
        self.assertFalse(stderr_thread.is_alive())
        self.assertFalse(any(
            thread.is_alive() and thread.name.startswith("mcp-fake-")
            for thread in threading.enumerate()
        ))

    def test_response_id_and_shape_are_exact(self):
        mismatch = mcp_client.MCPConnection("fake", "unused")
        mismatch._reader_eof = True
        mismatch._recv_queue.put(b'{"jsonrpc":"2.0","id":8,"result":{}}\n')
        with self.assertRaisesRegex(mcp_client.MCPProtocolError, "does not match"):
            mismatch._recv(expected_id=7)

        malformed = mcp_client.MCPConnection("fake", "unused")
        malformed._reader_eof = True
        malformed._recv_queue.put(
            b'{"jsonrpc":"2.0","id":7,"result":{},"error":{"code":1,"message":"x"}}\n'
        )
        with self.assertRaisesRegex(mcp_client.MCPProtocolError, "shape"):
            malformed._recv(expected_id=7)

    def test_inbound_and_outbound_byte_limits_apply_before_decode_or_write(self):
        class _Process:
            def __init__(self):
                self.stdout = io.BytesIO(b"x" * 33 + b"\n")
                self.terminated = False

            def poll(self):
                return None if not self.terminated else -15

            def terminate(self):
                self.terminated = True

        inbound = mcp_client.MCPConnection("bounded", "unused")
        inbound.process = _Process()
        with mock.patch.object(mcp_client, "MAX_INBOUND_LINE_BYTES", 32):
            inbound._start_reader()
            inbound._reader_thread.join(timeout=2)
            with self.assertRaisesRegex(mcp_client.MCPProtocolError, "byte limit"):
                inbound._recv(timeout=0.1)
        with mock.patch.object(mcp_client, "MAX_OUTBOUND_BYTES", 32):
            with self.assertRaisesRegex(mcp_client.MCPProtocolError, "byte limit"):
                inbound._encoded_message({"jsonrpc": "2.0", "id": 1, "params": {"x": "y" * 64}})

    def test_discovery_omits_malformed_over_limit_and_direct_calls_fail_closed(self):
        conn = mcp_client.MCPConnection("fake", "unused")
        conn._request = mock.Mock(return_value={"tools": [
            {"name": "valid", "description": "ok", "inputSchema": {"type": "object"}},
            {"name": "valid", "description": "duplicate", "inputSchema": {}},
            {"name": "bad name", "description": "bad", "inputSchema": {}},
            {"name": "huge", "description": "large", "inputSchema": {"description": "x" * 256}},
        ]})
        with mock.patch.object(mcp_client, "MAX_TOOL_SCHEMA_BYTES", 64):
            self.assertEqual([tool["name"] for tool in conn.discover_tools()], ["valid"])

        manager = mcp_client.MCPClientManager()
        denied_conn = mock.Mock()
        manager.connections["playwright"] = denied_conn
        manager.all_tools["mcp_playwright_browser_evaluate"] = (
            "playwright", "browser_evaluate",
        )
        self.assertIn(
            "policy denied",
            manager.call_mcp_tool(
                "mcp_playwright_browser_evaluate", {"function": "() => process.env"},
            )["error"].lower(),
        )
        denied_conn.call_tool.assert_not_called()
        self.assertIn("Unknown MCP tool", manager.call_mcp_tool("mcp_fake_unknown", {})["error"])


class MCPManagerTests(unittest.TestCase):
    @staticmethod
    def _configured_tools():
        registry = json.loads(
            (_REPO / "config" / "mcp-servers.json").read_text(encoding="utf-8")
        )
        return registry, {server["name"]: set(server["tools"]) for server in registry["servers"]}

    def _initialize(self, *, token: str, failing: str | None = None):
        registry, tools = self._configured_tools()
        instances = {}

        def validate(raw):
            name = raw["name"]
            return {
                "name": name, "command": "/fake/node", "args": [],
                "cwd": str(_REPO), "create_cwd": False,
                "env_allowlist": [], "env_from_parent": [], "env": {},
                "required_env": ["GITHUB_PERSONAL_ACCESS_TOKEN"] if name == "github" else [],
                "tools": tools[name],
            }

        class FakeConnection:
            def __init__(self, name, *args, **kwargs):
                self.name = name
                self.tools = []
                self.closed = False
                instances[name] = self

            def connect(self):
                if self.name == failing:
                    raise RuntimeError("fixture startup failure")
                return True

            def discover_tools(self):
                return [
                    {"name": name, "description": name, "inputSchema": {"type": "object"}}
                    for name in sorted(tools[self.name] | {"child_only_unknown"})
                ]

            def shutdown(self):
                self.closed = True

        manager = mcp_client.MCPClientManager()
        with mock.patch.object(mcp_client, "_validate_server_config", side_effect=validate), \
             mock.patch.object(mcp_client, "MCPConnection", FakeConnection), \
             mock.patch.dict(os.environ, {"GITHUB_PERSONAL_ACCESS_TOKEN": token}, clear=False):
            manager.initialize()
        return manager, instances, registry

    def test_catalog_is_child_discovery_intersected_with_all_three_allowlists(self):
        manager, instances, _ = self._initialize(token="fixture-token")
        try:
            counts = {name: 0 for name in ("vault-fs", "playwright", "github")}
            for server, _tool in manager.all_tools.values():
                counts[server] += 1
            self.assertEqual(counts, {"vault-fs": 14, "playwright": 24, "github": 26})
            self.assertFalse(any("child_only_unknown" in name for name in manager.all_tools))
        finally:
            manager.shutdown()
        self.assertTrue(all(instance.closed for instance in instances.values()))

    def test_missing_github_token_skips_only_github(self):
        manager, instances, _ = self._initialize(token="")
        try:
            self.assertEqual(set(manager.connections), {"vault-fs", "playwright"})
            self.assertEqual(len(manager.all_tools), 38)
            self.assertNotIn("github", instances)
        finally:
            manager.shutdown()

    def test_one_server_failure_does_not_suppress_the_other_two(self):
        manager, instances, _ = self._initialize(token="fixture-token", failing="playwright")
        try:
            self.assertEqual(set(manager.connections), {"vault-fs", "github"})
            self.assertEqual(len(manager.all_tools), 40)
            self.assertTrue(instances["playwright"].closed)
        finally:
            manager.shutdown()

    def test_missing_locked_browser_fails_only_playwright_clearly(self):
        registry, tools = self._configured_tools()

        def validate(raw):
            if raw["name"] == "playwright":
                raise mcp_client.MCPConfigError(
                    "playwright: exact locked Chromium is not installed; rerun scripts/install.py"
                )
            return {
                "name": raw["name"], "command": "/fake/node", "args": [],
                "cwd": str(_REPO), "create_cwd": False,
                "env_allowlist": [], "env_from_parent": [], "env": {},
                "required_env": [], "tools": tools[raw["name"]],
            }

        class FakeConnection:
            def __init__(self, name, *args, **kwargs):
                self.name = name
                self.tools = []
            def connect(self): return True
            def discover_tools(self): return []
            def shutdown(self): pass

        manager = mcp_client.MCPClientManager()
        with mock.patch.object(mcp_client, "_validate_server_config", side_effect=validate), \
             mock.patch.object(mcp_client, "MCPConnection", FakeConnection), \
             mock.patch.object(sys, "stderr", new_callable=io.StringIO) as stderr:
            manager.initialize()
        self.assertEqual(set(manager.connections), {"vault-fs", "github"})
        self.assertIn("exact locked Chromium is not installed", stderr.getvalue())


class PlaywrightBrowserAvailabilityTests(unittest.TestCase):
    def test_runtime_resolves_only_repo_local_locked_browser(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            core = runtime / "node_modules" / "playwright-core"
            browser = core / ".local-browsers" / "chromium-123" / "chrome"
            browser.parent.mkdir(parents=True)
            browser.write_text("binary", encoding="utf-8")
            (core / "cli.js").write_text("", encoding="utf-8")
            completed = subprocess.CompletedProcess([], 0, stdout=str(browser), stderr="")
            with mock.patch.object(mcp_client.subprocess, "run", return_value=completed) as run:
                resolved = mcp_client._playwright_browser_executable(
                    str(runtime), "/exact/node",
                )
            self.assertEqual(resolved, str(browser.resolve()))
            self.assertEqual(run.call_args.args[0][0], "/exact/node")
            self.assertEqual(run.call_args.kwargs["env"], {"PLAYWRIGHT_BROWSERS_PATH": "0"})

    def test_runtime_rejects_missing_locked_browser(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            core = runtime / "node_modules" / "playwright-core"
            core.mkdir(parents=True)
            (core / "cli.js").write_text("", encoding="utf-8")
            completed = subprocess.CompletedProcess([], 0, stdout=str(core / ".local-browsers/missing"), stderr="")
            with mock.patch.object(mcp_client.subprocess, "run", return_value=completed), \
                 self.assertRaisesRegex(mcp_client.MCPConfigError, "not installed"):
                mcp_client._playwright_browser_executable(str(runtime), "/exact/node")


class PlaywrightRouteHookTests(unittest.TestCase):
    def test_fake_context_routes_http_and_websocket_and_states_residual(self):
        node = shutil.which("node")
        self.assertIsNotNone(node)
        hook = _ORCHESTRATOR / "mcp_playwright_init.mjs"
        script = """
const { installRoutes } = await import(%s);
let httpHandler, websocketHandler, httpInstalls = 0, websocketInstalls = 0;
const context = {
  route: async (_pattern, handler) => { httpInstalls++; httpHandler = handler; },
  routeWebSocket: async (_pattern, handler) => { websocketInstalls++; websocketHandler = handler; },
};
const events = [];
const checker = async url => { if (url.includes('blocked')) throw new Error('private'); };
await installRoutes(context, checker);
await installRoutes(context, checker);
await httpHandler({request: () => ({url: () => 'https://public.test/a'}), continue: async () => events.push('http-continue'), abort: async () => events.push('http-abort')});
await httpHandler({request: () => ({url: () => 'http://blocked.test/a'}), continue: async () => events.push('bad-continue'), abort: async reason => events.push('http-' + reason)});
await websocketHandler({url: () => 'wss://public.test/ws', connectToServer: () => events.push('ws-connect'), close: () => events.push('ws-close')});
await websocketHandler({url: () => 'ws://blocked.test/ws', connectToServer: () => events.push('bad-connect'), close: value => events.push('ws-' + value.code)});
console.log(JSON.stringify({httpInstalls, websocketInstalls, events}));
""" % json.dumps(hook.as_uri())
        completed = subprocess.run(
            [node, "--input-type=module", "-e", script],
            capture_output=True, text=True, timeout=10,
            env={"PATH": os.environ.get("PATH", "")},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["httpInstalls"], 1)
        self.assertEqual(result["websocketInstalls"], 1)
        self.assertEqual(
            result["events"],
            ["http-continue", "http-blockedbyclient", "ws-connect", "ws-1008"],
        )
        source = hook.read_text(encoding="utf-8").casefold()
        for residual in ("redirect", "dns", "webrtc", "webtransport"):
            self.assertIn(residual, source)
        self.assertIn("does not deliver", source)

    def test_policy_cli_rejects_private_url_without_logging_it(self):
        value = "http://127.0.0.1/private-do-not-log"
        completed = subprocess.run(
            [sys.executable, str(_ORCHESTRATOR / "mcp_network_policy_cli.py")],
            input=value, capture_output=True, text=True, timeout=10,
            env={"PYTHONUNBUFFERED": "1"},
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn(value, completed.stdout + completed.stderr)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(completed.stderr, "")


if __name__ == "__main__":
    unittest.main()
