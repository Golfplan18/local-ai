"""MCP client manager — connects to MCP servers, discovers tools,
routes tool calls through JSON-RPC."""

from __future__ import annotations

import json
import os
import queue
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

# Placeholders resolvable in server config values (command / args / env /
# url). Resolved at launch time — env var of the same name wins, else the
# runtime_paths default — so the checked-in registry never carries a
# machine- or platform-specific absolute path (e.g. the vault-fs server's
# root is ${ORA_VAULT}, which resolves to %USERPROFILE%\Documents\vault on
# Windows and ~/Documents/vault on POSIX unless overridden).
#
# The convention outgrew the MCP registry: config/routing-config.json and
# config/capabilities.json use the same placeholders, so the expander lives
# in runtime_paths (which owns the roots it resolves against) and every
# loader shares one implementation. These names stay as the module's own
# spelling of it.
_PLACEHOLDER_ATTRS = _rp.PLACEHOLDER_ATTRS
_expand_placeholders = _rp.expand_placeholders

# Cap on buffered stdout lines per connection (see MCPConnection.__init__).
_RECV_QUEUE_MAXLINES = 10_000


class MCPConnection:
    """Manages a single MCP server connection via stdio transport."""

    def __init__(self, name: str, command: str, args: list = None, env: dict = None):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env
        self.process = None
        self.tools = []
        self._request_id = 0
        self._lock = threading.Lock()
        # Bounded so a notification-chatty server cannot grow parent memory
        # without limit: when the queue fills, the reader blocks, the OS
        # pipe fills, and the server write-blocks — the same backpressure
        # the pipe itself provided before the reader thread existed. The
        # cap is a PROVISIONAL tuning constant (worst case ~a few MB per
        # connection at typical line sizes), not empirically calibrated.
        self._recv_queue: queue.Queue = queue.Queue(
            maxsize=_RECV_QUEUE_MAXLINES)
        self._reader_thread: threading.Thread | None = None
        self._reader_eof = False

    def _start_reader(self):
        """Pump the server's stdout onto a queue from a daemon thread.

        This is the cross-platform replacement for waiting on the pipe with
        ``select.select()``: on Windows, select supports only sockets — it
        cannot wait on a subprocess pipe handle — so a select-based receive
        would fail every stdio MCP initialization there. A blocking
        ``readline`` on a daemon thread plus ``Queue.get(timeout=...)``
        works identically on every platform. When the stream ends (EOF or a
        read error, which is logged, never swallowed silently) the pump
        sets ``_reader_eof`` and pushes a ``None`` sentinel so ``_recv``
        can distinguish a closed server from a quiet one — and, via the
        flag, answer immediately (not after a full timeout) on every call
        after the stream is gone, matching the old select-on-EOF behavior."""
        def _pump():
            try:
                for line in iter(self.process.stdout.readline, ""):
                    self._recv_queue.put(line)
            except Exception as e:
                try:
                    print(f"[MCP] {self.name}: stdout reader error: {e}",
                          file=sys.stderr)
                except Exception:
                    pass
            self._reader_eof = True   # set BEFORE the sentinel: a consumer
            self._recv_queue.put(None)  # that sees the flag never blocks

        self._reader_thread = threading.Thread(
            target=_pump, daemon=True, name=f"mcp-{self.name}-stdout")
        self._reader_thread.start()

    def connect(self) -> bool:
        """Start the MCP server subprocess and initialize."""
        try:
            cmd = [self.command] + self.args
            proc_env = os.environ.copy()
            if self.env:
                proc_env.update(self.env)

            # encoding is pinned: MCP stdio is UTF-8 by spec, but bare
            # text=True decodes with the locale's preferred encoding — on
            # Windows Python <= 3.14 that is the ANSI codepage (cp1252 et
            # al.), so the first non-ASCII response would corrupt or kill
            # the stream. errors="replace" keeps one malformed line from
            # ending the reader: the line decodes with U+FFFD and at worst
            # fails json.loads and is skipped, instead of raising in the
            # pump and permanently deadening a healthy connection.
            self.process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=proc_env, text=True,
                encoding="utf-8", errors="replace",
            )
            self._start_reader()

            # Send initialize request
            self._send({"jsonrpc": "2.0", "id": self._next_id(),
                         "method": "initialize",
                         "params": {"protocolVersion": "2024-11-05",
                                    "capabilities": {},
                                    "clientInfo": {"name": "ora", "version": "1.0"}}})
            resp = self._recv(timeout=10)
            if resp and "result" in resp:
                # Send initialized notification
                self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
                return True
            return False
        except Exception as e:
            print(f"[MCP] Failed to connect to {self.name}: {e}")
            return False

    def discover_tools(self) -> list:
        """Call tools/list to discover available tools."""
        try:
            self._send({"jsonrpc": "2.0", "id": self._next_id(),
                         "method": "tools/list", "params": {}})
            resp = self._recv(timeout=10)
            if resp and "result" in resp:
                self.tools = resp["result"].get("tools", [])
                return self.tools
        except Exception as e:
            print(f"[MCP] Tool discovery failed for {self.name}: {e}")
        return []

    def call_tool(self, tool_name: str, arguments: dict, timeout: int = 30) -> dict:
        """Call a tool on this MCP server."""
        try:
            self._send({"jsonrpc": "2.0", "id": self._next_id(),
                         "method": "tools/call",
                         "params": {"name": tool_name, "arguments": arguments}})
            resp = self._recv(timeout=timeout)
            if resp and "result" in resp:
                return resp["result"]
            if resp and "error" in resp:
                return {"error": resp["error"]}
            return {"error": "No response from MCP server"}
        except Exception as e:
            return {"error": str(e)}

    def shutdown(self):
        """Close the connection and terminate the subprocess."""
        if self.process and self.process.poll() is None:
            try:
                self.process.stdin.close()
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _send(self, message: dict):
        with self._lock:
            data = json.dumps(message)
            # MCP stdio transport is newline-delimited JSON-RPC — one compact
            # JSON message per line, NOT LSP-style Content-Length framing.
            # (The earlier Content-Length header made the server fail to parse
            # the request and made _recv block forever waiting for a \r\n\r\n
            # terminator the server never sends.)
            self.process.stdin.write(data + "\n")
            self.process.stdin.flush()

    def _recv(self, timeout: float = 10) -> dict | None:
        """Read one newline-delimited JSON-RPC response, with a real timeout.

        Lines arrive via the daemon reader thread + queue started in
        ``connect()`` (see ``_start_reader`` — ``select.select`` cannot wait
        on subprocess pipes on Windows, so this receive must not touch the
        pipe directly). A server that never answers times out cleanly
        (returning None); a server that closed stdout yields the EOF
        sentinel. Server-initiated notifications (lines with no id/result/
        error) are skipped so they don't get mistaken for the response.
        """
        deadline = time.time() + timeout
        while True:
            if self._reader_eof:
                # Stream is gone: only already-queued lines remain. Drain
                # without blocking so a dead server answers immediately on
                # every call (the old select-on-EOF behavior), not after a
                # full timeout each time.
                try:
                    line = self._recv_queue.get_nowait()
                except queue.Empty:
                    return None  # EOF — server closed its stdout
            else:
                remaining = deadline - time.time()
                if remaining <= 0:
                    return None  # timed out — server did not respond
                try:
                    line = self._recv_queue.get(timeout=remaining)
                except queue.Empty:
                    return None  # timed out — server did not respond
            if line is None:
                continue  # EOF sentinel — flag is set; drain any leftovers
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue  # not a complete JSON line; keep reading
            if isinstance(msg, dict) and ("result" in msg or "error" in msg or "id" in msg):
                return msg
            # otherwise it's a notification — keep waiting for the real response


class MCPClientManager:
    """Manages all MCP server connections."""

    def __init__(self):
        self.connections: dict[str, MCPConnection] = {}
        self.all_tools: dict[str, tuple[str, str]] = {}  # namespaced_name -> (server, tool_name)

    def initialize(self):
        """Load registry and connect to all configured servers."""
        if not os.path.exists(MCP_REGISTRY):
            return

        try:
            with open(MCP_REGISTRY) as f:
                registry = json.load(f)
        except Exception as e:
            print(f"[MCP] Failed to read registry: {e}")
            return

        servers = registry.get("servers", [])
        for server_cfg in servers:
            name = server_cfg.get("name", "unknown")
            transport = server_cfg.get("transport", "stdio")

            if transport == "stdio":
                conn = MCPConnection(
                    name=name,
                    command=_expand_placeholders(server_cfg.get("command", "")),
                    args=_expand_placeholders(server_cfg.get("args", [])),
                    env=_expand_placeholders(server_cfg.get("env")),
                )
                if conn.connect():
                    self.connections[name] = conn
                    tools = conn.discover_tools()
                    for tool in tools:
                        namespaced = f"mcp_{name}_{tool['name']}"
                        self.all_tools[namespaced] = (name, tool["name"])
                    print(f"[MCP] Connected to {name}: {len(tools)} tools")
                else:
                    print(f"[MCP] Failed to connect to {name}")
            # HTTP transport can be added later

    def call_mcp_tool(self, namespaced_name: str, parameters: dict) -> dict:
        """Route a tool call to the appropriate MCP server."""
        if namespaced_name not in self.all_tools:
            return {"error": f"Unknown MCP tool: {namespaced_name}"}

        server_name, tool_name = self.all_tools[namespaced_name]
        conn = self.connections.get(server_name)
        if not conn:
            return {"error": f"MCP server {server_name} not connected"}

        return conn.call_tool(tool_name, parameters)

    def get_tool_definitions(self) -> list:
        """Return tool definitions suitable for injection into the model's system prompt."""
        definitions = []
        for conn in self.connections.values():
            for tool in conn.tools:
                namespaced = f"mcp_{conn.name}_{tool['name']}"
                definitions.append({
                    "name": namespaced,
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {}),
                })
        return definitions

    def shutdown(self):
        """Shut down all MCP connections."""
        for conn in self.connections.values():
            conn.shutdown()
        self.connections.clear()
        self.all_tools.clear()


# Module-level singleton
_manager = None


def get_manager() -> MCPClientManager:
    global _manager
    if _manager is None:
        _manager = MCPClientManager()
        _manager.initialize()
    return _manager


def shutdown():
    global _manager
    if _manager:
        _manager.shutdown()
        _manager = None
