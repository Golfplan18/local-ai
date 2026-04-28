### PHASE 1, LAYER 5: COMMERCIAL AI CONNECTIONS

**Stage Focus:** Set up browser automation connections to commercial AI services, giving every reader access to cloud AI through their existing subscriptions.

### Processing Instructions

This layer configures Playwright browser automation to access commercial AI services. This is the primary evaluation channel for all tiers. It uses the reader's existing free or paid subscriptions at no additional cost.

1. Present the following explanation:

   ```
   Your system can access commercial AI services (Claude, ChatGPT, Gemini)
   through your web browser — using any accounts you already have.

   This works by automating your browser to send prompts and receive
   responses, just like you would do manually. Your existing free or
   paid subscriptions work — no API keys or credit cards needed.

   I'll help you connect to whichever services you use. You can add
   more later at any time.

   Which services do you have an account with?

   A) Claude (Anthropic) — claude.ai
   B) ChatGPT (OpenAI) — chat.openai.com
   C) Gemini (Google) — gemini.google.com
   D) Multiple — I'll set up each one
   E) None yet — I'll create a free account
   F) Skip this for now — I'll add connections later
   ```

2. For each selected service, execute the Browser Evaluation Setup Framework (`[workspace]/frameworks/book/browser-eval-setup.md`). IF the framework is not yet available from the repository, THEN execute the inline connection procedure:

   a. Launch Playwright with visible browser: `playwright.chromium.launch(headless=False)`.
   b. Navigate to the service's login page.
   c. Instruct the user: "Please log in to [service] in the browser window that just opened. When you're logged in and can see the chat interface, tell me and I'll save the session."
   d. Wait for user confirmation.
   e. Save the browser session state: `context.storage_state(path='[workspace]/config/browser-sessions/[service].json')`.
   f. Test the connection by sending a minimal test prompt ("Say hello.") via browser automation.
   g. IF the test succeeds, register the endpoint in `endpoints.json`.
   h. IF the test fails, report the failure and offer to retry or skip.

3. For each successfully connected service, add an entry to the endpoint registry:

   ```json
   {
     "name": "[service]-browser",
     "type": "browser",
     "service": "[claude|chatgpt|gemini]",
     "session_path": "config/browser-sessions/[service].json",
     "status": "active",
     "verified": "[date]"
   }
   ```

4. Set the default endpoint to the first successfully connected service.
5. **Terms of service note:** Present to the user: "Browser automation accesses these services through the same interface you use manually. Check each service's current terms of service regarding automated access. Enterprise users with API agreements should use API keys directly (covered in a later chapter) rather than browser automation."
6. IF the user selected "None yet" (option E), THEN:
   - Open the signup page for Claude (free tier) in the browser.
   - Guide the user through account creation.
   - After account creation, proceed with connection setup.
   - Claude's free tier provides immediate access to adversarial evaluation at no cost.

7. IF the user selected "Skip" (option F), THEN:
   - Record that no commercial AI connections are configured.
   - Note in the endpoint registry that the system is local-only until connections are added.
   - Inform the user: "You can add commercial AI connections later by telling your AI: 'Read and execute frameworks/browser-eval-setup.md'"

8. Install automatic session refresh. Browser session cookies expire over time. This step installs a background system that re-extracts cookies automatically whenever Chrome, Firefox, or Safari quits, so sessions stay current without any user action.

   **Prerequisite — first-time login instruction.** The refresh system can only capture cookies that already exist in a browser. Before proceeding, present the following to the reader:

   ```
   One-time setup: log into your AI accounts in each browser you use.

   For each browser installed on your machine (Chrome, Firefox, Safari, etc.):
     1. Open the browser.
     2. Go to claude.ai and log in (if you have an account).
     3. Go to chat.openai.com and log in (if you have an account).
     4. Go to gemini.google.com and log in (if you have an account).
     5. Quit the browser completely (Cmd+Q on Mac, File > Quit on Windows/Linux).

   You only need to do this once. After quitting, your login sessions are
   saved automatically and kept current from that point forward.

   Skip any service you don't use. Skip any browser you never use.
   ```

   Wait for the reader to confirm they have completed this step before continuing. IF the reader skips entirely, note in the installation report that sessions have not been seeded and the auto-refresh system will capture nothing until they log in and quit a browser.

   a. **Detect installed browsers and their cookie locations.**

      For each of the following, check whether the browser is installed and locate its cookies file:

      - **Google Chrome:** `~/Library/Application Support/Google/Chrome/Default/Cookies` (macOS) or `%LOCALAPPDATA%\Google\Chrome\User Data\Default\Cookies` (Windows) or `~/.config/google-chrome/Default/Cookies` (Linux)
      - **Firefox / Firefox Nightly:** Read `~/Library/Application Support/Firefox/profiles.ini` (and the Firefox Nightly equivalent) to find the active profile directory. The cookies file is `[profile_dir]/cookies.sqlite`. On Windows: `%APPDATA%\Mozilla\Firefox\profiles.ini`. On Linux: `~/.mozilla/firefox/profiles.ini`. Check for both standard Firefox and Firefox Nightly profile directories.
      - **Safari (macOS only):** `~/Library/Cookies/Cookies.binarycookies`. Safari is present on all Macs. Always include it when running on macOS, regardless of whether the reader uses it as their primary browser.
      - **Other Chromium-based browsers** (Brave, Edge, Arc): check their respective Application Support directories. Cookie extraction uses the same Chrome SQLite schema.

      Record each detected browser's: cookies file path, lock file path (or equivalent), process name.

      Chrome lock file: `[Chrome User Data]/Default/SingletonLock`
      Firefox lock file: `[profile_dir]/lock`
      Safari lock file: none — Safari does not use a lock file. Use the cookies file itself as the WatchPaths target, and rely on `pgrep` to confirm Safari has quit before extracting.

   b. **Generate the session refresh script** at `[workspace]/config/refresh-sessions.py`. The script must:

      - Accept a `source` argument (`chrome`, `firefox`, `safari`, `auto`, `install`, or `manual`) for logging.
      - For each detected browser: check whether that browser is currently running (via `pgrep` on macOS/Linux, `tasklist` on Windows). IF running, THEN skip it — the cookie database may be locked or in an inconsistent state.
      - Copy the cookie database to a temp file before reading, to avoid locking the live database.
      - For Chrome/Chromium: query the `cookies` table. Extract `host_key, name, value, path, expires_utc, is_secure, is_httponly, samesite` for the target domains of each service (Claude, ChatGPT, Gemini). Convert Chrome's epoch (microseconds since 1601-01-01) to Unix epoch.
      - For Firefox: query the `moz_cookies` table. Extract `host, name, value, path, expiry, isSecure, isHttpOnly, sameSite` for the same target domains.
      - For Safari: parse `~/Library/Cookies/Cookies.binarycookies` using a pure Python binary parser. Safari cookies are stored in Apple's proprietary binary format — not SQLite. The format is: 4-byte magic (`cook`), 4-byte big-endian page count, array of 4-byte page sizes, then pages. Each page contains cookies with fields for URL, name, value, path, domain, expiry timestamp (Mac absolute time: seconds since 2001-01-01, convert by adding 978307200 to get Unix epoch), creation timestamp, and flags. Flags bitmask: bit 0 = isSecure, bit 2 = isHttpOnly. Implement the parser directly in Python using the `struct` module — do not depend on external libraries.
      - Merge strategy: when multiple browsers have cookies for the same service, merge by cookie name. Priority order (highest to lowest): Firefox, Chrome/Chromium, Safari. Higher-priority browser cookies overwrite lower-priority cookies for the same name. Cookies present only in a lower-priority browser are kept. This ensures the most-used browser's session is authoritative while capturing any service the reader only logged into in a secondary browser.
      - Write a Playwright-compatible storage state file (`{"cookies": […], "origins": []}`) for each service to `[workspace]/config/browser-sessions/[service].json`.
      - Log all actions with timestamps to `[workspace]/config/session-refresh.log`.
      - Send a macOS notification (`osascript display notification`) on success. On Linux, use `notify-send` if available. On Windows, use a PowerShell toast notification if available.
      - IF no cookies were extracted (all browsers running or no browsers detected), log this without error — it is normal.

      Target domains per service:
      - Claude: `.claude.ai`, `claude.ai`, `.anthropic.com`, `anthropic.com`
      - ChatGPT: `.openai.com`, `openai.com`, `chat.openai.com`, `.chatgpt.com`, `chatgpt.com`
      - Gemini: `.google.com`, `google.com`, `gemini.google.com`

   c. **Install OS-level file watchers** that trigger the script when a browser quits.

      **macOS — LaunchAgents:**

      For each detected browser, generate a `.plist` file at `~/Library/LaunchAgents/com.ora-ai.[browser]-sessions.plist`. The plist must:
      - Set `WatchPaths` to the browser's lock file path (Chrome, Firefox) or the cookies file path (Safari).
      - Call `python3 [workspace]/config/refresh-sessions.py [browser]`.
      - Use the full absolute path to the Python executable (from `which python3`).
      - Set `RunAtLoad` to false — only trigger on file change.
      - Redirect stdout and stderr to `[workspace]/config/session-refresh.log`.

      Load each agent: `launchctl load ~/Library/LaunchAgents/com.ora-ai.[browser]-sessions.plist`

      Note on Safari: because Safari's cookies file changes while the browser is running (not just on quit), the WatchPaths trigger fires frequently during a Safari session. The `pgrep Safari` check in the script ensures extraction only happens when Safari is actually closed. The frequent triggering is harmless — the script exits in under a second if Safari is still running.

      **Linux — inotifywait:**

      Generate a background watcher script at `[workspace]/config/watch-sessions.sh` that uses `inotifywait -m` to watch Chrome and Firefox lock files. Install `inotify-tools` if not present. Add the watcher to the system start script. Safari is not available on Linux — skip it.

      **Windows:** Generate a PowerShell script using `FileSystemWatcher` to watch Chrome and Firefox lock files. Register it as a scheduled task that runs at login. Safari is not available on Windows — skip it.

   d. **Run the script once immediately** after installation (with `source=install`) to populate sessions from any browsers the reader just quit during the prerequisite login step.

   e. **Verify LaunchAgents are registered (macOS):**

      ```
      launchctl list | grep com.ora-ai
      ```

      All agents should appear with status `0` (idle, waiting for trigger). A status of `0` is correct — it means the agent is loaded and watching.

   f. **IF no browsers were detected** (no cookies files found on the system), THEN:
      - Skip this step entirely.
      - Note in the installation report that automatic session refresh is not configured.
      - This is not a failure — it means the reader is using API keys rather than browser automation.

### Output Format for This Layer

```
COMMERCIAL AI CONNECTIONS
Services connected: [list]
Services skipped: [list]
Default endpoint: [name]
Endpoint registry: [workspace]/config/endpoints.json ([count] endpoints)
Browser sessions: [workspace]/config/browser-sessions/
Auto-refresh: installed (watching: [list of browser names]) / not installed (reason)
LaunchAgents: [list of registered agents, or "N/A — not macOS"]
```

---

