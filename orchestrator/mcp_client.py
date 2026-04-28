"""MCP client manager — connects to MCP servers, discovers tools,
routes tool calls through JSON-RPC."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time

WORKSPACE = os.path.expanduser("~/ora/")
MCP_REGISTRY = os.path.join(WORKSPACE, "config/mcp-servers.json")


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

    def connect(self) -> bool:
        """Start the MCP server subprocess and initialize."""
        try:
            cmd = [self.command] + self.args
            proc_env = os.environ.copy()
            if self.env:
                proc_env.update(self.env)

            self.process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=proc_env, text=True,
            )

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
            header = f"Content-Length: {len(data)}\r\n\r\n"
            self.process.stdin.write(header + data)
            self.process.stdin.flush()

    def _recv(self, timeout: int = 10) -> dict | None:
        """Read a JSON-RPC response with timeout."""
        import select
        deadline = time.time() + timeout
        while time.time() < deadline:
            # Read Content-Length header
            line = ""
            while time.time() < deadline:
                try:
                    ch = self.process.stdout.read(1)
                    if not ch:
                        return None
                    line += ch
                    if line.endswith("\r\n\r\n"):
                        break
                except Exception:
                    return None

            # Parse content length
            for header_line in line.strip().split("\r\n"):
                if header_line.lower().startswith("content-length:"):
                    length = int(header_line.split(":")[1].strip())
                    data = self.process.stdout.read(length)
                    try:
                        return json.loads(data)
                    except json.JSONDecodeError:
                        return None
            return None
        return None


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
                    command=server_cfg.get("command", ""),
                    args=server_cfg.get("args", []),
                    env=server_cfg.get("env"),
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
