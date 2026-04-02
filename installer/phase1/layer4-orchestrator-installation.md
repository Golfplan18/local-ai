### PHASE 1, LAYER 4: ORCHESTRATOR INSTALLATION

**Stage Focus:** Install the Python orchestrator that makes boot.md tool calls functional.

### Processing Instructions

The orchestrator (boot.py) is the thin Python layer that reads boot.md, detects tool calls in the model's output, executes them, and injects results back into the conversation. It contains no intelligence — all behavioral decisions live in the boot.md specification. The orchestrator is mechanical plumbing.

The orchestrator maintains an **endpoint registry** — a configuration file listing all available AI endpoints, both local and cloud. The gear system routes to appropriate endpoints based on the registry. Boot files are identical across all tiers; only the endpoint registry differs.

1. Generate `[workspace]/orchestrator/boot.py` — a Python script implementing the detect→execute→inject loop. The orchestrator must:

   a. **Read the active boot.md** from `[workspace]/boot.md` and inject it as the system prompt.

   b. **Read the endpoint registry** from `[workspace]/config/endpoints.json`. The registry lists available endpoints with their type (local, browser, api), URL, model name, and status (active/inactive).

   c. **Call the AI model** through the appropriate endpoint:
      - IF local endpoint: HTTP POST to the local inference engine's API (Ollama or MLX).
      - IF browser endpoint: delegate to `browser_evaluate` tool (Playwright automation).
      - IF api endpoint: delegate to the appropriate API client (Anthropic, OpenAI, Google).

   d. **Detect tool calls** in the model's response. Parse the `<tool_call>` XML tags defined in boot.md. Extract the tool name and parameters.

   e. **Execute the tool:**
      - `web_search`: Call `DDGS().text(query, max_results=N)`. Import with `try: from ddgs import DDGS` and fall back to `from duckduckgo_search import DDGS`. Return results as formatted text.
      - `file_read`: Read the file at the specified path (validated within workspace). Return contents.
      - `file_write`: Write content to the specified path (validated within workspace). Return confirmation.
      - `knowledge_search`: Query the ChromaDB vector database. Two collections: `knowledge` (indexes the vault at the path stored in endpoints.json) and `conversations` (indexes processed turn-pair chunks in `~/Documents/conversations/`). The `knowledge` collection supports semantic similarity search with provenance weighting. The `conversations` collection supports both timestamp-sorted retrieval (for prompt cleanup) and semantic similarity retrieval (for historical memory). Return ranked results with source metadata.
      - `browser_open`: Call `webbrowser.open(url)`. Return confirmation. (Used by the API Key Acquisition Framework.)
      - `credential_store`: Call `keyring.set_password(service, username, key)` to store. Call `keyring.get_password(service, username)` to retrieve. Return confirmation or value.
      - `browser_evaluate`: Send a prompt to a commercial AI via Playwright browser automation. Uses existing logged-in sessions. Returns the model's response. See Phase 1, Layer 5 for setup.

   f. **Inject the tool result** back into the messages array and call the model again.

   g. **Detect the stop condition**: when the model's response contains no tool calls, deliver the response to the user.

   h. **Safety validation**: before executing file_read or file_write, validate the path against allowed locations. User content writes resolve against the vault path from endpoints.json. Conversation data writes resolve against `~/Documents/conversations/`. Configuration writes (setup frameworks only) resolve against `[workspace]/config/`. Reject paths containing `..` or paths to sensitive directories. Reject paths matching the deny list: `.ssh`, `.gnupg`, `.env`, credential files. The AI never writes to the system folder during normal operation except to config/.

   i. **Operational context enforcement**: IF the system is running in autonomous mode (no human in the loop), THEN restrict tool access to local-only endpoints by default. Browser automation and API calls are prohibited during unattended work unless explicitly pre-authorized in the task specification.

2. Generate the endpoint registry template at `[workspace]/config/endpoints.json`:

   ```json
   {
     "vault_path": null,
     "conversations_path": "~/Documents/conversations/",
     "chromadb_path": "[workspace]/chromadb/",
     "endpoints": [],
     "default_endpoint": null,
     "operational_context": {
       "interactive": ["local", "browser", "api"],
       "autonomous": ["local"],
       "agent": ["local"]
     }
   }
   ```

   The registry starts with vault_path null (set during Layer 2 when the user chooses a vault location) and is populated with endpoints during Layers 5 (commercial AI connections) and Phase 2 (local model). The gear system routes to whatever endpoints are available.

3. Generate tool implementation files in `[workspace]/orchestrator/tools/`:
   - `web_search.py`
   - `file_ops.py` (read and write)
   - `knowledge_search.py`
   - `browser_open.py`
   - `credential_store.py`
   - `browser_evaluate.py`

   Each tool file contains a single function matching the tool's interface.

4. Generate a `[workspace]/boot/boot.md` specification file. This file is the system prompt that tells the model what tools are available and how to invoke them. It must specify:
   - The `<tool_call><n>…</n><parameters>{…}</parameters></tool_call>` XML format for invoking tools.
   - All seven tools with parameter definitions and examples: `web_search`, `file_read`, `file_write`, `knowledge_search`, `browser_open`, `credential_store`, `browser_evaluate`.
   - The workspace directory layout.
   - Safety rules (workspace-only file access, no credential files).
   - Behavioral guidelines (use tools when genuinely useful, stream output to `output/`, reference past sessions via `knowledge_search`).

5. Test the orchestrator:
   a. Import all tool modules directly and confirm no import errors.
   b. Call `file_write` to create a test file in `output/`, then `file_read` to confirm the contents match.
   c. Attempt `file_read` on a path outside the workspace (e.g., `/etc/passwd`). Verify it is rejected with a "blocked" message.
   d. Call `web_search` with a short query. Verify results are returned (not empty, no exception).
   e. Verify the endpoint registry template was created and is valid JSON.

### Output Format for This Layer

```
ORCHESTRATOR INSTALLED
Location: [workspace]/orchestrator/boot.py
Boot spec: [workspace]/boot/boot.md
Endpoint registry: [workspace]/config/endpoints.json
Tools: web_search, file_read, file_write, knowledge_search, browser_open, credential_store, browser_evaluate
Safety validation: [Pass / Fail]
Tool tests: [Pass / Fail with details]
```

---

