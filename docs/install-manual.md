# Manual Install

Last-resort fallback when `scripts/install.py` itself is broken or unavailable. These commands reproduce the install-state the script would produce, by hand. Use this if:

- `install.py` won't run at all (Python missing, import error in the script itself)
- You're auditing what the installer does and want to read it step by step
- You're scripting a more elaborate deployment that hand-rolls some of these steps

If `install.py` runs but fails at a specific step, read `install-recovery.md` instead — that's the right starting point. This document is the nuclear option.

The companion docs:

- **`install-guide.md`** — the happy-path walkthrough using the script
- **`install-recovery.md`** — recover from a partial install failure
- **`install-testing.md`** — formal test protocol

---

## The eight commands

These reproduce a Solo-profile install on macOS Apple Silicon. Adjust paths for your machine.

### 1. Clone the repo

```bash
git clone https://github.com/ora-commons/ora.git ~/ora
cd ~/ora
```

### 2. Verify Python

```bash
python3 --version
# Want: Python 3.11+. If not:
#   brew install python@3.12
#   /opt/homebrew/bin/python3.12 --version
```

Use whichever Python binary is 3.11+. The rest of these commands assume `python3` resolves to it.

### 3. Set API keys

```bash
export OPENROUTER_API_KEY=sk-or-xxxxxxxxxxxxxxxxxxxx
export AA_API_KEY=aa_xxxxxxxxxxxxxxxxxxxx     # optional but strongly recommended
```

Add these to `~/.zshrc` or `~/.bashrc` for persistence.

The `OPENROUTER_API_KEY` is required for catalog refresh and live model calls. `AA_API_KEY` enriches the catalog with intelligence rankings — without it, auto-populate (Step 6 below) falls through to cost-only sort.

### 4. Refresh the model catalog

```bash
python3 scripts/refresh-catalog.py
```

Writes `config/model-catalog.json` (unified OpenRouter + Artificial Analysis catalog) and `data/model-catalog-changes.jsonl` (per-refresh changelog).

If `AA_API_KEY` is unset, prints a multi-line warning and proceeds with OpenRouter-only catalog. Re-run with the key once you have it.

### 5. Auto-populate the user-pipeline configuration

```bash
python3 scripts/auto-populate-configuration.py optimum user-pipeline
```

Runs the Pareto + percentage-floor + cost-sort algorithm against the catalog. Picks 3 models per workhorse slot (Depth, Breadth, Consolidator, Verifier, Formatter) and 2 per utility slot. Writes `config/configurations/user-pipeline.json`.

Re-run any time the catalog changes or you want fresh picks.

### 6. (Optional) Local MLX models via HuggingFace

If you want local models:

```bash
python3 scripts/local_models.py
```

This is the standalone entry point to the local-model selection flow. Detects RAM tier, presents matched options, downloads via `huggingface_hub`. Expect 20-80 GB per model.

Skip this step for API-only operation.

### 7. Smoke test

```bash
python3 -c "
import sys; sys.path.insert(0, 'orchestrator')
from model_dispatch import invoke_chat
result = invoke_chat(
    system_prompt='Respond with exactly one word.',
    user_prompt='What is the capital of France?',
    slot='breadth',
)
print('Result:', repr(result[:200]) if result else 'None')
"
```

Should print `Result: 'Paris'` or similar. Confirms end-to-end routing works.

### 8. Start the server

```bash
./start.sh
```

Opens the chat server at <http://localhost:5000>. The V3 UI renders.

---

## Server install (Linux, API-only)

If you're hand-rolling the server install instead of `install-server.sh`:

### 1. apt deps

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

### 5. Rewrite routing-config.json for server use

```bash
python3 scripts/install_server_config.py
```

This rewrites `config/routing-config.json`'s `slot_assignments`, `default_endpoint`, `gear4_overrides`, and `operational_context` to OpenRouter-only picks. Backs up the original to `routing-config.json.pre-server-install`.

### 6. Save the OpenRouter key

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

Should output `Server install verified.` with five passing checks.

### 8. Verify routing works end to end

```bash
python3 -c "
import sys; sys.path.insert(0, 'orchestrator')
from model_dispatch import invoke_chat
result = invoke_chat(
    system_prompt='Respond with exactly one word.',
    user_prompt='What is the capital of France?',
    slot='breadth',
)
print('Result:', repr(result[:200]) if result else 'None')
"
```

---

## Discipline: stay in sync with the script

If the install scripts evolve (new dependencies, additional steps, schema changes), this document drifts out of date. The script is the source of truth. Treat this document as a snapshot — verify against the current `scripts/install.py` and `scripts/install-server.sh` before relying on a step list that might be stale.

Specifically, watch:

- **`scripts/install.py`'s step list** — if a step is added or renumbered, update this doc's Mac install section.
- **`scripts/install-server.sh`'s `DEPS` array** — if a new Python package is added, mirror it in step 3 of the server section above.
- **`scripts/install_server_config.py`'s `SERVER_SLOT_ASSIGNMENTS`** — if the default picks change, mirror them or just say "run the script for current picks."

The maintenance burden is real. If you find this doc out of sync with the scripts, file an issue or fix it in place.

## Related documents

- `install-guide.md` — happy-path script walkthrough
- `install-recovery.md` — script failure diagnosis
- `install-testing.md` — formal test protocol
- `cloud-ora-install.md` — server-install operator guide
