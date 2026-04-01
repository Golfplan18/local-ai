# Your Local AI System

## Starting
Double-click **Local AI.command** on your Desktop.
Your browser will open to http://localhost:5000 — your AI chat interface.

## Stopping
Run: ~/local-ai/stop.sh
Or close the terminal window that appeared when you started.

## How This Works

Your AI interface runs at localhost:5000 — a small server on your machine that keeps Python in
the loop between you and the AI model.

This matters because your AI can use tools — web search, file access, knowledge search — and those
tools run in Python. The browser interface at localhost:5000 IS the orchestrator interface.
Tool calls execute automatically, invisibly, before you see the final response.

Do not use claude.ai, ChatGPT, or Gemini directly for work that requires tools. Those interfaces
have no Python in the loop. Use localhost:5000.

## Your Models

**Default: gpt-oss-120b (MXFP4)**
~120B parameters, ~62 GB RAM. Large-scale open model. Strong for long-form generation,
broad knowledge, and complex tasks.

**Also installed:**
- DeepSeek-R1-Distill-Llama-70B (5-bit MLX, ~46 GB) — strong reasoning model
- gpt-oss-20b (4-bit MLX, ~12 GB) — faster, lighter, good for quick tasks

To switch models, tell your AI: "Switch to DeepSeek" or "Use the 20B model"
(The AI will update endpoints.json and restart routing.)

## Your System Files

- **boot.md** (~/local-ai/boot/boot.md): The active system specification.
  Your AI reads this file as its operating instructions.

- **Vault** (~/Documents/vault/): Put files here that you want your AI to search.
  Notes, documents, project files — anything you would like the AI to reference.

- **Conversations** (~/Documents/conversations/): Session logs saved automatically.

- **Frameworks** (~/local-ai/frameworks/): The framework library.
  Your AI can execute any framework by name.

- **config/endpoints.json**: Lists your available AI connections.

## Commercial AI Access

Your system has browser sessions for Claude, ChatGPT, and Gemini.
These are used for browser_evaluate tool calls (adversarial evaluation, second opinions).

To reconnect after a session expires:
Tell your AI: "Read and execute frameworks/browser-eval-setup.md"

## If Something Goes Wrong

- **Browser shows "connection refused"**: Server isn't running. Click the launcher.
- **Browser shows "No AI endpoints configured"**: Run ~/local-ai/start.sh and check endpoints.json.
- **Tool calls not executing** (you see <tool_call> tags in responses): You may be connected
  directly to a commercial AI instead of localhost:5000. Always use the launcher.
- **Garbled output from local model**: Run this framework again to re-check the chat template.

## Updating

To update framework library when the repository is published:
  cd ~/local-ai/frameworks/book && git pull

To add API keys:
  Tell your AI: "Read and execute frameworks/api-key-setup.md"
