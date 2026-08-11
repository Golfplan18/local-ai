# Using Ora — Operator Guide

*Task-indexed guide for installing, running, and operating an installed Ora system. It derives from [[Reference — Ora Technical Documentation]] and adds no new claims. Find your task, do the steps.*

**Documentation baseline.** Install and general-operation guidance retains its established platform pins. The Programming section describes the current explicit standalone implementation. The vault guide remains canonical; synchronize body-only to `docs/user-guide.md`.

**Platform labels.** Every command is labeled. `[macOS]` is the tested path (Apple Silicon). `[Linux server]` is the supported headless path. `[Windows-native]` and `[WSL]` are labeled where they differ; **`[Windows-native]` is intended but untested** — treat it as best-effort until a clean-room Windows install has been verified. If a command carries no label, it applies everywhere Ora runs.

**What things are called (nomenclature, 2026-07-11).** A working session with Ora is a **Dialogue**. You type into the **Inquiry** pane, read results in the **Findings** pane, and see diagrams in the **Exhibits** pane (the canvas beside the text). The small side-model chat panes in the upper right are the **Aside**, and the browse window for your Dialogues, engrams, and files — opened from the sidebar — is the **Library**. The interface uses these names as of the 2026-07-11 update; internal file and folder names — such as the `conversations` folder where Dialogues are stored — keep their original names.

---

## Start a Dialogue without duplicating prior work

1. Choose **New Dialogue** from the sidebar, the spine `+`, or the New Dialogue keyboard shortcut. Standard, Private, and Stealth creation all use the same review flow; the privacy choice remains visible in the heading.
2. Give the Dialogue a short title and an expanded description of what you want to explore or accomplish. The description must contain at least 20 characters and three terms so retrieval has enough subject matter to work with.
3. Choose **Find related material**. Ora searches both prior Dialogues and atomic notes. Nothing is created at this point.
4. Review the surfaced set. For each item you may:
   - **Add contributor** — include that source as read-only reference material in the new Dialogue without making it an ancestor.
   - **Continue** — return to an existing live Dialogue.
   - **Fork** — create a true child branch of an existing live Dialogue.
5. If you still want a new Dialogue, select any contributors, confirm that you reviewed the suggestions, and choose **Create Dialogue**. Editing the description invalidates the prior review and requires another search.

The confirmation asks Ora to issue a server-side creation contract bound to the exact title, description, selected contributors, privacy target, and active project you reviewed. Changing any of those inputs invalidates that confirmation. The new Dialogue is persisted only after the final Create action; concurrent delivery or a network retry returns the same Dialogue instead of creating another one.

Its description then appears in Inquiry as an **unsent draft**; review or edit it before submitting the first turn. Continue and Fork use the same rule, carrying the description as an unsent draft rather than sending it automatically.

A Dialogue may have one parent and any number of explicit contributors. Ora preserves contributor order, removes duplicates, and resolves each reference on every turn. A Dialogue contributor brings only its recursively cutoff-safe history. An atomic-note contributor brings indexed whole-content chunks. Missing, privacy-withheld, and budget-deferred references remain accounted for; they are not silently dropped.

Fork ancestry and contributors do different jobs. A new fork stores the direct parent and the parent's immutable local-message count at the fork point, but starts with `messages=[]`; its first new exchange is local turn 1. When you return, Ora recursively reconstructs only the permitted prefix at every ancestry edge. Later ancestor turns never leak into the child, and forking never changes the parent. The older `fork_point_chunk_id` field is compatibility metadata, not the current history boundary.

Every processing path receives server-authoritative history, including Phase A cleanup, Direct, G1–G4, and special consumers. Ora packs complete turn and note units into the selected endpoint's safe request size. The Dialogue maximum is 200,000 tokens, but the effective budget can be smaller after required payload, output, retry, image, provider, and safety allowances. Recent local context and the fork frontier come first, followed by eligible contributors, older history, and lower-priority global retrieval. Ora does not cut a turn in half or infer a durable “accepted decision” from model prose; the raw exchanges remain authoritative.

Privacy is cumulative: Standard may use Standard sources, Private may use Standard and Private, and Stealth may use all three. An explicitly selected archived Dialogue remains eligible as a read-only contributor when its entire required ancestry is permitted. Archived atomic notes and archived rows from global retrieval are excluded. Global retrieval also excludes the current Dialogue and all of its ancestors, contributors, and contributor ancestors so the same source cannot re-enter through a background path.

Use **Library** when you want the same search outside creation. A Library result can be opened, used to seed a new contributor review, continued when it is a live Dialogue, or forked when it is a live Dialogue. Archived Dialogues and atomic notes remain read-only, so Continue and Fork are unavailable for those rows.

Use the lifecycle controls literally:

- The ordinary sidebar shows the current project's non-Stealth Dialogues and only the active Stealth Dialogue. Closed Dialogues live in **Manage**.
- **Close** on Standard or Private sets a retained hidden state. Restore it from Manage; its transcript and descendants remain available.
- **Exit Stealth** is navigation only. Ora returns to the latest readable direct parent, even if that parent is Stealth, or opens a fresh Standard Dialogue when no readable parent exists. It does not close or delete anything.
- **Delete Forever** is the protected Stealth purge, even when descendants exist. Children detach and keep only their local turns. Ora strips a legacy copied-parent prefix only when an exact match proves what was copied; ambiguous content is preserved. Explicit exports and copies held by providers, Git, backups, or other external systems remain outside Ora's managed purge boundary.

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
3. Install the recommended per-user supervised service:
   ```bash
   ./scripts/ora-launchd.sh install
   ```
   The installer starts Ora immediately and configures macOS `launchd` to keep it available across logins. It also verifies that the responding server belongs to this checkout and updates an existing Ora.app launcher to delegate to the same service.
4. Open the exact `Health:` URL printed by the command. Ora normally uses port 5000 but may select the first available port through 5010. Check the installed service at any time with `./scripts/ora-launchd.sh status`.

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

**Recommended supervised setup** `[macOS]` (run once):
```bash
./scripts/ora-launchd.sh install
```
The command starts Ora immediately, installs a per-user `launchd` service with `RunAtLoad` and `KeepAlive`, verifies the expected checkout, and prints the exact `Health:` URL. Use that reported URL: the server binds the first free port in 5000–5010.

After supervision is installed, `./start.sh` starts the service if needed and opens Ora at its reported port. `./stop.sh` stops the service but keeps it installed. For explicit service control:

```bash
./scripts/ora-launchd.sh status
./scripts/ora-launchd.sh restart
./scripts/ora-launchd.sh uninstall
```

For a one-session, unsupervised macOS launch, run `./start.sh` before installing the service. If an unmanaged server is already running when you decide to install supervision, stop it with `./stop.sh` first, then run the install command above.

**Start** `[WSL]` `[Linux-desktop — untested/best-effort]`:
```bash
./start.sh
```
Open the exact URL that `start.sh` prints. The script is verified on macOS only; on WSL and Linux desktop it is untested.

**Start** `[Windows-native]`: run `start.bat` (see the caveat above).

**Stop** `[macOS]` `[WSL]` `[Linux]`:
```bash
~/ora/stop.sh
```
On macOS this delegates to the installed service when present; otherwise it stops only the Ora process belonging to this checkout. Use `./stop.sh` on every POSIX platform: `start.sh` backgrounds the unsupervised server, so closing the terminal is not a reliable stop.

**Stop** `[Windows-native]`: run `stop.bat`.

---

## Add your API keys

You need at least one working model endpoint before Ora can answer. The core install completes without keys, so this is usually your first step after installing.

1. Open the interface at the exact URL printed by the launchd install, or rerun `./start.sh` to print and open the current URL (port 5000–5010). The `status` action inspects service state; it does not report the health URL.
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

1. Open Ora at the exact reported URL (port 5000–5010), type your question or task in the Inquiry pane, and submit.
2. Wait. Ora is async by design — for serious work it runs the full pipeline server-side and does not stream a live progress bar. Submit, leave, come back. The interface reconciles what finished while you were gone.
3. Read the result in the Findings pane — the response side of the Dialogue. When Ora produces a diagram, it appears in the Exhibits pane, the canvas beside the text.

**Run a framework** (a whole procedure, not a single answer):
```
/framework <name> <your input>
```
Invoke a framework with no input to have Ora walk you through it one question at a time.

**Use tools without leaving the loop.** Do your tool-using work at the exact local Ora URL reported by the launcher, not at claude.ai or ChatGPT directly. The reason is mechanical: tools (web search, file access, knowledge search) run in the Python server between you and the model. A direct commercial chat interface has no Python in the loop, so the tools do not run.

---

## Programming

Use Programming when you want Ora to change and verify a real Git repository. Use ordinary Inquiry for answers, explanations, comparisons, drafts, and framework-guided thinking.

Programming begins only from the **Programming** toolbar action. Ora never classifies ordinary conversation into Programming and does not add Programming to the framework picker.

### Plan repository work

1. Open **Programming**.
2. Enter the repository's short name, such as `ora`, `vault`, or `mainstreetindependent`, or enter its Git worktree path.
3. Describe what should change in ordinary language and submit the Inquiry input.
4. Wait while Ora inspects repository instructions, implementation, tests, Git state, and visible automation.
5. Answer only material questions Ora cannot responsibly resolve from inspection. Ora asks no more than three questions per round and no more than two rounds.
6. Read the one proposed plan. It identifies the outcome, component scope, non-goals, protected work, milestones, checks, authorized effects, and Git finish line.
7. Choose **Approve and run** only if that complete boundary is right. Cancel leaves the repository unchanged.

Planning is read-only. Ora rechecks the Git baseline before creating a task branch. Safely separable unrelated work is protected and left uncommitted while Programming continues; Ora stops only when task work and user work cannot be separated safely.

### Follow execution and review

After approval, the Programming panel shows the current milestone, progress, accepted commit, and reviewer outcome. Ora's executor changes the real task repository and runs relevant commands. A separate fresh model call then inspects the raw diff, repository, and checks without receiving or trusting the executor's transcript.

Reviewer outcomes mean:

| Outcome | Meaning |
|---|---|
| **CONTINUE** | The current slice is sound and approved work remains. |
| **FIX** | A substantive defect can be corrected within the approved plan. |
| **DONE** | Final cumulative review proves the approved outcome complete. |
| **ASK USER** | Safe continuation requires changed scope or authority, a human-only decision, separation of user work, or a spend decision. |

Ora commits each accepted slice before continuing. Those commits are the rollback and resume points. There is no separate Run record, Process Library, trigger, lifecycle store, or background Programming daemon.

### Understand evidence and completion

The reviewer independently obtains evidence that matters to the plan. It may run local checks, inspect the implementation, fetch an authoritative outside source, or directly inspect an image or rendered PDF. An executor's statement that a test passed, a page says something, or an image looks correct is not evidence.

A required criterion remains unverified when its source or artifact cannot be inspected. Ora corrects it when possible inside scope and asks only when verification needs new authority, credentials, production effects, or human-only access.

Completion requires final **DONE**, clean accepted-slice commits, and the approved finish line:

- **local commits** — stop with the task branch ready locally;
- **push** — push that branch;
- **pull request** — push and open a pull request; or
- **merge** — perform the explicitly approved merge path.

If a newly discovered finish-line effect would deploy, publish, message, use credentials, or mutate another system without plan authority, Ora returns **ASK USER**.

### Leave, resume, cancel, or recover

Closing the Programming panel restores ordinary Inquiry; it does not create a persistent browser workflow. Before approval, cancel simply discards the proposal. During or after execution, the plan, task branch, commits, current diff, and checks are the recovery record.

To continue later, return to that repository and branch. Do not look for a Run Inspector, review queue, Trigger Manager, Process Library, activation control, or generic reopen action; standalone Programming does not create those objects.

### Troubleshoot Programming

| Symptom | Meaning | What to do |
|---|---|---|
| Repository required | No repository name or Git worktree path was supplied | Enter a short name or the worktree root |
| Planning stopped | Inspection or the configured planner failed | Read the visible error, correct repository/model access, and submit again |
| Baseline changed | Git state differs from the inspected plan baseline | Preserve or finish the unrelated work, then request a new plan |
| **FIX** repeats without progress | The same substantive defect survived three cycles without a changed task diff | Review Ora's consolidated **ASK USER** blocker |
| Required evidence is unavailable | The reviewer could not directly inspect a source or artifact | Grant only the exact authority/access needed or revise the plan |
| Programming needs a decision | Ora cannot continue responsibly inside the approved boundary | Decide the specific scope, authority, access, or spend question shown |
| Work is complete locally | The approved finish line was local commits | Inspect or continue from the task branch; push only when intended |


## Diagnose a problematic result with Trace Walk

**Current-feature note (2026-07-16, post-pin).** Trace Walk landed in Ora PR #269 (merge commit `241a31c0`, implementation commit `99638ef3`). This section is a scoped description of that shipped feature; it does not re-pin the rest of this guide from its installed-system baseline at `7a5e8f40`.

Tracing is automatic and on by default. There is no `/trace` slash command and no setup command to run. Each eligible turn records what actually happened under `~/ora/data/pipeline-traces/<dialogue-id>/<turn>/`. Setting `ORA_PIPELINE_TRACE=off` (also `false`, `0`, `no`, or `disabled`) disables new traces globally. A Stealth Dialogue never creates a trace.

### Open and read a trace

1. Go to the problematic turn in its Dialogue.
2. Hover over the lower-right edge of the Findings pane. The output toolbar appears.
3. Click **Trace** (tooltip: **How this was made**). The button is enabled only when that turn carries a trace reference.
4. Read the overview badges first: trace kind, terminal status, effective Gear, and retention state. If a Gear 4 attempt fell back to Gear 3, the Gear badge reports the Gear that actually completed.
5. Check the stage categories, then choose a recorded step in the left-hand map. Trace Walk shows a redacted structural projection: stage identity, endpoint/slot and health fields when recorded, retry or contingency markers, verdicts, routing/persistence state, and lengths/hashes instead of raw prompt or output text.

The manifest categories have literal meanings:

| Category | Meaning |
|---|---|
| Actual | A real `step*.json` artifact exists on disk. |
| Derived | A computed artifact such as step health or cost summary exists; it is not itself a production stage. |
| Missing expected | A normally required stage is absent from a completed turn. This deserves investigation. |
| Skipped | An optional stage did not run, or an exceptional exit prevented a required stage from being reached. |
| Replaced | A fallback or short path displaced normally expected work; the manifest retains the original expectation rather than rewriting history. |
| Contingency | A recorded retry, fallback, no-endpoint, or other exceptional production path actually ran. |
| Unexpected | A real stage ran but belongs to none of the expected, optional, replacement, or contingency sets. |

Use the evidence this way:

| Symptom | Inspect first |
|---|---|
| Wrong model, mode, or routing | `step1-pre-routing`, model-call configuration records, endpoint/slot fields, and the effective Gear badge |
| Sources or retrieved context seem absent | Step 2 context assembly, supplemental-RAG, and web-consultation stages; distinguish **skipped** from **missing expected** |
| Answer looks degraded or fell back | Step health plus **contingency**, **replaced**, and **skipped** stages |
| Findings differ from what the pipeline produced | `step-terminal-output`; its local artifact records the exact value only after output routing/delivery, including persistence state |
| A factual claim or verification seems unsupported | Claim-evidence assembly, verifier, quality-gate, and retry/fallback stages |

### Preserve, investigate, or export

- Click **Pin trace** before an important investigation. Unpinned traces are normally swept after 30 days; pinned traces are exempt. The same control becomes **Unpin trace**.
- Select the most suspicious step and click **Investigate**. Add the symptom when prompted. Ora creates a separate P-Debug diagnostic turn in the same Dialogue; it does not rerun, replay, approve, or modify the original trace.
- Click **Export HTML** for a portable report. Browser views and exports recursively redact raw strings and bytes to structural metadata, lengths, and SHA-256 hashes. A Private trace is labeled private and its raw content is omitted from the export. Investigation stays in the originating Dialogue and keeps its privacy tag. Stealth produces no trace at all.

The raw local trace files are more sensitive than the Trace Walk view: they can contain exact prompts, model responses, and terminal values. Treat `~/ora/data/pipeline-traces/` as private local diagnostic data and do not share a raw turn directory without reviewing it.

### Reproduce a problem from the command line `[macOS]`

Use the exact URL reported by the Ora launcher; do not assume port 5000 when the launcher selected another port.

```bash
cd ~/ora
export ORA_URL="http://127.0.0.1:5000"  # replace with the reported URL

./scripts/ora-test --list-configs
./scripts/ora-test --list-modes
./scripts/ora-test --server "$ORA_URL" \
  --id trace-repro-001 \
  "Describe the problem you need to reproduce"
```

Add `--config NAME` to use a saved configuration without changing the server's active configuration, or `--mode MODE` to pin a mode. The command prints the Dialogue id, pipeline stages, final trace directory, and a cost summary when available. `--no-wait` submits in the background; it is POSIX-only and gives you a directory pattern rather than a completed trace immediately.

A trace reference is the final two path components, `<dialogue-id>/<turn>`. From `~/ora`, inspect or preserve it without opening the browser:

```bash
python3 -m orchestrator.pipeline_trace status '<dialogue-id>/<turn>'
python3 -m orchestrator.pipeline_trace pin '<dialogue-id>/<turn>'
python3 -m orchestrator.pipeline_trace unpin '<dialogue-id>/<turn>'
```

For automation or remote diagnostics, the server exposes safe read-side projections. Replace the placeholders with the Dialogue id and turn timestamp from the trace reference:

```bash
curl -s "$ORA_URL/api/trace/list/<dialogue-id>"
curl -s "$ORA_URL/api/trace/manifest/<dialogue-id>/<turn>"
curl -s "$ORA_URL/api/trace/step/<dialogue-id>/<turn>/<step-name>"
curl -o ora-trace.html "$ORA_URL/api/trace/export/<dialogue-id>/<turn>"
```

If **Trace** is disabled or absent, the turn has no trace reference. Common causes are a turn created before Trace Walk was installed, a globally disabled trace layer, a Stealth Dialogue, an incomplete/current turn, or a fail-open trace-write error. Tracing is observational: a trace-write failure must not change the answer or crash the pipeline, so server logs are the next place to check.

---

## Where your things live

- **Vault** — `~/Documents/vault/`. Put files here that you want Ora to search: notes, documents, project files.
- **Dialogues** — `~/Documents/conversations/`. Raw session logs are saved automatically here. Lifecycle envelopes and retrieval caches are Ora-managed companions; use the interface rather than editing any of them by hand.
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
| Browser: "connection refused" | The server isn't running | On macOS install supervision with `./scripts/ora-launchd.sh install`, or run `./start.sh`; use the exact URL either command reports. On Windows-native, run `start.bat` `[untested, flag-incomplete]` |
| "No AI endpoints configured" | No working model key | Start the server, open its reported local URL, then add a key in **Settings → External APIs** |
| `<tool_call>` tags in the response | You're connected to a commercial AI directly, not to Ora's local server | Use the exact local URL Ora reports, not claude.ai / ChatGPT |
| Health passes, but Ora cannot read `~/Documents` | macOS privacy controls denied the supervised process access | Inspect `logs/ora-server.stderr.log`. In **System Settings → Privacy & Security**, grant the selected Python/Ora process **Files & Folders** access or **Full Disk Access**, then restart the service |
| Garbled output from a local model | The chat template needs a re-check | Switch models, or re-run the model setup |
| Output repeats itself | Repetition alone does not prove the Dialogue is too long; it may be a model, prompt, or coverage problem | Retry once, then inspect the Trace and numeric context coverage. Fork or start a new Dialogue only when you actually want a new branch or scope |
| Free model unavailable or rate-limited | Expected on the Free configuration | Add OpenRouter credits or a direct provider key |

If a command in this guide fails on Windows or Linux, that is consistent with the platform status: macOS is the tested target. Check the platform label on the step before assuming a defect.

On macOS, supervised stdout and stderr are written to `logs/ora-server.stdout.log` and `logs/ora-server.stderr.log`. An unsupervised `start.sh` launch uses the root `server.log`. Both log families are retention-bounded and rotated by Ora's retention sweeper.

---

## Try this now

- Install on macOS, run `./scripts/ora-launchd.sh install`, open the exact `Health:` URL it prints, add one OpenRouter key in **Settings → External APIs**, and submit a real question you have been putting off.
- Compare what comes back to what you would have written yourself in the same fifteen minutes.

---

## Cross-references

- (For why Ora runs two models instead of one, and why it makes AI reliable, see [[Reference — Ora Accessible Overview]].)
- (For how any of this works under the hood — the pipeline, the vault, the model routing, the platform matrix — see [[Reference — Ora Technical Documentation]].)
- (For the full install matrix and recovery detail, see `~/ora/docs/install-guide.md`, `install-recovery.md`, and `install-manual.md`.)
