### PHASE 2, LAYER 7: DESKTOP LAUNCHER CONTRACT

**Status 2026-07-12: reconciled legacy natural-language installer layer.** Do
not execute this file as the live installer. Use `scripts/install.py --profile
solo`; this layer is retained as the target contract for G3.32 reconciliation.

**Stage focus:** Preserve one server command and environment across interactive,
desktop-app, and supervised launch paths while keeping stop operations scoped to
the exact checkout that owns the process.

## Current Launcher Architecture

- `[workspace]/run-ora-server.sh` is the canonical foreground launcher. It
  canonicalizes `ORA_HOME`, supplies the runtime feature policy and executable
  search path, resolves Python, enables oversight by default, and `exec`s
  `[workspace]/server/server.py` without backgrounding.
- `[workspace]/start.sh` is the interactive cross-platform entry point. It
  delegates to the foreground launcher, discovers the selected port in
  5000–5010, verifies that `/health` reports this checkout's canonical
  `ora_home`, and opens that exact origin. It backgrounds the foreground
  launcher only when no macOS supervised service is installed.
- `[workspace]/stop.sh` delegates to the macOS service manager when launchd is
  available. Its unsupervised fallback may terminate only a Python process whose
  next argument is this checkout's exact `server/server.py`; path substrings,
  other worktrees, editors, tests, and similarly named backups are not matches.
- On macOS, `[workspace]/scripts/ora-launchd.sh` renders
  `installer/macos/com.ora.server.plist.template`. The per-user service runs the
  foreground launcher with `RunAtLoad` and `KeepAlive`, verifies the expected
  checkout's health before reporting success, and unloads a failed crash loop.
- An existing ignored `Ora.app` is updated from
  `installer/macos/ora-app-launcher.sh`. The shim derives its checkout from the
  app bundle and delegates to `start.sh`; it never carries a second server
  command or environment policy.
- Linux/WSL retain the unsupervised `start.sh` / `stop.sh` path. Windows retains
  its native batch launchers until that path receives its separate validation
  cycle.

## Reconciliation Constraints

An installer or fork reconciliation **must not**:

- reintroduce `pkill -f server/server.py`, a repo-agnostic `pgrep`, or another
  broad process-kill pattern;
- place an independent `python server/server.py` command or duplicate feature
  flags in `start.sh`, an app bundle, or a service wrapper;
- accept the first process answering `/health` without matching its `ora_home`;
- hardcode port 5000 when the server may select 5001–5010;
- stop, uninstall, or report ownership of the user-global launchd label from a
  different checkout. A target-mismatch override is for deliberate recovery or
  teardown only;
- background the process inside the launchd foreground launcher. launchd must
  supervise the process that becomes the Python server via `exec`.

## Install and Operation

The recommended macOS post-install action is:

```bash
./scripts/ora-launchd.sh install
```

The command installs and starts the service, updates an existing `Ora.app`, and
prints the exact health URL. `./start.sh` opens the matching UI origin;
`./stop.sh` stops the service without removing its plist;
`./scripts/ora-launchd.sh restart|status|uninstall` provide explicit lifecycle
operations.

On Linux/WSL, or for a deliberately unsupervised macOS session before service
installation, use `./start.sh` and `./stop.sh`.

## Verification Record

1. Run the foreground launcher with a fake Python executable and verify exact
   argv, environment parity, no-argument Bash 3.2 behavior, and `--no-oversight`.
2. Render and lint the plist; verify absolute physical paths, sparse-PATH
   recovery, `RunAtLoad`, `KeepAlive`, working directory, and bounded log paths.
3. Install twice against a fake launchctl domain; verify idempotence, app
   delegation, stop/start, and exact-checkout health readback.
4. Present decoy process rows containing the server path and verify only the
   exact Python invocation is selected.
5. Invoke `stop.sh` and uninstall from a different worktree and verify the
   canonical service remains loaded until a deliberate teardown override.
6. Simulate a wrong-checkout or failed health response; verify the command
   fails, shows the stderr tail, and unloads the KeepAlive crash loop.
7. Verify the browser uses the origin corresponding to the reported health port
   (5000–5010), and that the interface responds there.

### Output Format for This Layer

```text
DESKTOP LAUNCHER CONTRACT VERIFIED
Foreground authority: [workspace]/run-ora-server.sh
Interactive start: [workspace]/start.sh
Scoped stop: [workspace]/stop.sh
macOS service: com.ora.server [installed / not installed / n-a]
Health URL: [exact reported URL]
Checkout identity: [canonical ORA_HOME]
Desktop app delegation: [verified / absent / n-a]
Tests: [PASS / FAIL]
```

---
