# Using Ora — Operator Guide

*Task-indexed guide for installing, running, and operating an installed Ora system. It derives from [[Reference — Ora Technical Documentation]] and adds no new claims. Find your task, do the steps.*

**Documentation baselines.** Install and general-operation guidance remains pinned to `7a5e8f40`, with the verified supervision and currency updates through runtime commit `86a888bc` reconciled into this vault canonical once on 2026-07-19. The governed-process section is pinned to the accepted G1.1 Part 2 runtime at `6740f2fcc6663b5d5e1f57db9ce57de3578ac42c` and the Phase 3.1 as-built record. This one-time promotion of verified runtime guide behavior does not reverse the standing direction of truth: future guide edits begin here and synchronize body-only to `docs/user-guide.md`.

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
   - **Fork** — create a child of an existing live Dialogue, preserving its parent lineage.
5. If you still want a new Dialogue, select any contributors, confirm that you reviewed the suggestions, and choose **Create Dialogue**. Editing the description invalidates the prior review and requires another search.

The confirmation asks Ora to issue a server-side creation contract bound to the exact title, description, selected contributors, privacy target, and active project you reviewed. Changing any of those inputs invalidates that confirmation. The new Dialogue is persisted only after the final Create action; concurrent delivery or a network retry returns the same Dialogue instead of creating another one.

Its description then appears in Inquiry as an **unsent draft**; review or edit it before submitting the first turn. Continue and Fork use the same rule, carrying the description as an unsent draft rather than sending it automatically.

A Dialogue may have one parent and many contributors. A parent represents fork ancestry and carries conversational history. Contributors are explicit Dialogue or atomic-note references that Ora resolves into bounded, read-only reference context on each turn. Private material cannot contribute into a Standard Dialogue, and Stealth material cannot cross out of Stealth.

Use **Library** when you want the same search outside creation. A Library result can be opened, used to seed a new contributor review, continued when it is a live Dialogue, or forked when it is a live Dialogue. Archived Dialogues and atomic notes remain read-only, so Continue and Fork are unavailable for those rows.

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

## Governed processes

Use a governed Process when you want Ora to carry durable work across planning, execution, evidence, decisions, correction, and later reuse. Use ordinary Inquiry when you only want an answer, explanation, comparison, or draft.

The distinction is consequential. A governed Process creates a Process Run with an exact definition, project, plan, authority, artifact scope, evidence requirements, and persistent history. It may construct or invoke a reusable capability. Ordinary generation does none of those things merely because the answer mentions automation or Programming.

### Start the right kind of work

You can start governed work from five places:

1. Describe the outcome directly in the **Inquiry** pane. Ora classifies whether you are asking for ordinary generation, an existing capability, construction or modification, or activation.
2. Use the **Programming** action. If you previously chose the broader **Build** label after Ora proved non-programming construction, the same action may be labeled Build; the label does not change capability identity or authority.
3. Choose an exact Process Definition from the shared framework/process picker.
4. Open the **Process Library** and select an exact registered definition.
5. Name an available capability as the operator in ordinary language, such as “Have Programming verify this repository.”

Describe the result, not the technical implementation. “Set up a repeatable monthly cash-flow review” is enough to begin construction. “Summarize the Programming documentation” and “Use Programming as an example” remain ordinary generation because Programming is the subject, not the operator.

When Ora infers construction, it must show the construction form before any Process Run or effect begins. The form asks **What should happen?** and requires a visible project choice. If that form does not appear when you intended reusable or recurring work, cancel and use the Programming/Build action or restate the effect you want established. Do not assume an ordinary answer created a capability.

### Confirm the project and artifact scope

Every construction begins with project confirmation. Choose the project whose purpose, files, Dialogues, and permissions should contain the work. **Commons** is the universal view, but selecting it is still a real scope choice; it is not permission to affect every project.

The project chooser binds the construction request. The later plan binds the exact artifacts. Before approval, check the Principal view’s scope and the Technical view’s target paths, repository identity, inputs, outputs, and requested actions.

- If the wrong project is selected, cancel before continuing and restart under the correct project.
- If the project is right but an artifact, repository, output, or permission is wrong, choose **Change scope or permissions** at plan review.
- If the plan names an ambiguous or unexpected target, do not approve it. Ask for a corrected plan.
- A project choice does not grant mutation, publication, messaging, activation, or other reserved authority. Those remain separate.

### Answer the management interview

Ora asks only about unresolved parts of the management contract. The ten dimensions are:

| Dimension | What a useful answer supplies |
|---|---|
| Intended result | A concrete completed outcome, not “build an automation.” |
| Affected parties | Who uses, receives, approves, or could be harmed by the result. |
| Inputs and outputs | What the Process reads and what exact result it should produce. |
| Reuse | One-time work or a capability intended for later Runs. |
| Initiation | Manual request, a separately authorized trigger, or another declared start. |
| Authority | What Ora may decide or change and what must return to you. |
| Exceptions | Conditions that require correction, blocking, or a human decision. |
| Permissions | Exact systems, files, tools, and effects that may be used. |
| Evidence | What would prove the result is current and correct. |
| Stopping | When the Process must stop rather than continue or improvise. |

Answer the question currently shown. “I do not know,” placeholders, and vague objectives do not silently resolve a dimension; Ora leaves it open and asks for usable input. If you submit the same answer twice because of a retry or connection failure, the recorded answer is returned instead of being consumed as the answer to the next question.

Temporary analytical frameworks may help you think during the interview. Their results return to the same Dialogue; they do not replace the governing Process or acquire its authority.

When all ten dimensions are resolved, the same management surface changes to **Prepare canonical plan**. Confirm the **Exact target folder**, then enter the exact target-relative items—one file or directory path per line. The folder and items become authenticated planning inputs, not an inferred grant. Ambiguous paths, parent-directory escapes, wildcards, missing targets, and empty scope fail closed. Choose **Prepare plan** to create the proposal; this still does not approve or start anything.

### Review and approve the plan

Ora produces one canonical plan with two views:

- **Principal view:** outcome, users, scope, authority, risks, exceptions, proof, and activation request.
- **Technical view:** artifacts, architecture, dependencies, implementation sequence, tests, evidence identities, versioning, and recovery.

The browser opens these as **Principal view** and **Technical view** tabs in the **Plan review** surface. The surface shows the exact plan ID, version, and digest above both projections. Switching tabs changes only the projection—not the plan being decided.

Review the Principal view first. Open the Technical view when you need to confirm exact paths, selectors, commands, tests, or repository state. Both views refer to the same plan identity; changing a material field requires a new version.

At the approval boundary, choose one exact action:

- **Approve and start** approves this plan version and delegates it.
- **Approve without starting** records the approval but withholds execution until a later explicit start.
- **Request plan changes** keeps the objective and asks for a revised plan.
- **Change scope or permissions** requires a revised plan with different authority or artifacts.
- **Stop and retain the plan** ends the pre-execution Run without discarding the reviewed plan.

These five buttons send authenticated actions for the exact plan shown. Actions that revise, change scope, or retain the plan ask for a material reason before submission. If the server rejects an action, the error remains visible in the Plan review surface and no success state is invented.

After **Approve without starting**, the surface says execution remains withheld and shows **Start approved plan**. Use that control later to delegate the exact approved plan and approval receipt. Do not type “start” into the Inquiry pane as a substitute for this control.

Check the target baseline immediately before approval. If the target changed after planning, Ora marks the plan stale and withholds approval until a revision binds the current identity.

Plan approval is not blanket consent. Construction, registration, invocation, activation, trigger binding, and external effects are separate authorities. Approving construction does not activate the resulting capability. Approving a plan does not let a model expand the project or artifact scope later.

### Leave and return

After **Approve and start**, the delegated Run appears under **Processes**:

| Surface | What it means |
|---|---|
| **Pending** | A live Run is executing, waiting at a declared boundary, or blocked. Healthy work stays visually quiet. |
| **Unread** | A result or focused decision has returned and has not yet been opened. |
| **Automated Processes** | An activated standing definition is visible with its declared trigger and authority bindings. This view does not itself create or edit those bindings. |
| **Process Library** | Exact registered definitions available for discovery and permitted invocation, with version, digest, scope, package, and lifecycle metadata. |

Select a Process card to return to its governing Dialogue. Choose **Inspect** to open the authenticated Run Inspector. Opening an Unread card marks the governing Dialogue read; it does not accept the result or grant authority.

You may close the browser or restart Ora. The Dialogue binding, plan, Run, artifacts, attempts, checkpoints, evidence, and receipts persist. Reopen the same Dialogue, Pending card, or Inspector after restart. Do not start a duplicate Run merely because the browser was closed.

If you return while the management interview, plan review, or approved-without-start state is active, Ora reconstructs and reopens that surface for the Dialogue. It returns to the exact current question, plan version, stale state, or **Start approved plan** control. New Inquiry text cannot bypass that active management boundary.

Leaving does not create an autonomous background Agent. Ora preserves exact state and advances only through supported runtime events and declared routes. It does not invent new work because you are absent.

### Respond to a decision request

When a Run needs reserved authority, it appears prominently in Pending or Unread. Open **Inspect** and read the Overview before choosing:

- **Outcome** — what the Run is trying to produce.
- **State** — the current visible state and graph phase.
- **Next** — the declared route or routes available from here.
- **You** — the exact decision required from the Principal.

If the Run is waiting for authority, the Inspector shows **Authority requested** with the request type, requested authority, and declared options. Choose:

- **Approve request** to grant only that exact request.
- **Deny request** to follow the request’s declared denial or blocked route.
- **Authority unavailable** when the requested authority cannot be supplied.

Use the governing Dialogue when you need discussion before deciding. Discussion does not itself approve, deny, modify scope, or advance the Run. Return to the explicit authority control for the actual decision.

Never approve from the short label alone. Check the evidence, affected artifact, requested selector, and consequence. An `ESCALATE` request means the Process cannot own the next decision; it is not a recommendation that must be accepted.

### Read the Run Inspector

The Inspector opens on Overview and provides nine progressively disclosed views:

| View | Use it to answer |
|---|---|
| **Overview** | What is the outcome, current state, credible next action, and required user action? |
| **Plan** | Which exact canonical plan and approval govern this Run? |
| **Current State** | Which node is active, how many attempts have occurred, and what routes remain? |
| **Decisions** | Which human checkpoints and graph decisions occurred, who decided, under what authority, and where did they route? |
| **Changes** | What happened to the approved repository or external target, and which receipts bind the effects? |
| **Evidence** | Which checks apply to which exact result identities, and are they current? |
| **Permissions** | What authority, artifact scope, reserved actions, and stop/escalation rules govern the Run? |
| **Artifacts** | Which result, capability, evidence, receipt, and working artifacts exist? |
| **Technical** | What definition, records, files, diff, tests, logs, and machine details support the projection? |

The evidence banner has literal meaning:

- **Current evidence supports the result** means the required passing evidence is bound to the current result and target identity.
- **Current evidence does not yet support acceptance** means evidence is missing, failed, stale, or bound to an older identity.

Read the Evidence view before treating a result as complete. A produced artifact is not the same as an accepted result. Final `ACCEPT` is a governed transition supported by current independent review; there is no user button that can convert stale or missing evidence into acceptance.

If Changes reports an unexpected repository, ambiguous targets, or external drift, stop and resolve that condition. Do not infer that the newest artifact is the approved target.

### Inspect or edit technical work

Open **Changes** for the approved target and the diff from its baseline. Use **Copy target path** when it is available, then inspect the files in your preferred editor. Open **Technical** for exact records, tests, logs, definition identity, and lower-level state.

You may edit an authorized target externally. Ora detects that the target identity changed and invalidates evidence tied to the earlier state. The edited artifact must be recaptured and re-inspected before acceptance. Do not paste an inline hash or statement that “tests passed” as a substitute for authenticated repository state and test evidence.

If the working tree contains unrelated changes, preserve them. Do not approve a plan that assumes they can be overwritten. Ask for a narrower artifact scope or a revised plan.

### Author a reusable Process

Use this path only after the management interview is complete:

1. In the plan-preparation surface, choose **Author reusable Process**.
2. Review the proposed name, purpose, exact version/digest, ordered steps, and every human checkpoint. Ora does not add a Trigger, Persona, schedule, activation, outbound action, or external effect here.
3. Choose **Request definition changes** and give a concrete reason, or choose **Approve and register exact definition**. Approval applies only to the exact proposal identity shown.
4. When Ora reports that the Process is available, close the review and open **Process Library** when you are ready to run it.

Registration makes the exact definition durable; promotion makes it discoverable in the current Project. Neither action runs it, schedules it, activates standing work, or grants sending/publication authority. A changed proposal needs a new review and identity.

### Run a reusable Process manually

1. Open **Process Library** and select an available reusable Process.
2. Read its exact identity and enter the required inputs. The form is generated from the registered input schema; missing, extra, or malformed values are rejected.
3. Check **I confirm this Run belongs to Project: …**. The Project controls scope. Any existing Project, Process, Step, or one-run Model Profile selections and the existing output Style are resolved and bound by the server; Persona is unavailable and is not selected.
4. Choose **Start governed Run**. Ora starts one restart-safe Run of that exact version in a separate no-tools worker.
5. At each human checkpoint, inspect what has already been produced. Choose **Approve checkpoint** only to advance that Run, or **Deny and stop**. Checkpoint approval does not activate, schedule, send, or widen authority.
6. If execution pauses after a failure, choose **Retry from checkpoint** only after reading the error. Completed steps are preserved; Ora does not replay them merely because the service restarted.
7. Treat the displayed result as authenticated only when the Run is completed after independent verification.

The worked email Process classifies and summarizes one supplied email, pauses before drafting, and produces an **UNSENT DRAFT**. It cannot send the draft. Sending, recurring execution, and channels belong to later separately governed work.

### Find and invoke a reusable Process Definition

Open the **Process Library** and select a row only after checking:

- display name and description;
- exact `definition_id@version`;
- digest;
- project or universal scope;
- package identity and member count; and
- lifecycle status.

After selection, state **What should happen?** and confirm the project. Ora resolves the exact registered identity and starts one restart-safe governed Run only when the definition is available, active where required, in scope, and compatible with the supplied inputs. A retry returns the same Run and result rather than executing the definition again.

If Ora reports **awaiting activation**, no invocation and no Process Run have started. Request activation explicitly. Registration does not imply activation, and activation does not invent a trigger or external-effect permission. Forged, stale, unavailable, inactive, and out-of-scope references fail closed.

The current public Library route supports a bounded non-external action entry followed by verification. More complex external-effect entry shapes use dedicated governed paths. A Library invocation may produce a result that still awaits independent final acceptance.

### Understand activation and standing automation

Activation makes an exact definition available within a declared scope; it is not permission to do everything the definition can describe. A standing automated Process additionally needs a trigger binding and an authority binding. The trigger begins a new governed Run under those bindings; it does not grant new authority.

G1.1 exposes activated definitions under **Automated Processes**, but it does not ship a general trigger-management or broad activation interface. If no supported activation path is offered, the correct state is waiting for activation—not manual registry editing or an assumed deployment. Treat trigger creation, remote messaging, publication, and other reserved effects as separate work requiring explicit authority.

### Pause, stop, discuss, and recover

At plan review you can **Stop and retain the plan** before execution. During execution, a Run may pause at a declared human checkpoint, wait for authority, or become `BLOCKED`. Open the governing Dialogue to discuss the condition; use the Inspector’s explicit decision control to change state.

The current G1.1 interface does **not** provide a general button to force an arbitrary active Run to pause, stop, resume, or reopen after closure. Do not use Archive or Discard as a substitute for stopping active work; lifecycle choices appear only after the Run is terminal.

Recovery is identity-preserving:

1. Restart Ora using the platform instructions in this guide.
2. Reopen the same Dialogue or Process card.
3. Inspect Current State, Changes, and Evidence.
4. Continue only from the declared next route or exact user decision.

Ora reconstructs persisted state and validates effects recorded after checkpoints. It does not replay a recorded mutation. If an external action may have happened but its receipt is missing or inconsistent, do not retry the action. Inspect the external system and return evidence through the governed recovery route.

### Close a terminal Run

Every terminal Run requires one explicit lifecycle disposition:

- **Promote** preserves an authenticated capability as a reusable promoted definition. This appears only when an eligible capability artifact and accepted result are bound to the Run.
- **Preserve** keeps the effective output artifacts in their current retained state without promoting a capability.
- **Archive** marks the outputs archived; it does not delete source files.
- **Discard** marks the outputs discarded; it does not delete source files.

The choice is recorded once with an identity-bound receipt. Retrying the same request returns the recorded lifecycle state. None of the four choices activates standing automation.

There is no general **Reopen** action after lifecycle closure. If more work is required, start a new governed Run against the exact retained artifact or definition. Before terminal acceptance, use correction, replanning, redefinition, or an authority route rather than closing and attempting to reopen.

### Troubleshoot a governed Process

| What you see | What it means | What to do |
|---|---|---|
| A recurring setup request returned an ordinary answer | The request was classified as generation rather than construction | Use Programming/Build or restate the effect to establish; confirm that the project form appears before proceeding |
| The interview repeats a question | The answer did not materially resolve that dimension | Give a concrete answer tied to the requested result, party, input/output, permission, evidence, or stop condition |
| A retried answer does not advance | The original answer was already persisted | Continue from the question now shown; do not reword solely to force another state change |
| Prepare plan rejects the target or scope | The folder is unavailable or an item is empty, ambiguous, absolute, wildcarded, or escapes the target | Confirm one exact existing target folder and enter only exact target-relative items, one per line |
| A plan action shows an error | The exact plan, baseline, approval receipt, authority, or persisted state did not validate | Keep the surface open, read the error, reload the same Dialogue if needed, and act only on the reconstructed current plan |
| The plan says stale | The target identity changed after planning | Request a revised plan against the current baseline; do not approve the old version |
| Approval succeeded but execution did not start | You chose Approve without starting, or delegation was withheld | Reopen the same Dialogue and choose **Start approved plan** after resolving any stale target |
| A Run appears stuck in Pending | It may be healthy, waiting at a declared boundary, blocked, or missing evidence | Open Inspect; read Overview, Current State, Evidence, and You. Do not start a duplicate Run |
| A decision card appears | Reserved authority is required | Inspect the exact request and evidence, then Approve, Deny, mark Authority unavailable, or discuss in the governing Dialogue |
| Evidence is stale | The result, target, or evidence artifact changed | Recapture and re-run the required inspection; stale proof cannot support `ACCEPT` |
| Changes shows the wrong or ambiguous target | The approved target cannot be authenticated | Withhold action and request corrected scope; do not select the newest artifact by assumption |
| Ora restarted during work | Durable state should reconstruct from records | Reopen the same Dialogue/Run and inspect its current state; do not replay effects or create a replacement Run |
| An external effect may have partially completed | Repeating it could duplicate or worsen the effect | Stop further action, inspect the external state and receipts, and use the declared recovery or authority route |
| A Library capability is missing or says awaiting activation | It is unavailable, inactive, out of scope, or not authenticated | Confirm project, exact version/digest, and lifecycle. Request activation only through a supported explicit path |
| A result exists but the Run is not completed | Production and acceptance are separate | Read Evidence; wait for or perform the declared independent review rather than treating output presence as completion |
| Promote is unavailable | The Run has no authenticated promotable capability binding | Choose Preserve, Archive, or Discard as appropriate; do not infer a reusable capability from artifact shape |
| A closed Run needs more work | Lifecycle closure is final for that Run | Start a new Run bound to the retained artifact or exact Process Definition; no generic reopen control exists |

For server, model, and installation failures, use the general **Troubleshoot** section later in this guide. For internal graph, schema, migration, or rollback diagnosis, consult the technical documentation; those are maintainer tasks, not user controls.

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
| Browser: "connection refused" | The server isn't running | On macOS install supervision with `./scripts/ora-launchd.sh install`, or run `./start.sh`; use the exact URL either command reports. On Windows-native, run `start.bat` `[untested, flag-incomplete]` |
| "No AI endpoints configured" | No working model key | Start the server, open its reported local URL, then add a key in **Settings → External APIs** |
| `<tool_call>` tags in the response | You're connected to a commercial AI directly, not to Ora's local server | Use the exact local URL Ora reports, not claude.ai / ChatGPT |
| Health passes, but Ora cannot read `~/Documents` | macOS privacy controls denied the supervised process access | Inspect `logs/ora-server.stderr.log`. In **System Settings → Privacy & Security**, grant the selected Python/Ora process **Files & Folders** access or **Full Disk Access**, then restart the service |
| Garbled output from a local model | The chat template needs a re-check | Switch models, or re-run the model setup |
| Output repeats itself | The Dialogue has grown too long | Start a new Dialogue |
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

---

## Changelog

- **2026-07-23** — Added the G1.18 reusable-Process journey: definition review/revision/approval, exact registration and promotion, schema-driven inputs, explicit Project confirmation, no-tools manual execution, human checkpoint and restart/retry behavior, and the unsent-email boundary. Persona, Trigger scheduling, channels, and external effects remain unavailable here.
- **2026-07-20** — G1.4: documented the shipped description-rich Dialogue creation review, combined prior-Dialogue/atomic-note discovery, server-issued exactly-once creation contract, contributor versus parent lineage, Continue/Fork alternatives, unsent-draft behavior, privacy boundaries, and the same actions in Library. The vault remains canonical and the runtime guide body is synchronized from it.
- **2026-07-19** — G1.1 Phase 3.3 Gate correction: documented the shipped browser management surface, exact target/scope preparation, Principal/Technical tabs, five authenticated plan decisions, explicit later **Start approved plan** delegation, restart reconstruction, stale-plan handling, and visible failures. The correction adds only the browser-to-existing-governed-contract integration required by Gate 3.3; it does not enter Phase 3.4.
- **2026-07-19** — G1.1 Phase 3.3: added task-indexed governed-process guidance for entry, project/artifact scope, management interview, canonical plan approval, leave-and-return, attention and decisions, evidence, technical inspection/external edits, Process Library invocation, activation/standing-automation limits, pause/stop/discussion/recovery, terminal artifact lifecycle, and user troubleshooting. Recorded the one-time `86a888bc` runtime-to-vault reconciliation provenance and restored vault-canonical body parity. No runtime behavior changed during that one-time documentation reconciliation; the later Gate 3.3 browser correction is recorded separately above.
- **2026-07-12** — macOS operation now follows the consolidated supervision contract: `ora-launchd.sh install` is the recommended setup, `start.sh` and `stop.sh` delegate when supervision is installed, every operational step uses the exact reported port in the 5000–5010 range, and troubleshooting covers launchd logs plus the Documents/TCC permission caveat. The repository mirror remains body-identical.
- **2026-07-12** — Closure currency note: Commons is the universal all-Dialogue view (both unassigned and project-assigned Dialogues appear there); Commons saves now land at the vault root; and V3 uses one fixed resizable Inquiry/Findings/Aside/Exhibits workspace rather than selectable layout presets. The body remains pinned to `7a5e8f40`.
- **2026-07-11** — Interface strings caught up to the nomenclature (ora PR #211): the running UI now shows these names, so the earlier "interface may still show older labels" caveat was removed. Still terminology-only; content remains pinned to `7a5e8f40`.
- **2026-07-11** — Commons rename pass: the default project (where work lands when no project is selected) is now **Commons** in user-facing language, formerly General; its internal id is still `general` (code rename pending). Audited this guide — it contains no references to the default project, so no body text changed. Terminology only; content remains pinned to ora commit `7a5e8f40`.
- **2026-07-11** — Code-level rename landed (ora PR #218, commit `062b67a7`, well after this document's `7a5e8f40` pin): the default project's internal nexus id is now `commons`, with the legacy id `general` still recognized everywhere, permanently — not a one-time migration. This guide names no internal ids, so no body text changed. A currency note only; this document's pinned content is not re-audited against `062b67a7`.
- **2026-07-11** — User-facing nomenclature pass: Dialogues (conversations), Inquiry pane (text input), Findings pane (text output), Exhibits pane (visual canvas), Aside (side-model chat panes), Library (browse modal). Terminology only — content remains pinned to ora commit `7a5e8f40`; this is not a re-pin and the parity audit was not re-run.
- **2026-07-04** — Initial version (Documentation-Code Parity closeout, pinned to `7a5e8f40`).
