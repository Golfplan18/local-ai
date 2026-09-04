# Manual Install

Last-resort fallback when `scripts/install.py` itself is broken or unavailable. These commands reproduce the install state the script would normally produce for the Solo source-install path.

If `install.py` runs but fails at a specific step, use `install-recovery.md` first. This document is for cases where the script cannot run at all or you need to audit the install by hand.

Companion docs:

- `install-guide.md` — happy-path script walkthrough
- `install-recovery.md` — recover from a partial install failure
- `install-testing.md` — formal test protocol
- `cloud-ora-install.md` — server-install operator guide

---

## Desktop source install by hand

### 1. Clone the repo

```bash
git clone https://github.com/ora-commons/ora.git ~/ora
cd ~/ora
```

On Windows PowerShell:

```powershell
git clone https://github.com/ora-commons/ora.git $env:USERPROFILE\ora
cd $env:USERPROFILE\ora
```

### 2. Verify Python

```bash
python3 --version
```

You want Python 3.11 or newer. On Windows:

```powershell
py -3 --version
```

### 3. Install the Python dependencies

```bash
python3 -m pip install -r requirements.txt
```

Nothing else in the repo installs these, and the server imports `flask`, `requests`, `chromadb`, `keyring`, `openai`, and `yaml` at module scope. If pip refuses with `externally-managed-environment` (Homebrew and most distro Pythons are PEP 668 managed), create the isolated environment the launchers prefer instead:

```bash
python3 -m venv .venv
.venv/bin/python3 -m pip install -r requirements.txt
```

The script also installs the three pinned MCP servers from `mcp-runtime/package-lock.json` and their exact Playwright browser, which needs Node.js and npm:

```bash
cd mcp-runtime && npm ci --ignore-scripts --no-audit --no-fund && cd ..
node mcp-runtime/patch-playwright.cjs
PLAYWRIGHT_BROWSERS_PATH=0 node mcp-runtime/node_modules/playwright-core/cli.js install chromium
```

The patch binds approved browser interactions to their reviewed Page, document, and native target. Apply it after installing the pinned packages; Ora refuses an unpatched connector at startup.

`PLAYWRIGHT_BROWSERS_PATH=0` is not optional. It puts Chromium inside the package's own `.local-browsers` directory instead of the shared per-user cache, and Ora accepts only the package-local copy — both `install.py` and `orchestrator/mcp_client.py` re-resolve the browser with that variable set and refuse it if it lands anywhere else.

### 4. Create the vault if you do not have one

The script creates the vault when the resolved vault path does not exist, and never writes into an existing one. That path is `~/Documents/vault` unless `ORA_VAULT` or `ORA_DOCUMENTS` moves it. By hand, that is:

```bash
mkdir -p ~/Documents/vault/"Projects/Ora" \
         ~/Documents/vault/Sessions \
         ~/Documents/vault/Engrams \
         ~/Documents/vault/Resources \
         ~/Documents/vault/Administration
```

If you already have a vault, skip this — leave it exactly as it is.

### 5. Install the Word/PDF converters

```bash
python3 scripts/converters.py
```

Ora renders Word (`.docx`) and PDF by handing markdown to Pandoc, with Typst as the PDF engine. This uses whatever the machine already has and otherwise downloads the publishers' pinned, checksum-verified releases into `data/converters/bin`. Add `--dry-run` to see what it would do without changing anything. Skipping this step costs you Word and PDF export and nothing else.

### 6. Refresh the OpenRouter model catalog

```bash
python3 scripts/refresh-catalog.py
```

Writes `config/model-catalog.json` and `data/model-catalog-changes.jsonl`. This does not require an OpenRouter key because the model-list endpoint is public. A catalog already ships in the repository, so if OpenRouter is unreachable you can skip this step and carry on against the packaged copy — the picks will simply be as current as that file's date.

### 7. Sync the model registry

```bash
python3 scripts/sync_model_registry.py sync --no-probe
```

Writes `config/model-registry.json` from OpenRouter, LiteLLM, Chatbot Arena, and public metadata. Artificial Analysis is optional; the install does not require `AA_API_KEY`.

If you intentionally want empirical vision probes and already have an OpenRouter key, omit `--no-probe`.

### 8. Auto-populate the user pipeline and bake the presets

```bash
python3 scripts/auto-populate-configuration.py budget user-pipeline
```

Writes `config/configurations/user-pipeline.json` from the **Budget** preset. The valid preset names are `premium`, `budget`, `speed`, and `free`; there is no "optimum".

The script also bakes the four preset cards the Models pane shows. Free is the only one that mixes locally installed models into its picks, and the code that does it refuses to guess: with no `config/models.json` it raises rather than route to a model that may not be on disk. That file is machine-local and never committed, so a fresh clone has none and a bake run on its own gets three cards and an error where Free should be. Record the inventory first, exactly as the installer and the Models pane both do, and then bake:

```bash
mkdir -p ~/ora/models
python3 -m orchestrator.local_model_discovery --write
python3 -c "from orchestrator import active_configuration as ac; print(ac.bake_missing_presets(force=True, log=print))"
```

Finding no local models is an ordinary answer, not a failure: the scan records an empty inventory and Free keeps its cloud picks. All four names should come back from the bake — `['free', 'budget', 'speed', 'premium']`.

Without this, the cards are baked the first time you open Settings → Models instead; that pane runs the same scan before it bakes.

### 9. Create the Free smoke-test configuration

```bash
python3 scripts/auto-populate-configuration.py free smoke-test-free
```

This verifies that the free preset can produce a concrete configuration. If you have no OpenRouter key, this is the manual smoke-test fallback.

### 10. Optional live OpenRouter smoke test

Only run this if you have an OpenRouter key in the environment:

```bash
export OPENROUTER_API_KEY=sk-or-xxxxxxxxxxxxxxxxxxxx
python3 -c "
import json, os, urllib.request
payload = json.dumps({
    'model': 'openrouter/free',
    'messages': [
        {'role': 'system', 'content': 'Reply with exactly: Ora install smoke ok'},
        {'role': 'user', 'content': 'Smoke test.'},
    ],
    'temperature': 0,
    'max_tokens': 12,
}).encode('utf-8')
req = urllib.request.Request(
    'https://openrouter.ai/api/v1/chat/completions',
    data=payload,
    headers={
        'Authorization': 'Bearer ' + os.environ['OPENROUTER_API_KEY'],
        'Content-Type': 'application/json',
        'HTTP-Referer': 'https://ora-ai.app',
        'X-Title': 'Ora manual smoke test',
    },
    method='POST',
)
print(urllib.request.urlopen(req, timeout=45).read().decode('utf-8')[:500])
"
```

Free models are rate-limited and sometimes unavailable. A valid key with an unavailable free model is not the same thing as a broken install.

### 11. Start the server

On macOS, the recommended durable start installs and verifies the per-user
launchd service:

```bash
./scripts/ora-launchd.sh install
```

On Linux/WSL, or for a deliberately unsupervised macOS session, use
`./start.sh`; on Windows, use `start.bat`. Open the origin for the exact health
port it reports (5000–5010), rather than assuming port 5000 is free.

---

## Optional local models

After the source install works:

```bash
python3 scripts/install.py models
```

or:

```bash
python3 scripts/local_models.py
```

The local-model helper detects RAM tier, presents model options, and asks before downloading. Skip this for API-only operation.

---

## API keys after manual install

Add keys in **Settings -> External APIs** after the UI starts. Recommended starter package:

- OpenRouter for broad cloud-model access.
- Tavily for AI-oriented search.
- Artificial Analysis for model-selector intelligence.

Direct vendor keys can bypass OpenRouter's gateway markup for that vendor's own models. Speech/image/video keys are optional and only matter when those features are selected.

---

## Server install by hand

For Linux API-only server installs, prefer `scripts/install-server.sh`. If hand-rolling:

### 1. Install apt deps

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git curl
```

### 2. Clone

```bash
git clone https://github.com/ora-commons/ora.git ~/ora
cd ~/ora
```

### 3. Venv + Python deps

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install flask flask-cors requests pyyaml jsonschema referencing pydantic \
            chromadb python-pptx python-docx xlsxwriter \
            anthropic openai google-generativeai keyring
```

### 4. Ollama for ChromaDB embeddings

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull bge-m3
```

`bge-m3` at 1,024 dimensions is the tracked fresh-install profile in `config/chromadb.json.template` and the runtime fallback when no machine-specific `config/chromadb.json` exists. If you select another embedder, its vector dimension and physical collection names must change with it.

### 5. Rewrite routing config for server use

```bash
python3 scripts/install_server_config.py
```

### 6. Save server API keys

```bash
mkdir -p ~/.config
cat > ~/.config/ora-server.env <<'EOF'
OPENROUTER_API_KEY=sk-or-xxxxxxxxxxxxxxxxxxxx
EOF
chmod 600 ~/.config/ora-server.env
```

### 7. Smoke test

```bash
source .venv/bin/activate
set -a; source ~/.config/ora-server.env; set +a
python3 scripts/install_server_smoke.py
```

---

## Stay in sync with the script

The script is the source of truth. If `scripts/install.py`, `scripts/install-server.sh`, or their helper scripts change, update this manual fallback immediately.
