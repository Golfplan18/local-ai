# Your Local AI System

This page describes a source install of Ora. The live installer is:

```bash
cd ~/ora
python3 scripts/install.py --profile solo
```

## Starting
Double-click **Local AI.command** on your Desktop.
Your browser will open to http://localhost:5000 — your AI chat interface.

## Stopping
Run: ~/ora/stop.sh
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
(The AI updates the active named configuration and routing settings. The old
`config/endpoints.json` registry is retired.)

## Your System Files

- **boot.md** (~/ora/boot/boot.md): The active system specification.
  Your AI reads this file as its operating instructions.

- **Vault** (~/Documents/vault/): Put files here that you want your AI to search.
  Notes, documents, project files — anything you would like the AI to reference.

- **Conversations** (~/Documents/conversations/): Session logs saved automatically.

- **Frameworks** (~/ora/frameworks/): The framework library.
  Your AI can execute any framework by name.

- **config/routing-config.json**: Stores runtime routing and user paths.

- **config/model-registry.json** and **config/model-catalog.json**: Store model
  capability metadata and available model inventory.

- **config/configurations/**: Stores named routing presets such as Free, Budget,
  Optimum, and Premium.

## Commercial AI Access

Commercial AI access is via direct API providers or OpenRouter. Set up
keys in the Settings panel's External APIs tab, or run
`/framework api-key-setup` from the chat.

## If Something Goes Wrong

- **Browser shows "connection refused"**: Server isn't running. Click the launcher.
- **Browser shows "No AI endpoints configured"**: Run `~/ora/start.sh`, then review
  Settings -> Models and Settings -> External APIs.
- **Tool calls not executing** (you see <tool_call> tags in responses): You may be connected
  directly to a commercial AI instead of localhost:5000. Always use the launcher.
- **Garbled output from local model**: Run this framework again to re-check the chat template.

## Updating

To update framework library when the repository is published:
  cd ~/ora/frameworks/book && git pull

To add API keys:
  Open Settings -> External APIs, or run `/framework api-key-setup` from chat.
