### PHASE 2, LAYER 11: APP BUNDLE + CUSTOM ICON

**Status 2026-07-12: reconciled legacy natural-language installer layer.** Do
not execute this file as the live installer. Use `scripts/install.py --profile
solo`; this layer is retained as the app-bundle target contract for G3.32
reconciliation.

**When to apply:** After Phase 2, Layer 10. macOS only. Linux/WSL use the
unsupervised shell launcher; Windows retains its native batch launcher pending a
separate validation cycle.

**Purpose:** Provide an optional in-place `Ora.app` shell and custom icon without
creating another server command. The app delegates to the same tracked
`start.sh` path used interactively; the launchd service and
`run-ora-server.sh` remain the only supervision and foreground-server
authorities.

### Processing Instructions

1. **Generate icon variants** using the tracked `make_icons.py`. It requires
   Pillow and macOS `iconutil`. Run `python3 make_icons.py` from the workspace
   root. The script produces six ignored `.icns` files in `config/icons/`:
   - `ora-dark.icns` — white mark on a dark background (default)
   - `ora-light.icns` — dark mark on a light background
   - `ora-amber.icns`, `ora-teal.icns`, `ora-blue.icns`, and `ora-warm.icns`
     — accent variants

   The tracked design is Ora's `◎` mark: two concentric rings rendered at 4×
   supersampling and downsampled with LANCZOS. It is flat, high-contrast, and
   legible at small sizes.

2. **Build or retain the generated app bundle in place** at
   `[workspace]/Ora.app/`:
   ```
   Ora.app/
     Contents/
       Info.plist
       MacOS/
         ai              ← tracked Bash shim copy (executable)
       Resources/
         ai.icns         ← active icon (copy of ora-dark.icns by default)
   ```

   The bundle is generated per machine and ignored by git. Keep it directly
   under the checkout: the tracked shim derives the checkout from that location.
   Add the in-place bundle to the Dock if desired; do not move or copy it to
   `/Applications`, where the relative checkout derivation would no longer be
   valid.

3. **Write `Contents/Info.plist`**:
   ```xml
   CFBundleExecutable: ai
   CFBundleIconFile: ai
   CFBundleIdentifier: app.ora-ai.launcher
   CFBundleName: Ora
   CFBundleDisplayName: Ora
   CFBundlePackageType: APPL
   NSHighResolutionCapable: true
   LSMinimumSystemVersion: 12.0
   ```

4. **Install the tracked launcher shim.** Once
   `Ora.app/Contents/MacOS/` exists, run:

   ```bash
   ./scripts/ora-launchd.sh install-app --ora-home "[workspace]"
   ```

   This copies `installer/macos/ora-app-launcher.sh` to
   `Ora.app/Contents/MacOS/ai` with mode `0755`, preserving a one-time
   `.pre-supervision` backup of an existing launcher. The shim derives its
   checkout and `exec`s that checkout's `start.sh`. It must not contain a Python
   shebang, a direct `server.py` invocation, feature flags, broad `pkill`, a
   detached child process, or a fixed port.

5. **Install the default icon** with `./swap-icon.sh dark`. The tracked helper
   accepts `dark`, `light`, `amber`, `teal`, `blue`, or `warm`, honors
   `ORA_HOME`, validates the in-place bundle/resource directory, copies the
   matching `config/icons/ora-*.icns` to `Contents/Resources/ai.icns`, and
   refreshes LaunchServices when available.

6. **Install supervision** with `./scripts/ora-launchd.sh install`. That command
   updates an existing app shim, installs and starts `com.ora.server`, and prints
   the exact healthy origin selected in the 5000–5010 range. Double-clicking
   `Ora.app` thereafter opens that same checkout-specific origin and starts the
   installed service first if it was stopped.

7. **Preserve scoped lifecycle control.** Stop Ora with `[workspace]/stop.sh`;
   never add an app-local kill command. `stop.sh` unloads the matching launchd
   service or, in the unsupervised fallback, targets only the exact checkout's
   Python server invocation.

8. **First launch.** If macOS presents an unidentified-developer warning for
   the generated unsigned bundle, right-click `Ora.app` in the checkout and
   choose **Open** once. The bundle may then be pinned to the Dock without being
   relocated.

### Verification

1. Confirm `Ora.app/Contents/MacOS/ai` is byte-identical to
   `installer/macos/ora-app-launcher.sh` and executable.
2. Confirm the selected `ora-*.icns` exists and
   `Ora.app/Contents/Resources/ai.icns` was updated.
3. Start through `Ora.app`, read the exact URL reported by the launcher, and
   verify `/health` returns the physical `[workspace]` path as `ora_home`.
4. Run `[workspace]/stop.sh` and verify that checkout stops without touching a
   server from another worktree.

### Output Format for This Layer

```text
APP BUNDLE INSTALLED
Bundle: [workspace]/Ora.app (kept in place)
Launcher source: installer/macos/ora-app-launcher.sh
Server authority: [workspace]/run-ora-server.sh via com.ora.server
Health URL: [exact reported 5000–5010 origin]
Checkout identity: [canonical ora_home]
Icon: ora-dark (default) — 6 variants in config/icons/
Icon swap: ./swap-icon.sh [dark|light|amber|teal|blue|warm]
Scoped stop: [workspace]/stop.sh
First launch: right-click → Open if Gatekeeper prompts
```

---
