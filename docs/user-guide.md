# Using Ora — Operator Guide

*Task-indexed guide for installing, running, and operating an installed Ora system. It derives from [[Reference — Ora Technical Documentation]] and adds no new claims. Find your task, do the steps.*

**Platform labels.** Every command is labeled. `[macOS]` is the tested path (Apple Silicon). `[Linux server]` is the supported headless path. `[Windows-native]` and `[WSL]` are labeled where they differ; **`[Windows-native]` is intended but untested** — treat it as best-effort until a clean-room Windows install has been verified. If a command carries no label, it applies everywhere Ora runs.

**What things are called (nomenclature, 2026-07-11).** A working session with Ora is a **Dialogue**. You type into the **Inquiry** pane, read results in the **Findings** pane, and see diagrams in the **Exhibits** pane (the canvas beside the text). The small side-model chat panes in the upper right are the **Aside**, and the browse window for your Dialogues, engrams, and files — opened from the sidebar — is the **Library**. The running interface may still show older labels until its next update; where this guide names a control, the new names apply.

---

## Before you start

You need:

- Git
- Python 3.11 or newer
- At least 5 GB free disk for a source install
- Internet access (to GitHub and the model-catalog sources)

Optional but useful: an OpenRouter API key (broad cloud-model access), a Tavily key (web search), an Artificial Analysis key (better model-selector data). None are required to finish the install — you add them later.

There is no packaged one-click installer. The install is a source install: you clone the repository and run a script.

---

## Install Ora

### macOS desktop `[macOS]`

1. Clone the repository and enter it:
   ```bash
   git clone https://github.com/ora-commons/ora.git ~/ora
   cd ~/ora
   ```
2. Run the installer for the Solo profile:
   ```bash
   python3 scripts/install.py --profile solo
   ```
   The installer runs seven steps (preflight → profile → catalog refresh → registry sync → auto-populate → smoke test → API orientation). It is safe to re-run.
3. Start the server:
   ```bash
   ./start.sh
   ```
4. Open <http://localhost:5000> in your browser.

Solo is the only supported profile today. Hybrid and Organization are reserved — the installer refuses them with a clear message.

### Windows — native `[Windows-native — untested]`

1. Clone and enter the repo:
   ```powershell
   git clone https://github.com/ora-commons/ora.git $env:USERPROFILE\ora
   cd $env:USERPROFILE\ora
   ```
2. Run the installer with the Python launcher:
   ```powershell
   py -3 scripts\install.py --profile solo
   ```
3. Start the server with `start.bat`.

Two things to know before you rely on this. The native Windows path has not passed a clean-install test yet. And `start.bat` launches the server but does **not** set the runtime feature flags that `start.sh` sets — so a Windows launch runs a reduced pipeline. Until Windows is verified, prefer WSL.

### Windows — WSL `[WSL]`

Install Ubuntu under WSL, then run the desktop install steps inside it — but treat this as **untested**. The technical documentation labels the desktop installer and `start.sh` as untested on WSL and Linux; WSL behaves like a Linux desktop, which is a best-effort path, not a verified one. WSL makes the Python tooling behave like Linux; browser and file integration feel less native than a Windows-native install. If you need a supported non-Mac path, use the Linux server install below.

### Linux server (headless, API-only) `[Linux server]`

1. Clone and enter the repo:
   ```bash
   git clone https://github.com/ora-commons/ora.git ~/ora
   cd ~/ora
   ```
2. Run the server installer:
   ```bash
   ./scripts/install-server.sh
   ```

This path builds a Linux Python environment, routes every model call to cloud APIs (no local models), stores keys in `~/.config/ora-server.env`, and runs a smoke test. It does not expose the browser UI publicly.

### Add local models (optional) `[macOS]`

The core install does not download model weights. To add local models later:

```bash
python3 scripts/install.py models
```

The flow detects your RAM, recommends matching options, and asks before downloading. Expect tens of gigabytes per model. Local models run on Apple Silicon (MLX) — on any other platform, Ora routes model calls to the cloud instead.

---

## Start and stop the server

**Start** `[macOS]` (tested) · `[WSL]` `[Linux-desktop — untested/best-effort]`:
```bash
./start.sh
```
Then open <http://localhost:5000>. The server binds the first free port in 5000–5010. `start.sh` is verified on macOS only; on WSL and Linux desktop it is untested.

**Start** `[Windows-native]`: run `start.bat` (see the caveat above).

**Stop** `[macOS]` `[WSL]` `[Linux]`:
```bash
~/ora/stop.sh
```
Or close the terminal window the server started in.

**Stop** `[Windows-native]`: run `stop.bat`.

---

## Add your API keys

You need at least one working model endpoint before Ora can answer. The core install completes without keys, so this is usually your first step after installing.

1. Open the interface at <http://localhost:5000>.
2. Open **Settings → External APIs**.
3. Add a key. OpenRouter is the broadest single choice; direct provider keys (Anthropic, OpenAI, Google, and others) skip OpenRouter's gateway markup for those providers' own models.
4. Save. On macOS desktop, keys go into the system keychain, not a plaintext file.

You can also run the guided flow from the Inquiry pane (the text-entry box):
```
/framework api-key-setup
```

On the Linux server path, keys live in the plaintext file `~/.config/ora-server.env` (permissions `600`), not the keychain — that is by design for a headless host.

---

## Choose and switch models

Ora assigns models to named roles (the analyst, the reviewer, the fast helper, and so on) rather than tying you to one model. You set this in the interface.

**Pick a configuration.** Open **Settings → Models**. Four presets are always available — Free, Budget, Speed, Premium — plus any custom configurations you save. Picking one sets which models fill which roles.

**Edit a single role.** In the same Models pane, change which model fills a given slot; the interface writes the change into your active configuration's routing. (Edit routing through the Models pane, not by hand-editing config files.)

If you pick Free, expect the trade-off up front: free models are rate-limited and sometimes unavailable. Add OpenRouter credits or a direct provider key for daily use.

---

## Do work

1. Type your question or task in the Inquiry pane at <http://localhost:5000> and submit.
2. Wait. Ora is async by design — for serious work it runs the full pipeline server-side and does not stream a live progress bar. Submit, leave, come back. The interface reconciles what finished while you were gone.
3. Read the result in the Findings pane — the response side of the Dialogue. When Ora produces a diagram, it appears in the Exhibits pane, the canvas beside the text.

**Run a framework** (a whole procedure, not a single answer):
```
/framework <name> <your input>
```
Invoke a framework with no input to have Ora walk you through it one question at a time.

**Use tools without leaving the loop.** Do your tool-using work at <http://localhost:5000>, not at claude.ai or ChatGPT directly. The reason is mechanical: tools (web search, file access, knowledge search) run in the Python server between you and the model. A direct commercial chat interface has no Python in the loop, so the tools do not run.

---

## Where your things live

- **Vault** — `~/Documents/vault/`. Put files here that you want Ora to search: notes, documents, project files.
- **Dialogues** — `~/Documents/conversations/`. Session logs of your Dialogues, saved automatically.
- **System prompt** — `~/ora/boot/boot.md`. Ora reads this as its operating instructions.
- **Your values/voice** — `~/ora/mind.md`. Customizable from **Settings → Output Styles**, or via `/framework mindspec-interview`.
- **Model configuration** — `~/ora/config/routing-config.json` (routing and slots) and `~/ora/config/model-registry.json` (model inventory). Edit these through the Models pane, not by hand.

On Windows, read `~/...` as `%USERPROFILE%\...`.

---

## Update Ora

There is no packaged updater and no documented update procedure. Updating an existing install is open work in the system as documented — so this guide does not give you an update command, because the technical documentation does not yet authorize one. If you need the current state of the update story, check the repository and the technical documentation before changing a working install; do not treat any informal source-pull-and-reinstall sequence as a supported upgrade path.

---

## Recover from a failed install

The installer keeps state, so you can retry without starting over. The commands below use `python3` and POSIX paths `[macOS]` `[WSL]` `[Linux]`; on `[Windows-native — untested]` substitute `py -3` for `python3` and `%USERPROFILE%\ora\...` for `~/ora/...`.

1. See what happened: read `~/ora/install.log` `[macOS/WSL/Linux]` (`%USERPROFILE%\ora\install.log` on `[Windows-native]`).
2. Preview without changing anything:
   ```bash
   python3 scripts/install.py --dry-run
   ```
3. Continue a halted run:
   ```bash
   python3 scripts/install.py --resume
   ```
4. Start the install state over (this clears installer state only — it does **not** delete your vault, Dialogues, or downloaded models):
   ```bash
   python3 scripts/install.py --reset
   ```

For a script that is broken at the source level, `docs/install-manual.md` reproduces the install by hand. For per-step failure fixes, see `docs/install-recovery.md`.

---

## Troubleshoot

| What you see | What it means | What to do |
|---|---|---|
| Browser: "connection refused" | The server isn't running | Start it: `./start.sh` `[macOS]` (verified on macOS only; WSL/Linux-desktop untested) or `start.bat` `[Windows-native — untested, flag-incomplete]` |
| "No AI endpoints configured" | No working model key | Start the server (`./start.sh` `[macOS]`, `start.bat` `[Windows-native — untested]`), then add a key in **Settings → External APIs** |
| `<tool_call>` tags in the response | You're connected to a commercial AI directly, not to localhost | Use <http://localhost:5000>, not claude.ai / ChatGPT |
| Garbled output from a local model | The chat template needs a re-check | Switch models, or re-run the model setup |
| Output repeats itself | The Dialogue has grown too long | Start a new Dialogue |
| Free model unavailable or rate-limited | Expected on the Free configuration | Add OpenRouter credits or a direct provider key |

If a command in this guide fails on Windows or Linux, that is consistent with the platform status: macOS is the tested target. Check the platform label on the step before assuming a defect.

---

## Try this now

- Install on macOS, run `./start.sh`, open <http://localhost:5000>, add one OpenRouter key in **Settings → External APIs**, and submit a real question you have been putting off.
- Compare what comes back to what you would have written yourself in the same fifteen minutes.

---

## Cross-references

- (For why Ora runs two models instead of one, and why it makes AI reliable, see [[Reference — Ora Accessible Overview]].)
- (For how any of this works under the hood — the pipeline, the vault, the model routing, the platform matrix — see [[Reference — Ora Technical Documentation]].)
- (For the full install matrix and recovery detail, see `~/ora/docs/install-guide.md`, `install-recovery.md`, and `install-manual.md`.)

---

## Changelog

- **2026-07-11** — User-facing nomenclature pass: Dialogues (conversations), Inquiry pane (text input), Findings pane (text output), Exhibits pane (visual canvas), Aside (side-model chat panes), Library (browse modal). Terminology only — content remains pinned to ora commit `7a5e8f40`; this is not a re-pin and the parity audit was not re-run.
- **2026-07-04** — Initial version (Documentation-Code Parity closeout, pinned to `7a5e8f40`).
