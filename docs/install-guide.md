# Ora Install Guide

Step-by-step walkthrough for installing Ora. There are two installers depending on what you're running:

- **`scripts/install.py`** — Mac desktop install with local MLX models. Interactive, with hardware-tier detection and an optional HuggingFace download flow. This is the Solo deployment profile.
- **`scripts/install-server.sh`** — Linux server install, API-only. Designed for cloud / headless use (Hetzner CX33, similar). No local models, no chat UI exposure.

Pick the one that matches your hardware and read the corresponding section. If you're not sure, you almost certainly want the Mac installer.

The companion docs:

- **`install-recovery.md`** — what to do when something fails partway
- **`install-manual.md`** — eight-command fallback for when the script itself is broken
- **`install-testing.md`** — formal protocol for snapshot/restore test cycles

---

## Before you start (both installers)

You'll need accounts at two services. The signups are free and take a couple of minutes each. Do them now and have the API keys ready — the installer will prompt for both.

### 1. OpenRouter (required)

OpenRouter is a unified API for cloud-based AI models. Ora uses it as the primary path to OpenAI, Anthropic, Google, Mistral, Qwen, and dozens of others.

- Sign up at <https://openrouter.ai>
- **You do NOT need a credit card to start.** OpenRouter has a free tier with several models that work without payment. Add payment later if you want to use paid models (Sonnet, GPT-4o, etc.).
- Grab your API key from the dashboard — it starts with `sk-or-`.
- Export it in your shell before running the installer:
  ```bash
  export OPENROUTER_API_KEY=sk-or-xxxxxxxxxxxxxxxxxxxx
  ```
  Add it to `~/.zshrc` or `~/.bashrc` if you want it to persist.

### 2. Artificial Analysis (strongly recommended)

Artificial Analysis publishes the intelligence-index rankings Ora's auto-populate engine uses to rank models within their size bucket. Without it, every model scores the same on capability and the algorithm falls through to pure cost-sort — you'll get the cheapest model per slot regardless of how capable it actually is.

- Sign up at <https://artificialanalysis.ai/>
- Free tier is sufficient.
- Grab your API key.
- Export it:
  ```bash
  export AA_API_KEY=aa_xxxxxxxxxxxxxxxxxxxx
  ```

The installer will warn loudly and pause for confirmation if `AA_API_KEY` isn't set. You CAN proceed without it, but expect to add it later and re-run `scripts/refresh-catalog.py` + `scripts/auto-populate-configuration.py` to get sensible slot picks.

### 3. Anthropic API (optional)

Only needed if you want to call Anthropic models directly rather than via OpenRouter. The Mac install doesn't prompt for this; the server install asks for it as optional. MSI's article generator uses it via the `MSI_AUTHOR_MODEL` env var when configured to do so.

---

## Mac install (`scripts/install.py`)

### Prerequisites

- macOS 12+ on Apple Silicon (M1 / M2 / M3 / M4 / M5). The local MLX runtime is Apple-Silicon-only.
- Python 3.11+ (macOS ships with 3.9; install 3.11+ via Homebrew: `brew install python@3.12`).
- At least 5 GB free disk space (plus ~40-80 GB per local model if you opt into HuggingFace downloads).
- Outbound HTTPS to `api.openrouter.ai`, `artificialanalysis.ai`, `huggingface.co`, `github.com`.

### Run the installer

```bash
git clone https://github.com/ora-commons/ora.git ~/ora
cd ~/ora
python3 scripts/install.py
```

The installer walks 6 steps. Each step is idempotent — re-running the installer skips work that's already done.

#### Step 1/6 — Preflight checks

Verifies Python version, disk space, OpenRouter API reachability, and write permissions in the repo directory. If anything fails, the installer prints the missing item and exits non-zero. Fix the issue and re-run.

#### Step 2/6 — Deployment profile selection

Three profiles: **Solo** (local + cloud, single-user, MLX-safe), **Hybrid** (local + API failover, small worker pool), **Organization** (pure API, scales to 20+ concurrent processes).

For a desktop install, pick Solo. Hybrid and Organization are scaffolded but currently disabled — they're being landed in a separate work stream.

Non-interactive: pass `--profile solo` to skip the prompt.

#### Step 3/6 — OpenRouter API key setup

Checks for `OPENROUTER_API_KEY` in env. If present, the step passes. If absent, the installer logs instructions and exits — you set the env var, then re-run.

The installer also looks at `config/routing-config.json` for an existing OpenRouter endpoint — if one's configured from a prior install, the step passes without requiring the env var.

#### Step 4/6 — Catalog refresh

Fetches the OpenRouter model list (~357 models) and enriches with Artificial Analysis rankings (~229 enriched).

If `AA_API_KEY` is not set, the installer prints a multi-line warning explaining the consequence (auto-populate falls through to cost-only sort) and **pauses for Enter to continue**. You can proceed without AA — but expect to re-run the catalog refresh + auto-populate once you have the key.

Writes `config/model-catalog.json`. Also writes `data/model-catalog-changes.jsonl` recording new/retired models and free→paid transitions.

Takes 5-15 seconds depending on network.

#### Step 5/6 — Auto-populate user-pipeline configuration

Runs `scripts/auto-populate-configuration.py optimum user-pipeline`. Uses the Pareto + percentage-floor + cost-sort algorithm to pick 3 models per workhorse slot and 2 per utility slot.

Result lands in `config/configurations/user-pipeline.json`. You can re-run this anytime to refresh picks against a fresh catalog.

Takes a few seconds.

#### Step 6/6 — Smoke test

Auto-populates a Free configuration, sends one test prompt through it, and verifies the response. Confirms end-to-end routing works.

If this passes, the install is complete and the log ends with:
```
INSTALL_COMPLETE: 0 warnings, 0 errors
```

### After install

Start the chat server:
```bash
cd ~/ora
./start.sh
```

Open <http://localhost:5000> in a browser. The V3 chat interface should render.

### Hardware tier and local models (optional)

The Solo profile defaults to API-only. If you want local MLX models:

```bash
python3 scripts/install.py models
```

This re-enters the local-model flow. Detects your RAM tier (6-11, 12-23, 24-47, 48-95, 96+ GB) and presents matched options:

| RAM tier | Recommendation |
|---|---|
| 6-11 GB | Single small utility model (3-7B, 4-bit quantization) |
| 12-23 GB | Local Workhorse single 30B model OR Local Mid+Small pair |
| 24-47 GB | Local Workhorse + Local Mid (~40 GB combined) |
| 48-95 GB | Full Local achievable with 3-bit quantization (degradation warning) |
| 96+ GB | Full Local + Adversarial Diversity (two 70B-class models in different families) |

Downloads happen via the HuggingFace Hub. Expect 20-80 GB per model. The script asks for confirmation before downloading.

---

## Linux server install (`scripts/install-server.sh`)

For headless cloud / server use. See `cloud-ora-install.md` for the full operator guide. The TL;DR:

```bash
# On the server, in the directory where ora should live:
git clone https://github.com/ora-commons/ora.git
cd ora
./scripts/install-server.sh
```

The script apt-installs Python deps, creates a venv, installs ollama for ChromaDB embeddings, rewrites `routing-config.json` to OpenRouter-only slot picks, prompts for `OPENROUTER_API_KEY` (and optionally Anthropic), and runs a smoke test.

Differences from the Mac install:
- **API-only.** No MLX, no HuggingFace downloads.
- **One-key setup.** All slot picks are routed through OpenRouter so the server only needs `OPENROUTER_API_KEY`.
- **Single-process.** No worker pool until the Organization profile lands.
- **No public Flask exposure.** The chat UI isn't bound on the server; access is via Tailscale or local-only.
- **No AA_API_KEY needed today.** The server uses hard-coded slot picks rather than the auto-populate engine.

---

## Friction points (honest list)

Here's where users typically hit snags:

| Friction | What to expect | Fix |
|---|---|---|
| **OpenRouter signup** | 2-5 minutes if you don't already have an account | Sign up at <https://openrouter.ai>. Free models work without a credit card. |
| **Artificial Analysis signup** | 2-5 minutes. Easy to skip and regret later. | Sign up at <https://artificialanalysis.ai/>. The installer warns loudly if you skip; better to set it up now. |
| **OS approval popups (Mac)** | 1-2 popups during install: ollama install, possibly Xcode CLI tools | Click Allow. They're for legitimate tools (ollama, Python build deps). |
| **HuggingFace download size** | 20-80 GB per local model. Cancel anytime; not part of the critical install path. | If on a slow connection, skip the local models. API-only install is fully functional. |
| **Python version** | macOS ships with 3.9, which lacks newer type-hint syntax | `brew install python@3.12` and ensure `python3 --version` shows 3.11+ before running the installer. |
| **AA_API_KEY warning** | The installer pauses and waits for Enter | Read the warning; understand that skipping means cheapest-model picks. Then either set the key and re-run, or press Enter to proceed knowingly. |
| **Tailscale (server install)** | Required for SSH access if you've closed port 22 | Set up Tailscale on both the local machine and the server before SSHing in. |

---

## Next steps after install

- Read `~/ora/CLAUDE.md` for the repository overview.
- Read the working doc `~/Documents/vault/Working — Project — Ora Install Script Overhaul.md` for the state of the install-script project (which chunks are done, which are pending).
- If the install failed at any step, see `install-recovery.md`.
- If you want to fall back to manual commands (because the script itself is broken), see `install-manual.md`.
- If you're setting up a test environment for snapshot/restore cycles, see `install-testing.md`.

## Related documents

- `cloud-ora-install.md` — full operator guide for the Linux server installer
- `install-recovery.md` — recovery from partial install failures
- `install-manual.md` — manual command fallback
- `install-testing.md` — formal test protocol
