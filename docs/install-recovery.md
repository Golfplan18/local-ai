# Install Recovery

What to do when `scripts/install.py` or `scripts/install-server.sh` fails partway through. Both installers are idempotent — re-running them skips work that's already done — but some failures need manual diagnosis before re-running will help.

The companion docs:

- **`install-guide.md`** — the happy-path walkthrough
- **`install-manual.md`** — eight-command fallback when the script itself is broken
- **`install-testing.md`** — formal test protocol

---

## First steps for any failure

### 1. Read `install.log`

`scripts/install.py` writes structured output to stdout that's worth capturing:

```bash
python3 scripts/install.py --profile solo 2>&1 | tee ~/ora/install.log
```

Re-running with the log redirected makes failure diagnosis much easier. The log ends with one of:

- `INSTALL_COMPLETE: 0 warnings, 0 errors` — success
- A step that exited non-zero — that's where to look

### 2. Check install state

The installer persists progress to `~/ora/install-state.json`:

```bash
cat ~/ora/install-state.json
```

Shows which steps completed. Re-running the installer skips completed steps and resumes from the first incomplete one.

### 3. Try `--dry-run` first

Before re-running for real, see what the installer thinks it'll do:

```bash
python3 scripts/install.py --profile solo --dry-run
```

`--dry-run` prints every action without executing. If `--dry-run` says it would re-do a step you thought was done, your state file may have been reset.

### 4. Worst case: `--reset`

```bash
python3 scripts/install.py --reset
```

Clears `~/ora/install-state.json`. Next run starts from scratch. **Doesn't undo file-level changes** — if Step 5 wrote `config/configurations/user-pipeline.json`, that file stays. `--reset` just makes the installer forget it's already done.

---

## Common failures and fixes

### Step 1 — Preflight checks

#### "Python 3.x found; need 3.11+"

macOS ships with Python 3.9, which lacks newer type-hint syntax (`dict | None` for example).

```bash
brew install python@3.12
# Verify:
which python3.12
python3.12 --version
# Run installer with the explicit binary:
/opt/homebrew/bin/python3.12 scripts/install.py --profile solo
```

If you've installed a newer Python but `python3 --version` still shows 3.9, your `PATH` order is wrong. Either fix `PATH` or invoke the binary explicitly as above.

#### "Disk space: only X GB free; need 5+ GB"

Free up disk. Most likely culprits: old Xcode CLI tools, large iCloud caches, abandoned Docker volumes. The installer wants 5 GB for the install itself; local models on top add 20-80 GB per model.

#### "OpenRouter API unreachable"

Network issue. Check:

```bash
curl -I https://openrouter.ai/api/v1/models
```

If that fails too, you've got a connectivity problem (DNS, firewall, VPN). Fix the network and re-run. The catalog endpoint does not require an API key.

#### "Write permission denied at /Users/.../ora"

The repo directory isn't writable by your user. Either you cloned as root (don't), or `chmod` is off:

```bash
ls -la ~/ora | head -3
chown -R "$USER:staff" ~/ora 2>/dev/null   # macOS
# or:
chown -R "$USER:$USER" ~/ora               # Linux
```

### Step 2 — Profile selection

If you pass `--profile hybrid` or `--profile organization`, the installer exits with:

> Profile 'hybrid' is reserved for future Ora installs, not supported today.

Hybrid and Organization profiles are reserved in `DEPLOYMENT_PROFILES` but disabled pending network-discovery and concurrency validation. Use `--profile solo` for the desktop install. For server installs, use `scripts/install-server.sh` instead.

### Step 3 — Catalog refresh

#### "Catalog refresh failed"

The desktop installer fetches the public OpenRouter model list. This step does not require `OPENROUTER_API_KEY`.

Common causes:

- OpenRouter catalog outage or rate limit. Wait a minute and re-run.
- Network, DNS, firewall, or VPN issue. Confirm `curl -I https://openrouter.ai/api/v1/models` works.
- A local Python dependency error. Read the stderr and install the missing package if one is named.

#### "Catalog refresh failed (exit N)"

The refresh subprocess errored. Look at the stderr in the installer output. Common causes:

- **OpenRouter catalog rate limit.** Wait 60 seconds and re-run.
- **Network blip.** Re-run.
- **Python dependency/import error.** Install the missing dependency or use the same Python binary the installer uses.

#### "Catalog refresh timed out after 120s"

Slow network or upstream catalog hiccup. Re-run; if it times out twice in a row, run the refresh directly to see the actual error:

```bash
cd ~/ora
python3 scripts/refresh-catalog.py
```

### Step 4 — Model registry sync

#### "Registry sync failed"

Registry sync is non-fatal. The installer logs a warning and proceeds with routing-config capability fallback. Re-run later with:

```bash
python3 scripts/sync_model_registry.py sync
```

Artificial Analysis is optional. The install path uses public Chatbot Arena/OpenRouter/LiteLLM data by default; an AA key can improve model-selector data after install but is not required.

### Step 5 — Auto-populate

#### "Auto-populate failed"

The most common cause: the catalog from Step 3 is empty or malformed. Verify:

```bash
python3 -c "import json; c = json.load(open('config/model-catalog.json')); print('models:', len(c.get('models', [])))"
```

If `models: 0`, re-run Step 4 (catalog refresh) — something broke the catalog. If model count looks healthy (~300+), look at the auto-populate stderr for the actual error.

You can re-run auto-populate directly:

```bash
python3 scripts/auto-populate-configuration.py optimum user-pipeline
```

Add `--verbose` if it's available, or just inspect the output configuration file:

```bash
cat config/configurations/user-pipeline.json
```

### Step 6 — Smoke test

#### "Smoke test failed"

The installer auto-populates a Free configuration. If an OpenRouter key is present in env or keyring, it sends one tiny live test prompt. Without a key, it validates the configuration and skips the live round-trip.

```bash
cd ~/ora
python3 -c "
import sys; sys.path.insert(0, 'orchestrator')
from model_dispatch import invoke_chat
print(invoke_chat(
    system_prompt='Respond with exactly one word.',
    user_prompt='Say hello.',
    slot='breadth',
))
"
```

If that returns a string, slot routing works and the smoke-test failure was probably a one-off. Re-run the installer.

If it errors, the error message points at the problem (missing model, invalid key, network).

#### "OpenRouter rejected the key"

The key exists but failed authentication. Update it in Settings -> External APIs or export a known-good key:

```bash
export OPENROUTER_API_KEY=sk-or-xxxxxxxxxxxxxxxxxxxx
python3 scripts/install.py --profile solo --resume
```

#### "Free models are rate-limited and sometimes unavailable"

That message is not an install failure. The configuration passed, but the live free-model test did not complete. Add OpenRouter credits/payment or direct provider keys for reliable daily model access.

### Step 7 — External APIs orientation

This step is informational. If a browser page fails to open automatically, copy the link from the log and paste it into your browser. You can also skip it and add keys later in Settings -> External APIs.

---

## Server install (`install-server.sh`)

The server installer's failure modes are different — apt, ollama, and venv setup dominate.

### apt-get install failed

```bash
sudo apt-get update
sudo apt-get install python3-venv python3-pip git curl
```

Run those by hand. If apt itself errors, fix the underlying issue (sources.list, dpkg locks, disk full) before re-running the installer.

### ollama install failed

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama --version
```

If the install script errors, follow ollama's documentation. The `bge-m3` pull happens separately and restores Ora's 1,024-dimensional fresh-install embedding profile:

```bash
ollama pull bge-m3
```

You can re-run `install-server.sh` after this — the `command -v ollama` check skips re-install.

### `--skip-ollama` if you don't need ChromaDB RAG

If you're standing up a non-RAG server install (rare), pass `--skip-ollama` to skip ollama install and the embedding-model pull entirely.

### Python deps failed

```bash
cd ~/ora
source .venv/bin/activate
pip install --upgrade pip
pip install flask flask-cors requests pyyaml jsonschema referencing pydantic chromadb python-pptx python-docx xlsxwriter anthropic openai google-generativeai keyring
```

Inspect the actual pip error if a specific package fails (often network or wheel-build issues on minimal images).

### Smoke test failed on server

Re-run by hand:

```bash
cd ~/ora
source .venv/bin/activate
set -a; source ~/.config/ora-server.env; set +a
python3 scripts/install_server_smoke.py
```

Five checks; the failure message identifies which. Common fixes:

- `routing-config.json loads` fails → check the file is syntactically valid JSON
- `every slot resolves` fails → re-run `scripts/install_server_config.py` to rewrite the slot assignments
- `no slot references a local model` fails → same as above
- `OPENROUTER_API_KEY in env` fails → `source ~/.config/ora-server.env` before running the smoke test
- `chromadb is importable` fails → `pip install chromadb` in the venv

---

## When in doubt: nuke and re-install

If the install is in a state that makes no sense, the cleanest recovery is to start over:

### Mac

```bash
cd ~
# Move the broken install aside (don't delete — diagnose later if you care):
mv ora ora.broken.$(date +%Y%m%d-%H%M)
git clone https://github.com/ora-commons/ora.git ora
cd ora
python3 scripts/install.py --profile solo
```

If you have local model files at `~/ora/models/`, move them aside before the rename or copy them into the new install location.

### Server

```bash
cd ~
mv ora ora.broken.$(date +%Y%m%d-%H%M)
git clone https://github.com/ora-commons/ora.git ora
cd ora
./scripts/install-server.sh
```

The uninstall script (`uninstall/uninstall.py`) is the more careful path — preserves your conversation history and gives you a typed-DELETE confirmation. Read its `--help`.

---

## Asking for help

If you've tried the above and the install still won't go:

1. Capture the full install output:
   ```bash
   python3 scripts/install.py --profile solo 2>&1 | tee install-failure.log
   ```
2. Note your platform: `sw_vers` (macOS) or `lsb_release -a` (Linux), `python3 --version`, free disk space, free RAM.
3. Note the step that failed and the exact error message.
4. Open an issue at <https://github.com/ora-commons/ora/issues> with the log and the platform info.

## Related documents

- `install-guide.md` — happy-path walkthrough
- `install-manual.md` — bypass the script entirely with manual commands
- `install-testing.md` — formal test protocol
- `cloud-ora-install.md` — server install operator guide
