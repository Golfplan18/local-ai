# Cloud Ora Server Install

Headless API-only Ora install for cloud / server use. Designed for the MSI publication cadence on a small Linux box. Tested on Hetzner CX33 (Ubuntu 24.04, 4 vCPUs, 8 GB RAM).

This is the **minimal viable** server install — it gets MSI's publication cycle running on the server without the full Chunk 7 Organization profile (which is blocked on the concurrency architecture spec). When the worker pool / multi-process design lands, this install can be upgraded in place by re-running the orchestrator-side installer.

## What this install gives you

- Ora source tree in `~/ora/`, cloned from `ora-commons/ora`.
- Python venv at `~/ora/.venv/` with the Linux subset of Ora's deps (no `mlx-lm`).
- Ollama with `nomic-embed-text` pulled, for ChromaDB embeddings.
- `routing-config.json` with API-only slot assignments — `qwen/qwen3.6-35b-a3b` for utility slots, `qwen/qwen3.6-plus` for analysis slots, all routed through OpenRouter so the server only needs one API key. MSI's article generator picks its own model via the `MSI_AUTHOR_MODEL` env var (Sonnet forward, Haiku backfill) — independent of these slot picks.
- `OPENROUTER_API_KEY` saved to `~/.config/ora-server.env` with `600` perms. `ANTHROPIC_API_KEY` is optional (only needed if MSI's worker is configured to call Anthropic direct rather than via OpenRouter).
- A smoke test that confirms the install is functional.

## What it does NOT give you

- **Local model files** — no GPU on a server, no MLX, no HuggingFace downloads.
- **Worker pool / multi-process concurrency** — single-process. Fine for MSI's once-a-day cadence; insufficient for high-concurrency request serving.
- **Public Flask exposure** — the chat UI is intentionally not bound on the server.
- **systemd / cron configuration** — the MSI publication cycle is configured separately. Add a cron entry or systemd timer per your operational plan (see `Working — Project — Cloud Ora Implementation Plan.md` phase (d)).
- **Vault sync setup** — that's a Mac-side `launchd` agent configured by the Mac, not the server. See the cloud-Ora plan's phase (c-finalize).

## Prerequisites

- Linux host with `sudo` (the script apt-installs `python3-venv`, `pip`, `git`, `curl` if any are missing).
- Outbound HTTPS to `api.openrouter.ai`, `api.anthropic.com`, `ollama.com`, and `github.com`.
- An OpenRouter API key (`sk-or-...`); optionally an Anthropic API key.
- A clean directory at `~/ora/` (the install clones into the cwd if you run from the parent dir — see below).

### Optional: Artificial Analysis API key

This server installer uses **hard-coded slot picks** (set in `scripts/install_server_config.py`'s `SERVER_SLOT_ASSIGNMENTS`), so it does **not** require an Artificial Analysis API key — slot assignments are baked in rather than auto-populated.

The Mac-side `scripts/install.py` does run the auto-populate engine and **does** need an `AA_API_KEY` to get sensible picks. Without it, the auto-populate algorithm falls through to pure cost-sort and picks the cheapest model per slot regardless of capability. If you ever switch this server install to auto-populate (e.g. when the full Chunk 7 Organization profile lands), you'll need to sign up at <https://artificialanalysis.ai/> and set `AA_API_KEY` in `~/.config/ora-server.env`.

## Install

```bash
# On the server, in the directory where ora should live (typically ~/):
git clone https://github.com/ora-commons/ora.git
cd ora
./scripts/install-server.sh
```

The script is **idempotent** — re-running it skips work that's already done (existing venv, existing API keys, etc.). To change API keys, delete `~/.config/ora-server.env` and re-run.

### Flags

- `--skip-ollama` — don't install ollama or pull the embedding model. ChromaDB RAG won't work without it; only use this if you're standing up a non-RAG install.
- `--skip-key` — don't prompt for API keys (assumes they're already in env or `~/.config/ora-server.env`).
- `--dry-run` — show what would happen, don't change anything.
- `--help` — print the full header.

## Verifying the install

After install completes, the smoke test runs automatically. To re-run it later:

```bash
cd ~/ora
source .venv/bin/activate
set -a; source ~/.config/ora-server.env; set +a
python3 scripts/install_server_smoke.py
```

It checks five things:
1. `routing-config.json` loads via `boot.load_routing_config()`.
2. Every slot in `slot_assignments` resolves to an actual endpoint.
3. No slot points at a `local-mlx-*` model.
4. `OPENROUTER_API_KEY` is reachable in the environment.
5. `chromadb` is importable.

Exits non-zero on any failure.

## Configuration files

| File | Purpose |
|---|---|
| `~/ora/config/routing-config.json` | Capability + endpoint config. Rewritten by `scripts/install_server_config.py` during install to use API-only slots. |
| `~/ora/config/routing-config.json.pre-server-install` | Backup of the upstream Mac-flavor file, created once during install. |
| `~/.config/ora-server.env` | API keys (mode `600`). Sourced by anything that needs to call models. |
| `~/ora/.venv/` | Python virtualenv. |

If your cost preferences differ from the defaults (`qwen/qwen3.6-35b-a3b` utility, `qwen/qwen3.6-plus` analysis — both via OpenRouter), edit `scripts/install_server_config.py`'s `SERVER_SLOT_ASSIGNMENTS` block and re-run it directly:

```bash
cd ~/ora
source .venv/bin/activate
python3 scripts/install_server_config.py
```

## Architectural notes

**Why this is "minimal" and not the full Organization profile.** The full Chunk 7 Organization profile is blocked on the concurrency architecture thread (worker pool design). This installer sidesteps that question by being single-process — fine for MSI's once-a-day cadence, insufficient for serving high-concurrency requests. When the concurrency design lands, the full installer (`scripts/install.py --profile organization`) will supersede this one.

**Why slot_assignments not the v2 slots block.** Router today picks slot endpoints from the v2 `slots` block + bucket walks. The `slot_assignments` field is the legacy v1 representation kept as a Router-failure fallback (per install Chunk 12). This installer writes both forms compatibly — the v1 fallback now references API endpoints rather than local-MLX models — so even if Router fails to init, the server doesn't try to dispatch to a model that doesn't exist on the host.

**Why a separate install script and not a `--profile server` on `install.py`.** The main `install.py` carries the Solo profile only; Hybrid / Organization profiles are scaffolded but explicitly gated on the concurrency thread. Rather than enable a half-finished profile, this server install lives in its own bash script so the Solo profile stays clean for Mac use. When concurrency lands, this script's logic gets folded into `install.py --profile organization`.

## Operational checklist after install

1. **Vault sync target.** The Mac-side `launchd` agent rsyncs vault content to `/ora/vault-sync/` on the server. Confirm that directory exists or create it:
   ```bash
   mkdir -p ~/ora/vault-sync
   ```
2. **MSI publication cycle.** The server doesn't auto-run MSI. Configure a cron entry or systemd timer that invokes the MSI publisher (the exact command depends on the MSI Project Plugin Hygiene Cleanup landing — see the cloud-Ora plan).
3. **ChromaDB index.** First time MSI runs, it'll build the ChromaDB index from `/ora/vault-sync/`. Allow ~10-30 minutes for the initial pass on ~116k files; subsequent runs are incremental.
4. **Tailscale.** SSH access is Tailscale-gated. Confirm `tailscale status` shows the host joined. Public port 22 should already be closed (per phase (a) of the cloud-Ora plan).

## Related documents

- `Working — Project — Cloud Ora Implementation Plan.md` — the parent plan this install slots into.
- `Working — Project — Ora Install Script Overhaul.md` — the install-script overhaul this is a subset of. The "Chunk 7 Organization profile" line item there is the eventual supersession path.
- `scripts/install.py` — the Mac-side / Solo-profile installer. Lives in the same repo but takes a different code path (interactive prompts, hardware tier detection, HuggingFace model downloads).
