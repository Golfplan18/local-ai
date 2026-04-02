### PHASE 1, LAYER 7: UNIVERSAL CHAT SERVER

**Stage Focus:** Install a browser-accessible chat interface with the agentic loop fully integrated, so every reader — including Tier 0 — can interact with the system through a browser rather than a terminal, with tool calls executing automatically.

### Why This Layer Exists

boot.py (installed in Layer 4) provides a functional agentic loop in the terminal. A terminal interface is useful for debugging and scripting but is not the primary interface for most readers. More importantly, a reader who opens a commercial AI chat interface directly — bypassing the orchestrator entirely — will encounter the Unmanned Chat Trap: the model issues tool calls that nothing intercepts.

The universal chat server closes this gap. After this layer completes, the browser interface IS the orchestrator interface for all tiers.

### Processing Instructions

1. Generate `[workspace]/server/server.py` — a Python HTTP server implementing a browser chat interface with integrated agentic loop. The server must:

   a. **Serve a chat interface** on `localhost:5000` (or the next available port if 5000 is in use). The interface is a simple HTML page with a text input, a send button, and a response display area. Responses stream token by token so the user sees output as it is generated.

   b. **Auto-inject boot.md as the system prompt** on every conversation. Read `[workspace]/boot/boot.md` at request time (not at server startup) so that changes to boot.md take effect without restarting the server.

   c. **Route to the active endpoint** from the endpoint registry (`[workspace]/config/endpoints.json`). Select the `default_endpoint`. IF no default is set, select the first active endpoint. IF no endpoints are active, display a clear message in the chat interface: "No AI endpoints are configured. Add a commercial AI connection or install a local model to begin."

   d. **Implement the agentic loop** identically to boot.py:

   ```
   receive user message
   append to conversation history
   call model via active endpoint
   receive response — buffer all tokens
   IF response contains <tool_call> tags:
       parse tool name and parameters
       execute tool via tool dispatcher
       yield brief status token to browser (e.g., "[searching web...]")
       append tool result to conversation history
       call model again with updated history
       REPEAT
   IF no tool calls (or after tool loop completes):
       stream final response tokens to browser in real time
   ```

   e. **Import tool implementations** from `[workspace]/orchestrator/tools/`. Wrap all imports in try/except. IF imports fail, set `TOOLS_AVAILABLE = False` and display a warning in the chat interface header: "Tool access unavailable — orchestrator not found." Do not crash on import failure.

   f. **Maintain conversation history** in memory for the duration of the server session. Each new browser window or tab starts a fresh conversation. History does not persist across server restarts — session logging (boot.md's log-writing behavior) handles persistence.

   g. **Apply safety validation** on all file tool calls: validate paths are within workspace, reject deny-listed patterns. Same rules as boot.py.

   h. **Respect operational context**: In interactive mode (server running with a user present), all endpoints are available. Do not restrict to local-only unless the task specification explicitly requests autonomous mode.

   i. **Maximum agentic loop iterations**: 10. If the limit is reached, stream whatever the model last produced.

2. Generate `[workspace]/server/index.html` — the chat interface frontend. Requirements:

   - Clean, readable layout — this is a daily-use interface.
   - Text input at the bottom, conversation display above, scrolling history.
   - Brief tool status indicators visible during tool execution (e.g., "[searching web…]" appears, then is replaced by the actual response).
   - A small status indicator showing the active endpoint name (e.g., "Claude via browser" or "local-mlx").
   - No external dependencies — all CSS and JavaScript inline or from a local file. The server must function without internet access.
   - Visually clean and readable — dark text on light background, adequate font size, reasonable margins.
   - Display the active model name and a status indicator in the header.
   - Include a brief footer: "Built with the Local AI First Boot Framework — Natural Language Programming for AI Agents."

3. Generate `[workspace]/server/start-server.sh` (macOS/Linux) and `[workspace]/server/start-server.bat` (Windows) — shell scripts that launch the server and open the browser interface.
4. Test the server:

   a. Start the server: `python3 [workspace]/server/server.py &`
   b. Wait 3 seconds for startup.
   c. Send a test request to `localhost:5000/chat` with the message: "What tools do you have access to?"
   d. Verify the response arrives and mentions the tools defined in boot.md.
   e. Send a second test request: "Search the web for today's date." — this should trigger a web_search tool call and return a result.
   f. Verify tool execution: the response should contain information retrieved from the web, not a refusal or a made-up date.
   g. Stop the test server: `pkill -f server.py` (macOS/Linux) or equivalent.

   IF test (d) fails: the server is not routing to any endpoint — check endpoint registry.
   IF test (f) fails: the agentic loop is not intercepting tool calls — verify the loop implementation in step 1d.

5. Generate a desktop launcher:

   IF Phase 2 will not execute (hardware does not support local models):

   - Generate the desktop launcher now, pointing to `start-server.sh` or `start-server.bat`.
   - This launcher starts the server and opens `localhost:5000` in the default browser.
   - Label: "Local AI" (same label regardless of tier — the user experience is identical).

   IF Phase 2 will execute (hardware supports local models):

   - Skip launcher generation here — Phase 2, Layer 7 generates the launcher after the local model is configured.
   - The Phase 2 launcher will point to the same server.py — no separate launcher is needed.

### Output Format for This Layer

```
UNIVERSAL CHAT SERVER INSTALLED
Location: [workspace]/server/server.py
Interface: http://localhost:5000
Active endpoint: [endpoint name from registry, or "none configured"]
Agentic loop: integrated
Tool access: [list of tools available, or "unavailable — import failed"]
Server test — endpoint routing: [PASS / FAIL]
Server test — tool execution: [PASS / FAIL]
Desktop launcher: [generated / deferred to Phase 2]
```

---

