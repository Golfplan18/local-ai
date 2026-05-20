# Install Testing Protocol

Formal protocol for verifying the install scripts against clean-room environments. This is what we cycle when shipping changes to `scripts/install.py`, `scripts/install-server.sh`, or any of their dependencies.

The companion docs:

- **`install-guide.md`** — happy-path walkthrough
- **`install-recovery.md`** — recover from a partial install failure
- **`install-manual.md`** — eight-command manual fallback

---

## Test matrix

Three environments cover the supported platforms:

| Environment | Platform | Role |
|---|---|---|
| **Mac Mini A** | macOS, Apple Silicon | Primary clean-state testing |
| **Mac Mini B** | macOS, Apple Silicon | Spare / parallel-cycle testing |
| **Parallels Windows 11 VM** | Windows 11 ARM via Parallels | Windows fresh-install testing |

**Linux is out of the test matrix** but ships best-effort. Community contributions for Linux testing are welcome.

Each environment exercises **each of the three deployment profiles** (Solo, Hybrid, Organization) once the profile is enabled in `install.py`. Today, only Solo is enabled — Hybrid and Organization are gated on the concurrency-architecture work landing.

---

## Reset to clean state

Two paths for resetting an environment between test cycles:

### Parallels VM snapshot revert

For the Windows VM (and optionally Mac Minis if you've set up Parallels snapshots there):

1. In Parallels Desktop, right-click the VM → Snapshots Manager
2. Revert to a snapshot taken before any Ora install
3. Boot the VM clean

This is the most reliable reset — every install state is rolled back, not just the Ora-specific bits.

### Uninstall script

For Mac Minis without snapshots:

```bash
cd ~/ora
python3 uninstall/uninstall.py
```

Multi-step typed-DELETE confirmation. Removes:

- `~/ora/.venv/`
- Generated config files (`config/configurations/user-pipeline-auto.json`, `config/model-catalog.json`)
- Cache directories
- Optional: downloaded local models (opt-in flag — preserved by default)
- Optional: conversation history (opt-in flag — preserved by default)

Defense-in-depth hard-preserve: never touches the vault (`~/Documents/vault/`), source tree (`~/ora/`'s git checkout), or the uninstaller itself.

Flags:

```bash
python3 uninstall/uninstall.py --dry-run         # preview without changing anything
python3 uninstall/uninstall.py --include-models  # also remove downloaded HuggingFace models
python3 uninstall/uninstall.py --include-conversations  # also remove ~/Documents/conversations/
```

---

## Test cycle

Run this end-to-end on each environment for each deployment profile being tested.

### 1. Reset to clean state

Snapshot revert OR `uninstall/uninstall.py`. See above.

### 2. Pull latest

```bash
cd ~/ora  # or the directory you'll clone into
git pull origin main
# Or for first-time:
git clone https://github.com/ora-commons/ora.git ~/ora
cd ~/ora
```

### 3. Verify API keys are exported

```bash
echo "OpenRouter: ${OPENROUTER_API_KEY:+SET}"
echo "AA:         ${AA_API_KEY:+SET}"
```

Both should print `SET`. If either is empty, export them before continuing — re-running mid-cycle to fix a missing key invalidates the timing measurements.

### 4. Run the bootstrap

#### Mac

```bash
python3 scripts/install.py --profile solo 2>&1 | tee ~/ora/install.log
```

#### Linux server

```bash
./scripts/install-server.sh 2>&1 | tee ~/ora/install.log
```

(Or `install-bootstrap-linux.sh` once that exists; today it's the same script.)

### 5. Observe

Watch for:

- **Unclear prompts** — note them. Friction points are install-quality bugs.
- **Errors** — note the step, capture the stderr, screenshot if possible.
- **Time per step** — the installer logs timestamps; eyeballing the gaps tells you which steps are slow.
- **AA-warning behaviour** — if `AA_API_KEY` is unset, the installer should pause for Enter. Confirm this works as designed.

### 6. Verify pass criteria

A clean install means **all** of these are true:

- [ ] Script completed without manual intervention beyond initial API-key prompts.
- [ ] `~/ora/install.log` ends with `INSTALL_COMPLETE: 0 warnings, 0 errors`.
- [ ] Smoke test passed (Step 6/6 for Mac, the `install_server_smoke.py` run for Linux).
- [ ] Browser opens to `localhost:5000` and the V3 UI renders (Mac install only — server install doesn't bind Flask publicly).
- [ ] First conversation can be started within:
  - **30 seconds** of script completing — for cloud / API-only profiles
  - **60 seconds + download time** — for profiles that include local models

If any of these fail, the cycle is a fail. See Fail flow below.

### 7. End-to-end model call

Final validation — an actual API round-trip:

```bash
cd ~/ora
# Mac:
python3 -c "
import sys; sys.path.insert(0, 'orchestrator')
from model_dispatch import invoke_chat
print(invoke_chat(
    system_prompt='Respond with exactly one word.',
    user_prompt='What is the capital of France?',
    slot='breadth',
))
"
# Linux server:
source .venv/bin/activate
set -a; source ~/.config/ora-server.env; set +a
python3 -c "
import sys; sys.path.insert(0, 'orchestrator')
from model_dispatch import invoke_chat
print(invoke_chat(
    system_prompt='Respond with exactly one word.',
    user_prompt='What is the capital of France?',
    slot='breadth',
))
"
```

Expected output: `Paris` or similar single-word response. Confirms slot routing → API → model → response works end-to-end.

---

## Fail flow

When a cycle fails:

1. **Capture the install log** in full.
2. **Screenshot the failure state** — the terminal output at point of failure, and any UI state if relevant.
3. **Note environment-specific details:** macOS / Windows version, Python version, free disk, free RAM, network conditions.
4. **Share with the diagnostic session** — open a fresh Claude Code conversation, paste the log and screenshots, ask for triage.
5. **Apply the fix.**
6. **Reset, pull, retest** — the cycle starts over from step 1.

Cycle until all three environments pass with **zero glitches** under each of the three deployment profiles.

---

## Rolling-main install

The install script materializes whatever's on `main` at install time. You can continue modifying Ora during install testing; each test cycle pulls fresh from the repo.

**Install bugs vs Ora-side bugs are distinguishable:**

- **Install bugs** error during script execution. Failure shows up in `install.log`.
- **Ora-side bugs** error during the smoke test (step 6/6) or first conversation. Failure shows up in chat-server stderr or the V3 UI.

When triaging a failed cycle, the location of the failure tells you which side to fix.

---

## What "shipped" means

The install scripts are not shipped until **all three environments pass with zero glitches across all enabled deployment profiles**. Today that means:

- Mac Mini A, Solo profile — must pass
- Mac Mini B, Solo profile — must pass
- Parallels Windows 11, Solo profile — must pass

When Hybrid and Organization profiles enable (gated on the concurrency-architecture work), the matrix expands to nine cells. Until then, three is enough.

---

## Snapshot reset commands (reference)

### Parallels Desktop

```
# Via UI:
Snapshots Manager → revert to "ora-clean-baseline"

# Via CLI (Parallels Desktop Pro / Business):
prlctl snapshot-switch <vm-name> --id <snapshot-uuid>
```

### Time Machine (Mac)

Time Machine restores aren't fast enough for a test cycle — recommend Parallels snapshots on the test Macs instead, or use the uninstall script for in-place reset.

### Image-based (manual)

For a truly clean macOS test environment, image the boot disk before any Ora install via `asr` (Apple Software Restore). Heavy-handed; only useful for the first cycle.

---

## Related documents

- `install-guide.md` — happy-path walkthrough
- `install-recovery.md` — recover from a partial install failure
- `install-manual.md` — manual command fallback
- `cloud-ora-install.md` — server-install operator guide
- `../uninstall/` — the uninstaller and its docs
