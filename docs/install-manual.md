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

### 3. Refresh the OpenRouter model catalog

```bash
python3 scripts/refresh-catalog.py
```

Writes `config/model-catalog.json` and `data/model-catalog-changes.jsonl`. This does not require an OpenRouter key because the model-list endpoint is public.

### 4. Sync the model registry

```bash
python3 scripts/sync_model_registry.py sync --no-probe
```

Writes `config/model-registry.json` from OpenRouter, LiteLLM, Chatbot Arena, and public metadata. Artificial Analysis is optional; the install does not require `AA_API_KEY`.

If you intentionally want empirical vision probes and already have an OpenRouter key, omit `--no-probe`.

### 5. Auto-populate the user pipeline

```bash
python3 scripts/auto-populate-configuration.py optimum user-pipeline
```

Writes `config/configurations/user-pipeline.json`.

### 6. Create the Free smoke-test configuration

```bash
python3 scripts/auto-populate-configuration.py free smoke-test-free
```

This verifies that the free preset can produce a concrete configuration. If you have no OpenRouter key, this is the manual smoke-test fallback.

### 7. Optional live OpenRouter smoke test

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

### 8. Start the server

```bash
./start.sh
```

Open <http://localhost:5000>.

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
ollama pull nomic-embed-text
```

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
