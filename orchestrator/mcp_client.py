"""Pinned stdio MCP client with exact-tool discovery and lifecycle bounds."""

from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import time

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover
    from orchestrator import runtime_paths as _rp


WORKSPACE = _rp.WORKSPACE
MCP_REGISTRY = os.path.join(WORKSPACE, "config", "mcp-servers.json")

_PLACEHOLDER_ATTRS = {
    "ORA_HOME": "WORKSPACE",
    "ORA_VAULT": "VAULT_STR",
    "ORA_CONVERSATIONS": "CONVERSATIONS_STR",
    "ORA_SCRATCH": "SCRATCH_DIR_STR",
}

_RECV_QUEUE_MAXLINES = 256
MAX_OUTBOUND_BYTES = 8 * 1024 * 1024
MAX_INBOUND_LINE_BYTES = 16 * 1024 * 1024
MAX_STDERR_LINE_BYTES = 64 * 1024
MAX_STDERR_RETAINED_BYTES = 64 * 1024
MAX_TOOL_SCHEMA_BYTES = 256 * 1024
MAX_DISCOVERY_BYTES = 512 * 1024
MAX_TOOLS_PER_SERVER = 128
MAX_SCHEMA_DEPTH = 32
MAX_CATALOG_BYTES = 64 * 1024
_TOOL_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


class MCPError(RuntimeError):
    pass


class MCPConfigError(MCPError):
    pass


class MCPProtocolError(MCPError):
    pass


def _placeholder_value(name: str) -> str | None:
    if name == "ORA_NODE":
        return shutil.which("node")
    if name == "ORA_PYTHON":
        return os.path.realpath(sys.executable)
    attr = _PLACEHOLDER_ATTRS.get(name)
    if attr:
        return os.environ.get(name) or str(getattr(_rp, attr))
    return None


def _expand_placeholders(value):
    """Expand only Ora's known runtime placeholders, recursively."""

    if isinstance(value, str):
        for name in (*_PLACEHOLDER_ATTRS, "ORA_NODE", "ORA_PYTHON"):
            token = "${" + name + "}"
            if token in value:
                replacement = _placeholder_value(name)
                if replacement:
                    value = value.replace(token, replacement)
        return value
    if isinstance(value, list):
        return [_expand_placeholders(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_placeholders(item) for key, item in value.items()}
    return value


def _expected_server_specs() -> dict[str, dict]:
    home = os.path.realpath(str(_rp.WORKSPACE))
    vault = os.path.realpath(str(_rp.VAULT_STR))
    scratch = os.path.realpath(str(_rp.SCRATCH_DIR_STR))
    runtime = os.path.join(home, "mcp-runtime")
    playwright_output = os.path.join(scratch, "mcp-playwright")
    return {
        "vault-fs": {
            "package": "@modelcontextprotocol/server-filesystem",
            "version": "2026.7.10",
            "entry": os.path.join(runtime, "node_modules", "@modelcontextprotocol",
                                  "server-filesystem", "dist", "index.js"),
            "args": [vault],
            "cwd": vault,
        },
        "playwright": {
            "package": "@playwright/mcp",
            "version": "0.0.79",
            "entry": os.path.join(runtime, "node_modules", "@playwright", "mcp", "cli.js"),
            "args": [
                "--browser", "chromium", "--isolated", "--block-service-workers",
                "--init-page", os.path.join(home, "orchestrator", "mcp_playwright_init.mjs"),
                "--output-dir", playwright_output,
                "--output-max-size", "52428800",
            ],
            "cwd": playwright_output,
            "env": {
                "PLAYWRIGHT_BROWSERS_PATH": "0",
                "ORA_MCP_POLICY_PYTHON": os.path.realpath(sys.executable),
                "ORA_MCP_POLICY_CLI": os.path.join(
                    home, "orchestrator", "mcp_network_policy_cli.py",
                ),
            },
        },
        "github": {
            "package": "@modelcontextprotocol/server-github",
            "version": "2025.4.8",
            "entry": os.path.join(runtime, "node_modules", "@modelcontextprotocol",
                                  "server-github", "dist", "index.js"),
            "args": [],
            "cwd": runtime,
        },
    }


def _package_version(entry: str) -> str:
    current = Path(entry).resolve()
    for parent in (current, *current.parents):
        package_json = parent / "package.json"
        if package_json.is_file():
            try:
                return str(json.loads(package_json.read_text(encoding="utf-8")).get("version") or "")
            except Exception as exc:
                raise MCPConfigError("MCP package metadata is unreadable") from exc
    raise MCPConfigError("MCP package metadata is missing")


def _playwright_browser_executable(runtime: str, node: str) -> str:
    """Resolve and verify the browser owned by the locked Playwright package."""

    core = os.path.join(runtime, "node_modules", "playwright-core")
    cli = os.path.join(core, "cli.js")
    if not os.path.isfile(cli):
        raise MCPConfigError(
            "playwright: locked Playwright CLI is not installed; rerun scripts/install.py"
        )
    probe = subprocess.run(
        [node, "-e", (
            "const {chromium}=require(process.argv[1]);"
            "process.stdout.write(chromium.executablePath())"
        ), core],
        cwd=runtime, env={"PLAYWRIGHT_BROWSERS_PATH": "0"},
        capture_output=True, text=True, timeout=10,
    )
    browser = os.path.realpath((probe.stdout or "").strip())
    local_root = os.path.realpath(os.path.join(core, ".local-browsers"))
    try:
        local = os.path.commonpath([browser, local_root]) == local_root
    except ValueError:
        local = False
    if probe.returncode != 0 or not local or not os.path.isfile(browser):
        raise MCPConfigError(
            "playwright: exact locked Chromium is not installed; rerun scripts/install.py"
        )
    return browser


def _validate_server_config(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise MCPConfigError("MCP server declaration is not an object")
    name = str(raw.get("name") or "")
    expected = _expected_server_specs().get(name)
    if expected is None:
        raise MCPConfigError(f"unsupported MCP server declaration: {name or 'unnamed'}")
    if raw.get("transport") != "stdio":
        raise MCPConfigError(f"{name}: only pinned stdio transport is allowed")
    command = _expand_placeholders(raw.get("command"))
    node = shutil.which("node")
    if not isinstance(command, str) or not node or os.path.realpath(command) != os.path.realpath(node):
        raise MCPConfigError(f"{name}: command is not the exact local Node executable")
    args = _expand_placeholders(raw.get("args"))
    expected_args = [expected["entry"], *expected["args"]]
    def _arg_identity(value):
        return os.path.realpath(value) if isinstance(value, str) and os.path.isabs(value) else value
    if not isinstance(args, list) or list(map(_arg_identity, args)) != list(map(_arg_identity, expected_args)):
        raise MCPConfigError(f"{name}: entrypoint or arguments differ from the pinned launch contract")
    if not os.path.isfile(expected["entry"]):
        raise MCPConfigError(f"{name}: pinned local entrypoint is not installed")
    if _package_version(expected["entry"]) != expected["version"]:
        raise MCPConfigError(f"{name}: installed package version does not match the lock")
    cwd = _expand_placeholders(raw.get("cwd"))
    if not isinstance(cwd, str) or os.path.realpath(cwd) != os.path.realpath(expected["cwd"]):
        raise MCPConfigError(f"{name}: working directory differs from the pinned launch contract")
    tools = raw.get("tools")
    if not isinstance(tools, dict) or not tools:
        raise MCPConfigError(f"{name}: exact tool allowlist is missing")
    env_allowlist = raw.get("env_allowlist")
    env_from_parent = raw.get("env_from_parent", [])
    explicit_env = _expand_placeholders(raw.get("env", {}))
    required_env = raw.get("required_env", [])
    if not all(isinstance(value, list) and all(isinstance(item, str) and item for item in value)
               for value in (env_allowlist, env_from_parent, required_env)):
        raise MCPConfigError(f"{name}: environment declaration is malformed")
    if not isinstance(explicit_env, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in explicit_env.items()
    ):
        raise MCPConfigError(f"{name}: explicit environment is malformed")
    if name != "github" and (env_from_parent or required_env):
        raise MCPConfigError(f"{name}: ambient credential import is prohibited")
    if name == "github" and (env_from_parent != ["GITHUB_PERSONAL_ACCESS_TOKEN"]
                              or required_env != ["GITHUB_PERSONAL_ACCESS_TOKEN"]):
        raise MCPConfigError("github: token boundary differs from the pinned launch contract")
    if explicit_env != expected.get("env", {}):
        raise MCPConfigError(f"{name}: explicit environment differs from the pinned launch contract")
    forbidden = {"NODE_OPTIONS", "NODE_PATH", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                 "http_proxy", "https_proxy", "all_proxy"}
    if forbidden.intersection(env_allowlist + env_from_parent + list(explicit_env)):
        raise MCPConfigError(f"{name}: environment permits loader or proxy injection")
    launch_args = list(expected_args)
    if name == "playwright":
        launch_args.extend([
            "--executable-path",
            _playwright_browser_executable(
                os.path.join(os.path.realpath(str(_rp.WORKSPACE)), "mcp-runtime"),
                os.path.realpath(command),
            ),
        ])
    return {
        "name": name,
        "command": os.path.realpath(command),
        "args": launch_args,
        "cwd": expected["cwd"],
        "create_cwd": bool(raw.get("create_cwd")),
        "env_allowlist": env_allowlist,
        "env_from_parent": env_from_parent,
        "env": explicit_env,
        "required_env": required_env,
        "tools": set(tools),
    }


def _schema_depth(value, depth: int = 0) -> int:
    if depth > MAX_SCHEMA_DEPTH:
        return depth
    if isinstance(value, dict):
        return max((_schema_depth(item, depth + 1) for item in value.values()), default=depth)
    if isinstance(value, list):
        return max((_schema_depth(item, depth + 1) for item in value), default=depth)
    return depth


class MCPConnection:
    """One serialized newline-delimited JSON-RPC stdio connection."""

    def __init__(self, name: str, command: str, args: list | None = None,
                 env: dict | None = None, *, cwd: str | None = None,
                 env_allowlist: list[str] | None = None,
                 env_from_parent: list[str] | None = None):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.cwd = cwd
        self.env_allowlist = list(env_allowlist or [])
        self.env_from_parent = list(env_from_parent or [])
        self.process = None
        self.tools: list[dict] = []
        self._request_id = 0
        self._request_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._close_lock = threading.Lock()
        self._recv_queue: queue.Queue = queue.Queue(maxsize=_RECV_QUEUE_MAXLINES)
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._reader_eof = False
        self._fatal_error: str | None = None
        self._stderr = bytearray()
        self._closed = False

    def _fresh_environment(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for key in (*self.env_allowlist, *self.env_from_parent):
            value = os.environ.get(key)
            if value is not None:
                result[key] = value
        result.update({str(key): str(value) for key, value in self.env.items()})
        return result

    def _mark_fatal(self, reason: str) -> None:
        if self._fatal_error is None:
            self._fatal_error = reason
        process = self.process
        if process is not None:
            try:
                if process.poll() is None:
                    process.terminate()
            except Exception:
                pass

    def _queue_eof(self) -> None:
        self._reader_eof = True
        try:
            self._recv_queue.put_nowait(None)
        except queue.Full:
            try:
                self._recv_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._recv_queue.put_nowait(None)
            except queue.Full:
                pass

    def _start_reader(self) -> None:
        def pump() -> None:
            try:
                while True:
                    line = self.process.stdout.readline(MAX_INBOUND_LINE_BYTES + 1)
                    if line in (b"", ""):
                        break
                    raw = line.encode("utf-8", "strict") if isinstance(line, str) else bytes(line)
                    if len(raw) > MAX_INBOUND_LINE_BYTES or (
                        len(raw) == MAX_INBOUND_LINE_BYTES + 1 and not raw.endswith(b"\n")
                    ):
                        self._mark_fatal("MCP stdout line exceeds the byte limit")
                        break
                    try:
                        self._recv_queue.put(raw, timeout=0.25)
                    except queue.Full:
                        self._mark_fatal("MCP stdout queue overflow")
                        break
            except Exception as exc:
                self._mark_fatal(f"MCP stdout reader failed: {type(exc).__name__}")
            finally:
                self._queue_eof()

        self._reader_thread = threading.Thread(
            target=pump, daemon=True, name=f"mcp-{self.name}-stdout")
        self._reader_thread.start()

    def _start_stderr_reader(self) -> None:
        def pump() -> None:
            try:
                while True:
                    line = self.process.stderr.readline(MAX_STDERR_LINE_BYTES + 1)
                    if line in (b"", ""):
                        break
                    raw = line.encode("utf-8", "replace") if isinstance(line, str) else bytes(line)
                    if len(raw) > MAX_STDERR_LINE_BYTES:
                        raw = raw[:MAX_STDERR_LINE_BYTES]
                    remaining = MAX_STDERR_RETAINED_BYTES - len(self._stderr)
                    if remaining > 0:
                        self._stderr.extend(raw[:remaining])
            except Exception:
                pass

        self._stderr_thread = threading.Thread(
            target=pump, daemon=True, name=f"mcp-{self.name}-stderr")
        self._stderr_thread.start()

    def connect(self) -> bool:
        try:
            self.process = subprocess.Popen(
                [self.command, *self.args],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=self._fresh_environment(), cwd=self.cwd, text=False, bufsize=0,
            )
            self._start_reader()
            self._start_stderr_reader()
            result = self._request(
                "initialize",
                {"protocolVersion": "2024-11-05", "capabilities": {},
                 "clientInfo": {"name": "ora", "version": "1.0"}},
                timeout=10,
            )
            if not isinstance(result, dict):
                raise MCPProtocolError("initialize result is malformed")
            self._notify("notifications/initialized", {})
            return True
        except Exception as exc:
            print(f"[MCP] {self.name}: initialization failed ({exc})", file=sys.stderr)
            self.shutdown()
            return False

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _encoded_message(self, message: dict) -> bytes:
        try:
            encoded = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
        except (TypeError, ValueError) as exc:
            raise MCPProtocolError("outbound JSON-RPC message is not serializable") from exc
        if len(encoded) > MAX_OUTBOUND_BYTES:
            raise MCPProtocolError("outbound JSON-RPC message exceeds the byte limit")
        return encoded

    def _write_message(self, message: dict) -> None:
        if self._closed or self.process is None or self.process.stdin is None:
            raise MCPProtocolError("MCP connection is closed")
        encoded = self._encoded_message(message)
        with self._write_lock:
            self.process.stdin.write(encoded)
            self.process.stdin.flush()

    def _notify(self, method: str, params: dict) -> None:
        self._write_message({"jsonrpc": "2.0", "method": method, "params": params})

    def _request(self, method: str, params: dict, *, timeout: float) -> object:
        with self._request_lock:
            request_id = self._next_id()
            self._write_message({"jsonrpc": "2.0", "id": request_id,
                                 "method": method, "params": params})
            response = self._recv(expected_id=request_id, timeout=timeout)
            if response is None:
                raise MCPProtocolError(f"{method} timed out or the server closed")
            if "error" in response:
                raise MCPProtocolError(f"{method} returned JSON-RPC error")
            return response["result"]

    def _server_request_error(self, message: dict) -> None:
        self._write_message({
            "jsonrpc": "2.0", "id": message["id"],
            "error": {"code": -32601, "message": "Ora exposes no client request methods"},
        })

    def _recv(self, expected_id=None, timeout: float = 10) -> dict | None:
        deadline = time.monotonic() + timeout
        while True:
            if self._fatal_error:
                raise MCPProtocolError(self._fatal_error)
            if self._reader_eof:
                try:
                    raw = self._recv_queue.get_nowait()
                except queue.Empty:
                    return None
            else:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                try:
                    raw = self._recv_queue.get(timeout=remaining)
                except queue.Empty:
                    return None
            if raw is None:
                continue
            try:
                text = bytes(raw).decode("utf-8", "strict").strip()
            except UnicodeDecodeError as exc:
                self._mark_fatal("MCP stdout contains invalid UTF-8")
                raise MCPProtocolError(self._fatal_error) from exc
            if not text:
                continue
            try:
                message = json.loads(text)
            except json.JSONDecodeError as exc:
                self._mark_fatal("MCP stdout contains malformed JSON")
                raise MCPProtocolError(self._fatal_error) from exc
            if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                self._mark_fatal("MCP message is not JSON-RPC 2.0")
                raise MCPProtocolError(self._fatal_error)
            has_id = "id" in message
            has_method = isinstance(message.get("method"), str)
            has_result = "result" in message
            has_error = "error" in message
            if has_method and not has_id:
                continue
            if has_method and has_id and not has_result and not has_error:
                self._server_request_error(message)
                continue
            if has_result == has_error or not has_id or has_method:
                self._mark_fatal("MCP response shape is malformed")
                raise MCPProtocolError(self._fatal_error)
            if has_error:
                error = message.get("error")
                if not isinstance(error, dict) or isinstance(error.get("code"), bool) or not isinstance(error.get("code"), int) or not isinstance(error.get("message"), str):
                    self._mark_fatal("MCP error response shape is malformed")
                    raise MCPProtocolError(self._fatal_error)
            if expected_id is not None and message.get("id") != expected_id:
                self._mark_fatal("MCP response ID does not match the active request")
                raise MCPProtocolError(self._fatal_error)
            allowed_keys = {"jsonrpc", "id", "result" if has_result else "error"}
            if set(message) != allowed_keys:
                self._mark_fatal("MCP response contains an unexpected shape")
                raise MCPProtocolError(self._fatal_error)
            return message

    def discover_tools(self) -> list[dict]:
        result = self._request("tools/list", {}, timeout=10)
        if not isinstance(result, dict) or not isinstance(result.get("tools"), list):
            raise MCPProtocolError("tools/list result is malformed")
        raw_tools = result["tools"]
        try:
            aggregate = json.dumps(raw_tools, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise MCPProtocolError("tools/list is not JSON-serializable") from exc
        if len(aggregate) > MAX_DISCOVERY_BYTES:
            raise MCPProtocolError("tools/list exceeds the aggregate byte limit")
        accepted: list[dict] = []
        seen: set[str] = set()
        for raw in raw_tools[:MAX_TOOLS_PER_SERVER]:
            if not isinstance(raw, dict):
                continue
            name = raw.get("name")
            description = raw.get("description", "")
            schema = raw.get("inputSchema", {})
            if (
                not isinstance(name, str) or not _TOOL_NAME.fullmatch(name)
                or name in seen or not isinstance(description, str)
                or len(description.encode("utf-8")) > 16 * 1024
                or not isinstance(schema, dict)
            ):
                continue
            try:
                schema_size = len(json.dumps(schema, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
            except (TypeError, ValueError):
                continue
            if schema_size > MAX_TOOL_SCHEMA_BYTES or _schema_depth(schema) > MAX_SCHEMA_DEPTH:
                continue
            seen.add(name)
            accepted.append({"name": name, "description": description, "inputSchema": schema})
        self.tools = accepted
        return list(accepted)

    def call_tool(self, tool_name: str, arguments: dict, timeout: int = 30) -> dict:
        try:
            result = self._request(
                "tools/call", {"name": tool_name, "arguments": arguments},
                timeout=max(1, min(int(timeout), 120)),
            )
            return result if isinstance(result, dict) else {"error": "MCP tool result is malformed"}
        except Exception as exc:
            self.shutdown()
            return {"error": str(exc)}

    def shutdown(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
            process = self.process
            if process is not None:
                try:
                    if process.stdin:
                        process.stdin.close()
                except Exception:
                    pass
                try:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=2)
                except Exception:
                    try:
                        process.kill()
                        process.wait(timeout=2)
                    except Exception:
                        pass
                for stream_name in ("stdout", "stderr"):
                    try:
                        stream = getattr(process, stream_name, None)
                        if stream:
                            stream.close()
                    except Exception:
                        pass
            self._queue_eof()
            current = threading.current_thread()
            for thread in (self._reader_thread, self._stderr_thread):
                if thread is not None and thread is not current:
                    thread.join(timeout=2)
            self.process = None


class MCPClientManager:
    def __init__(self):
        self.connections: dict[str, MCPConnection] = {}
        self.all_tools: dict[str, tuple[str, str]] = {}
        self._definitions: dict[str, dict] = {}

    def initialize(self) -> None:
        if not os.path.exists(MCP_REGISTRY):
            return
        try:
            if os.path.getsize(MCP_REGISTRY) > 1024 * 1024:
                raise MCPConfigError("MCP registry exceeds its byte limit")
            with open(MCP_REGISTRY, encoding="utf-8") as stream:
                registry = json.load(stream)
        except Exception as exc:
            print(f"[MCP] registry unavailable ({exc})", file=sys.stderr)
            return
        servers = registry.get("servers") if isinstance(registry, dict) else None
        if not isinstance(servers, list):
            print("[MCP] registry has no server list", file=sys.stderr)
            return
        for raw in servers:
            conn = None
            name = str(raw.get("name") or "unknown") if isinstance(raw, dict) else "unknown"
            try:
                cfg = _validate_server_config(raw)
                if any(not os.environ.get(key) for key in cfg["required_env"]):
                    print(f"[MCP] {name}: skipped because its required token is absent")
                    continue
                if cfg["create_cwd"]:
                    os.makedirs(cfg["cwd"], exist_ok=True)
                elif not os.path.isdir(cfg["cwd"]):
                    raise MCPConfigError(f"{name}: working directory is missing")
                conn = MCPConnection(
                    name=name, command=cfg["command"], args=cfg["args"],
                    env=cfg["env"], cwd=cfg["cwd"],
                    env_allowlist=cfg["env_allowlist"],
                    env_from_parent=cfg["env_from_parent"],
                )
                if not conn.connect():
                    continue
                discovered = conn.discover_tools()
                allowed = cfg["tools"]
                recognized = [tool for tool in discovered if tool["name"] in allowed]
                conn.tools = recognized
                self.connections[name] = conn
                for tool in recognized:
                    namespaced = f"mcp_{name}_{tool['name']}"
                    self.all_tools[namespaced] = (name, tool["name"])
                    self._definitions[namespaced] = {
                        "name": namespaced,
                        "description": tool.get("description", ""),
                        "parameters": tool.get("inputSchema", {}),
                    }
                print(f"[MCP] Connected to {name}: {len(recognized)} recognized tools")
            except Exception as exc:
                print(f"[MCP] {name}: failed-soft ({exc})", file=sys.stderr)
                if conn is not None:
                    conn.shutdown()

    def call_mcp_tool(self, namespaced_name: str, parameters: dict) -> dict:
        binding = self.all_tools.get(namespaced_name)
        if binding is None:
            return {"error": f"Unknown MCP tool: {namespaced_name}"}
        try:
            try:
                import tool_events
            except ImportError:  # pragma: no cover
                from orchestrator import tool_events
            resolved = tool_events.mcp_policy(namespaced_name, parameters)
        except Exception as exc:
            return {"error": f"MCP policy denied the call: {exc}"}
        server_name, tool_name = binding
        conn = self.connections.get(server_name)
        if conn is None:
            return {"error": f"MCP server {server_name} not connected"}
        return conn.call_tool(tool_name, resolved["parameters"])

    def get_tool_definitions(self) -> list[dict]:
        definitions = [self._definitions[name] for name in sorted(self._definitions)]
        encoded = json.dumps(definitions, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if len(encoded) > MAX_CATALOG_BYTES:
            return []
        return definitions

    def shutdown(self) -> None:
        for conn in list(self.connections.values()):
            conn.shutdown()
        self.connections.clear()
        self.all_tools.clear()
        self._definitions.clear()


_manager: MCPClientManager | None = None


def get_manager() -> MCPClientManager:
    global _manager
    if _manager is None:
        manager = MCPClientManager()
        manager.initialize()
        _manager = manager
    return _manager


def shutdown() -> None:
    global _manager
    manager = _manager
    _manager = None
    if manager is not None:
        manager.shutdown()
    try:
        try:
            import dispatcher
        except ImportError:  # pragma: no cover
            from orchestrator import dispatcher
        if getattr(dispatcher, "_mcp_client", None) is manager:
            dispatcher.set_mcp_client(None)
    except Exception:
        pass
