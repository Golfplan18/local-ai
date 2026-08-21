# Install Recovery

What to do when `scripts/install.py` or `scripts/install-server.sh` fails partway through. Both installers are idempotent — re-running them skips work that's already done — but some failures need manual diagnosis before re-running will help.

The companion docs:

- **`install-guide.md`** — the happy-path walkthrough
- **`install-manual.md`** — manual command fallback when the script itself is broken
- **`install-testing.md`** — formal test protocol

---

## First steps for any failure

### 1. Read `install.log`

`scripts/install.py` writes every line it prints to `~/ora/install.log` itself — you do not need to redirect anything. Read it after a failed run:

```bash
tail -n 60 ~/ora/install.log
```

The file is appended to across runs, so the last run's output is at the end. The log ends with one of:

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

Deletes `~/ora/install-state.json` **and** `~/ora/install.log`, then writes its own one-line confirmation into a fresh log — so everything the failed run recorded above is gone. Copy anything you still need out of `install.log` before you run this. Next run starts from scratch. **Doesn't undo file-level changes** — if Step 7 wrote `config/configurations/user-pipeline.json`, that file stays. `--reset` just makes the installer forget it's already done.

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

#### "Cannot reach OpenRouter"

**This is a warning, not a failure.** Pre-flight reports it and the install continues; Step 5 falls back to the model catalog packaged with this checkout, and only halts if that packaged catalog is missing or unusable. Every preset and the user pipeline bake correctly from the packaged copy, so the cost of installing during an outage is that models released since the packaged catalog's date are missing, and prices, context windows, and rankings are as of that date.

If you would rather fix the network first, check:

```bash
curl -I https://openrouter.ai/api/v1/models
```

If that fails too, you've got a connectivity problem (DNS, firewall, VPN). The catalog endpoint does not require an API key. Once the network is back, `python3 scripts/refresh-catalog.py` brings the catalog current without re-running the whole install.

#### "Could not create the vault at …"

Pre-flight creates the vault when the resolved vault path does not exist — the root plus `Projects/Ora`, `Sessions`, `Engrams`, `Resources`, and `Administration`. An existing vault is left exactly as it is and is never written into. Creation failure halts the install, and the installer removes the directories it had just made so a re-run starts clean; anything it could not remove is named in the log. Check the parent directory's permissions and free space, then re-run with `--resume`. If the log says a path was left in place, look at it before re-running.

Setting `ORA_VAULT` to an existing vault is the other way past this — the installer then reports that vault and leaves it alone.

#### "Write permission denied at /Users/.../ora"

The repo directory isn't writable by your user. Either you cloned as root (don't), or `chmod` is off:

```bash
ls -la ~/ora | head -3
chown -R "$USER:staff" ~/ora 2>/dev/null   # macOS
# or:
chown -R "$USER:$USER" ~/ora               # Linux
```

### Step 2 — Python dependencies

#### "pip install failed"

The step installs `requirements.txt` with the same interpreter that is running the installer, and prints the exact command it used so you can retry it by hand. Read the pip error first — a specific package failing is usually a network or wheel-build problem, not an Ora problem.

If pip refuses with `externally-managed-environment`, the installer has already handled it: Homebrew and most distro Pythons are PEP 668 managed, so it creates an isolated `.venv/` and installs there instead. `run-ora-server.sh` prefers that `.venv/` automatically. A failure to *create* the venv is fatal — check disk space and permissions in the checkout.

#### "Node.js and npm are required for the three shipped MCP servers"

This halts the install. The step installs the exact lock in `mcp-runtime/package-lock.json` and its matching Playwright Chromium, and neither works without `node` and `npm` on `PATH`. Install Node.js, confirm `node --version` and `npm --version` answer, then re-run with `--resume`.

### Step 3 — Document converters

#### "Converters were not fully provisioned"

**This never halts the install.** Ora renders Word (`.docx`) and PDF through Pandoc, with Typst as the PDF engine; a failure here costs you those two export formats and nothing else. The installer prints the cause and continues, and the step is not recorded as complete, so `--resume` retries it.

Retry it on its own without re-running the install:

```bash
python3 scripts/install.py converters
```

To see what it would do without changing anything:

```bash
python3 scripts/converters.py --dry-run
```

It uses a Pandoc or Typst the machine already has and otherwise downloads the publishers' pinned, checksum-verified releases into `data/converters/bin`. No package manager is required, and an archive whose checksum does not match never reaches the disk.

### Step 4 — Deployment profile selection

If you pass `--profile hybrid` or `--profile organization`, the installer exits with:

> Profile 'hybrid' is reserved for future Ora installs, not supported today.

Hybrid and Organization profiles are reserved in `DEPLOYMENT_PROFILES` but disabled pending network-discovery and concurrency validation. Use `--profile solo` for the desktop install. For server installs, use `scripts/install-server.sh` instead.

### Step 5 — Catalog refresh

#### "Catalog refresh did not complete"

The desktop installer fetches the public OpenRouter model list. This step does not require `OPENROUTER_API_KEY`.

**A refresh that does not complete is not, by itself, an install failure.** A model catalog ships in the repository, so the refresh makes it current rather than bringing it into existence. Whatever the cause — an outage, a rate limit, a network problem, a missing `scripts/refresh-catalog.py`, or a 120-second timeout — the installer prints the reason in full, falls back to the packaged catalog, says what is stale about it, and carries on. Everything downstream (the user pipeline, the four presets, the smoke test) bakes from that file exactly as it would from a fresh one.

Common causes worth reading the printed reason for:

- **OpenRouter catalog outage or rate limit.** Wait 60 seconds.
- **Network, DNS, firewall, or VPN issue.** Confirm `curl -I https://openrouter.ai/api/v1/models` works.
- **Python dependency or import error.** Read the stderr and install the missing package, or use the same Python binary the installer uses.

Once the network is back, get a current catalog without re-running the install:

```bash
cd ~/ora
python3 scripts/refresh-catalog.py
```

#### "There is no catalog to fall back on"

This one *does* halt the install, and it is the only way Step 5 halts. It means the packaged catalog is missing, unreadable, holds no models, or holds no entry with a model id — so there is nothing for the later steps to pick from. Check the file:

```bash
python3 -c "import json; c = json.load(open('config/model-catalog.json')); print('models:', len(c.get('models', [])))"
```

Restore `config/model-catalog.json` (a clean clone ships one) and re-run with `--resume`.

### Step 6 — Model registry sync

#### "Registry sync failed"

Registry sync is non-fatal. The installer logs a warning and proceeds with routing-config capability fallback. Re-run later with:

```bash
python3 scripts/sync_model_registry.py sync
```

Artificial Analysis is optional. The install path uses public Chatbot Arena/OpenRouter/LiteLLM data by default; an AA key can improve model-selector data after install but is not required.

### Step 7 — User pipeline and presets

This step does two things: it writes `config/configurations/user-pipeline.json` from the **Budget** preset — the configuration Ora actually serves requests from — and then bakes the four preset cards the Models pane shows (Free, Budget, Speed, Premium) through the runtime's own baker.

#### "Auto-populate failed"

The most common cause: the catalog is empty or malformed. Verify:

```bash
python3 -c "import json; c = json.load(open('config/model-catalog.json')); print('models:', len(c.get('models', [])))"
```

If `models: 0`, re-run Step 5 (catalog refresh) — something broke the catalog. If model count looks healthy (~300+), look at the auto-populate stderr for the actual error.

You can re-run auto-populate directly:

```bash
python3 scripts/auto-populate-configuration.py budget user-pipeline
```

The valid preset names are `premium`, `budget`, `speed`, and `free`. There is no "optimum" preset — older docs named one, and passing it fails with `Unknown preset: optimum`.

Inspect the output configuration file:

```bash
cat config/configurations/user-pipeline.json
```

#### "These presets do not exist after the bake" / "baked with no model in any slot"

Both halt the install on purpose. Ora promises a card for each of Free, Budget, Speed, and Premium in Settings → Models; a preset that is absent, or that exists with a model in none of its five slots, is a blank card the pipeline cannot run from, so the installer stops rather than report success over it. The same test is applied to `user-pipeline` itself.

The message names the catalog those picks came from and how many models it held. A catalog that never refreshed is the usual cause:

```bash
python3 scripts/refresh-catalog.py
python3 scripts/install.py --profile solo --resume
```

A preset that filled *some* of its slots is the genuinely partial case: it warns and the install finishes. Fill the empty slots in Settings → Models, or refresh the catalog and re-bake from the pane's Refresh button.

### Step 8 — Smoke test

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

### Step 9 — ChatGPT and External APIs orientation

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
