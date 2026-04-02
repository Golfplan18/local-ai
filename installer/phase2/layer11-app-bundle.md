### PHASE 2, LAYER 11: APP BUNDLE + CUSTOM ICON

**When to execute**: After Phase 2, Layer 10. macOS only. Skip on Linux and Windows — provide a plain shell script launcher instead.

**Purpose**: Replace the generic `.command` shell script (which shows the default macOS script icon in the Dock) with a proper `.app` bundle named "ai" with a custom lettermark icon.

### Processing Instructions

1. **Generate icon variants** using Pillow (install if needed: `pip install Pillow`). Run `make_icons.py` from the workspace root. This produces five `.icns` files in `config/icons/`:
   - `ai-dark.icns` — white lettermark on dark background (default)
   - `ai-light.icns` — dark lettermark on light background
   - `ai-amber.icns`, `ai-teal.icns`, `ai-blue.icns` — accent color variants

   Icon design: 1024×1024 base at 4× supersampling, downsampled with LANCZOS for anti-aliasing. Single-story geometric "a" (donut circle with bottom at baseline + right stem same height as circle) + geometric "i" (stem same height as "a", dot 1.5× stem width floating above with gap equal to letter spacing). Dark background #1a1a1a, foreground #f0f0f0. Flat, no gradients, no effects. Legible at 32×32.

2. **Build the `.app` bundle** at `[workspace]/ai.app/`:
   ```
   ai.app/
     Contents/
       Info.plist
       MacOS/
         ai              ← Python launcher (executable)
       Resources/
         ai.icns         ← active icon (copy of ai-dark.icns by default)
   ```

3. **Write `Contents/Info.plist`**:
   ```xml
   CFBundleExecutable: ai
   CFBundleIconFile: ai
   CFBundleIdentifier: local.ai.launcher
   CFBundleName: ai
   CFBundleDisplayName: ai
   CFBundlePackageType: APPL
   NSHighResolutionCapable: true
   LSMinimumSystemVersion: 12.0
   ```

4. **Write `Contents/MacOS/ai`** as a Python script with shebang `/opt/homebrew/bin/python3`. The launcher must use `subprocess.Popen(..., start_new_session=True)` to detach the Flask server into its own OS session. **Do not use `nohup` + `disown` in a shell script** — macOS kills the shell's process group when the executable exits, taking the server with it. Python's `start_new_session=True` is the reliable cross-session detach on macOS.

   Launcher logic:
   - `pkill -f server/server.py` (kill any stale instance)
   - `sleep 1`
   - `Popen([python, server_script], start_new_session=True, stdout=logfile, stderr=logfile)`
   - Poll `/health` up to 30s, then `subprocess.run(['open', 'http://localhost:5000'])`
   - `sys.exit(0)`

5. **Set executable bit**: `chmod +x ai.app/Contents/MacOS/ai`

6. **Copy default icon**: `cp config/icons/ai-dark.icns ai.app/Contents/Resources/ai.icns`

7. **Write `swap-icon.sh`** in the workspace root: accepts one argument (dark/light/amber/teal/blue), copies the chosen `.icns` to the bundle, runs `touch ai.app` to invalidate the icon cache.

8. **Install**: Instruct the reader to drag `ai.app` to `/Applications` or the Dock. On first launch, macOS will show an "unidentified developer" warning — right-click → Open to bypass once. After that, double-click works normally. To force icon refresh: `killall Dock`.

### Output Format for This Layer

```
APP BUNDLE INSTALLED
Bundle: [workspace]/ai.app
Launcher: Python (start_new_session=True detach)
Icon: ai-dark (default) — 5 variants in config/icons/
Icon swap: ./swap-icon.sh [dark|light|amber|teal|blue]
Install: drag ai.app to /Applications or Dock
First launch: right-click → Open (bypasses Gatekeeper once)
```

---

