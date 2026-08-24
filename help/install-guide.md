# Ora Install Guide

This guide describes the current Ora install path. The public desktop install is a **source install** from this repository. Cloning the repo gives you the source tree; `scripts/install.py` prepares the working Solo profile.

There is no packaged app installer yet.

Companion docs:

- `install-recovery.md` — what to do when a script fails partway
- `install-manual.md` — manual fallback when the script itself is broken
- `install-testing.md` — clean-room test protocol
- `cloud-ora-install.md` — headless Linux/API-only server install

---

## Supported paths

| Path | Status | Command |
|---|---|---|
| macOS desktop | Primary path, especially Apple Silicon | `python3 scripts/install.py --profile solo` |
| Windows native | Intended, pending Parallels clean-install test | `py -3 scripts\install.py --profile solo` |
| Windows WSL | Practical fallback for Linux-style tooling | `python3 scripts/install.py --profile solo` inside Ubuntu/WSL |
| Linux desktop | Best effort/community | Source install may work; not the primary tested desktop path |
| Linux server | Supported API-only/headless | `./scripts/install-server.sh` |

Hybrid and Organization profiles are reserved for future network discovery and concurrency work. Today, use Solo for desktop installs.

---

## Before you start

Required:

- Git
- Python 3.11+
- Node.js and npm — Step 2 installs the three pinned MCP servers and their exact Playwright browser from the repository lock, and halts if `node` or `npm` is missing
- At least 5 GB free disk for the source install
- Internet access to GitHub, PyPI, the npm registry, and Playwright's browser CDN — Step 2 fetches the pinned MCP servers from the registry whenever the local npm cache is cold and then downloads their exact Chromium, and a failure at either one halts the install. OpenRouter's catalog endpoint and the public model-metadata sources are wanted but not required: if OpenRouter is unreachable, the install falls back to the model catalog packaged with the checkout and continues.

You do not need an existing vault, and you do not need Pandoc, Typst, Homebrew, WinGet, or Chocolatey. The installer creates the vault when there is none and downloads the two converters when the machine has none.

Optional but recommended:

- OpenRouter API key for broad cloud-model access
- Tavily API key for AI-oriented web search
- Artificial Analysis API key for improved model-selector data
- Direct provider keys if you already use Anthropic, OpenAI, Google, Mistral, DeepSeek, Qwen, or similar

Keys are not required for the core script to complete. Add them during Step 9's orientation or later in **Settings -> External APIs**. Keys are stored in the system keychain by the settings UI, not in plaintext config files.

OpenRouter is strongly recommended but optional. Free models are rate-limited and sometimes unavailable; paid models need credits/payment. Direct provider keys can skip OpenRouter's roughly 5.5% gateway markup for those providers' own models.

Claude Code is not required. Claude Code, Codex, Copilot, OpenCode, Cursor, Continue, Cline, Aider, or another coding agent can help diagnose a failed install, but the script runs directly in a terminal.

---

## macOS desktop install

```bash
git clone https://github.com/ora-commons/ora.git ~/ora
cd ~/ora
python3 scripts/install.py --profile solo
./scripts/ora-launchd.sh install
```

The launchd installer starts Ora immediately, verifies that the expected
checkout answers its health check, and installs a per-user `RunAtLoad` /
`KeepAlive` service for restart and login recovery. It also updates an existing
local `Ora.app` launcher to delegate to the same tracked startup path. Inspect it
with:

```bash
./scripts/ora-launchd.sh status
```

Use the port in the exact `Health:` URL printed by the installer and open that
origin (normally `http://localhost:5000`, but 5001–5010 may be selected if a
lower port is occupied). Logs are written to `logs/ora-server.stdout.log` and
`logs/ora-server.stderr.log` and are bounded by Ora's retention sweeper.

For a one-session, unsupervised start instead, use `./start.sh` before installing
the service. If an unsupervised Ora process is already running when you decide to
enable supervision, run `./stop.sh` first, then the install command above.

Service controls:

```bash
./start.sh                              # start the installed service if needed and open Ora
./stop.sh                               # stop it; keep the plist installed
./scripts/ora-launchd.sh restart
./scripts/ora-launchd.sh uninstall      # stop it and remove the plist
```

The label is user-global. Management commands refuse to stop or uninstall a
service installed from a different checkout; `--force-target-mismatch` exists
only for deliberate recovery after checking the installed plist target.

### Optional local models

The core install does not download local model weights. To add local models later:

```bash
python3 scripts/install.py models
```

The local-model flow detects RAM, recommends matching options, and asks before downloading. Expect tens of gigabytes per local model.

---

## Windows install

### Native PowerShell

```powershell
git clone https://github.com/ora-commons/ora.git $env:USERPROFILE\ora
cd $env:USERPROFILE\ora
py -3 scripts\install.py --profile solo
```

Use the Windows launcher when present. Until the Parallels test cycle completes, treat native Windows as intended but not fully verified.

### WSL

Install Ubuntu under WSL, then:

```bash
git clone https://github.com/ora-commons/ora.git ~/ora
cd ~/ora
python3 scripts/install.py --profile solo
./start.sh
```

WSL usually makes Python tooling simpler, but browser and file integration can feel less native than a Windows-native install.

---

## What `scripts/install.py` does

The desktop source installer runs nine steps:

1. **Pre-flight checks** — Python version, disk space, repo write permissions, the resolved storage roots, and whether OpenRouter is answering. An unreachable OpenRouter is reported, not fatal. This step also **creates the vault** when the resolved vault path does not exist yet — the root plus `Projects/Ora`, `Sessions`, `Engrams`, `Resources`, and `Administration`. An existing vault is reported and left exactly as it is; nothing is written into one.
2. **Python dependencies** — installs `requirements.txt`, plus the pinned MCP runtime and its exact Playwright browser. If the interpreter is externally managed (PEP 668), it falls back to an isolated `.venv/`.
3. **Document converters** — Word (`.docx`) and PDF export run through Pandoc, with Typst as the PDF engine. Neither ships in the repository, so the installer uses whatever the machine already has and otherwise downloads the publishers' own pinned, checksum-verified releases into `data/converters/bin`. No package manager is needed. This step never halts the install: only Word and PDF export depend on it, so a failure prints the cause and the retry command `python3 scripts/install.py converters` and the install carries on.
4. **Deployment profile selection** — Solo is supported; Hybrid and Organization return a clear "not yet" message.
5. **Catalog refresh** — fetches OpenRouter operational fields and writes `config/model-catalog.json`. A copy of that catalog ships in the repository, so the refresh makes it current rather than bringing it into existence. A refresh that cannot complete falls back to the packaged copy, says what is stale about it, and the install continues; it halts here only when no usable catalog exists at all.
6. **Model registry sync** — builds `config/model-registry.json` from OpenRouter, LiteLLM, Chatbot Arena, and optional probe data. Artificial Analysis is optional, not an install gate.
7. **User pipeline and presets** — writes `config/configurations/user-pipeline.json` from the **Budget** preset, then bakes all four presets the Models pane shows: Free, Budget, Speed, and Premium. A promised preset that is missing afterwards — or that exists with a model in none of its slots — halts the install and names which one and why. The user pipeline is read back against the same test, because that is the configuration Ora serves requests from.
8. **Smoke test** — generates a Free configuration. If an OpenRouter key is present, the script tries one tiny live chat round-trip. Without a key, it validates config and tells the user to add keys later. If a key is rejected, the install fails so the user can fix it.
9. **External APIs orientation** — explains the optional ChatGPT subscription route and the optional provider set, and offers official links.

The script is idempotent and resumable:

```bash
python3 scripts/install.py --dry-run
python3 scripts/install.py --resume
python3 scripts/install.py --reset
```

`--reset` clears installer state. It does not delete the vault, conversations, or downloaded models.

---

## Optional External APIs

Recommended starter package:

- **OpenRouter** — broad model access; free models are rate-limited/sometimes unavailable; paid models need credits/payment.
- **Tavily** — AI-oriented web search.
- **Artificial Analysis** — independent model intelligence; useful for the model selector.

Additional optional groups:

- **Search** — Exa and Brave Search API.
- **Direct model providers** — Anthropic, OpenAI, Google Gemini, Mistral, DeepSeek, Alibaba Qwen, and others. Direct keys can avoid OpenRouter's gateway markup and fall back to OpenRouter where configured.
- **Speech/image/video** — AssemblyAI, Deepgram, ElevenLabs, Stability AI, Replicate, Tensor.Art.

FRED is intentionally not part of the public install recommendation; it is for specialized economic-data workflows.

---

## Linux server install

For headless/API-only server use:

```bash
git clone https://github.com/ora-commons/ora.git ~/ora
cd ~/ora
./scripts/install-server.sh
```

This path creates a Linux Python environment, configures API-only routing, stores server env keys in `~/.config/ora-server.env`, and runs a server smoke test. It does not download local MLX models or expose the Flask UI publicly.

See `cloud-ora-install.md` for the full operator guide.

---

## Common friction points

| Friction | What to expect | Practical answer |
|---|---|---|
| Running a terminal script | The current installer is not a double-click package | Copy the commands exactly; use a coding agent only if you want help |
| OpenRouter signup | Optional but strongly recommended | Free models can work; paid use requires credits/payment |
| Free model reliability | Free models may be rate-limited or unavailable | Add OpenRouter credits or direct provider keys for daily use |
| API provider costs | Most providers vary by usage | Start with free tiers/credits where available; avoid fixed cost assumptions |
| Python version | macOS and Windows may point to older Python | Install Python 3.11+ and run the installer with that binary |
| macOS vault access under launchd | Health can pass while Documents access is denied | Inspect `logs/ora-server.stderr.log`; in System Settings → Privacy & Security, grant the selected Python/Ora process Files & Folders or Full Disk Access |
| Local model downloads | Large downloads and RAM-dependent fit | Skip at first; run `python3 scripts/install.py models` later |

---

## Related documents

- `install-recovery.md` — recovery from partial install failures
- `install-manual.md` — manual command fallback
- `install-testing.md` — formal clean-install test protocol
- `cloud-ora-install.md` — Linux server operator guide
