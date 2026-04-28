# Browser Evaluation Setup Framework

*Guided Setup for Commercial AI Browser Automation Connections*

---

## PURPOSE

This framework walks the user through connecting their system to commercial AI services (Claude, ChatGPT, Gemini) via Playwright browser automation. It handles initial setup and re-authentication when sessions expire. The local AI runs this framework through the orchestrator, launching a visible browser for the user to log in and saving the authenticated session for automated use.

## INPUT CONTRACT

Required:
- This framework loaded into the local AI system. Source: user tells the AI to read and execute this file, or the orchestrator invokes it when a browser session has expired.
- Playwright installed with Chromium browser binaries. Source: installed during the first boot framework Phase 1. IF Playwright is not installed, THEN inform the user and halt — run the first boot framework to install it.

Optional:
- **Service selection:** User states which service(s) to connect (Claude, ChatGPT, Gemini, or all). Source: user provides during execution. Default if absent: framework presents all three and asks.
- **Existing session files:** Previous sessions that may have expired. Source: `[workspace]/config/browser-sessions/`. Default if absent: framework treats this as a first-time setup for each service.

## OUTPUT CONTRACT

Primary outputs:
- Authenticated browser session files stored at `[workspace]/config/browser-sessions/[service].json` for each connected service. Quality threshold: each session file enables the `browser_evaluate` tool to send a prompt and receive a response without manual login.

Secondary outputs:
- Updated endpoint registry at `[workspace]/config/endpoints.json` with browser endpoint entries for each connected service.
- Connection summary noting which services were connected, which failed, and the date of each connection.

## EXECUTION TIER

Agent: This framework executes through the local orchestrator with tool access. It uses Playwright to launch a visible browser, waits for the user to log in, saves the session, and tests the connection. Minimal user interaction — the user logs in; the framework handles everything else.

---

## MILESTONES DELIVERED

This framework's declaration of the project-level milestones it can deliver. Used by the Problem Evolution Framework (PEF) to invoke this framework for milestone delivery under project supervision.

### Milestone Type: Registered browser evaluation endpoint

- **Endpoint produced:** For each requested service (Claude, ChatGPT, Gemini, or a user-specified URL): an authenticated Playwright session file at `[workspace]/config/browser-sessions/[service].json` plus a corresponding active entry in `[workspace]/config/endpoints.json` with `name`, `type: browser`, `service`, `session_path`, `status: active`, and `verified` (ISO date) fields. IF no `default_endpoint` was previously set, the entry is also installed as the default.
- **Verification criterion:** (a) the session file exists at the named path and loads without error into a fresh Playwright context; (b) a second Playwright context opened with that stored state reaches the service's chat page in a logged-in state (chat interface visible, no redirect to login); (c) a minimal test prompt ("Say hello.") sent through the `browser_evaluate` tool either returns a response within 30 seconds or the timeout is explicitly logged per Layer 3; (d) the endpoint registry entry exists for the service with `status: active` and the verification date populated, and no duplicate entry remains from a prior expired session.
- **Preconditions:** Playwright is installed with Chromium binaries (installed by the first boot framework Phase 1); the user can complete interactive login in a visible browser including any 2FA or CAPTCHA challenges; the target service's URL resolves and its chat page is reachable. Re-authentication invocation (when a specific prior session has expired) inherits the expired service name from the orchestrator and skips Layer 1's selection prompt per Execution Command 5.
- **Framework Registry summary:** Registers an authenticated Playwright browser session for a commercial AI service (Claude, ChatGPT, Gemini, or custom URL) as an active endpoint in `endpoints.json`.

---

## EVALUATION CRITERIA

1. **Connection Success:** At least one commercial AI service connected and verified.
   - 5: All requested services connected and verified with a successful test prompt.
   - 4: All requested services connected. One required a second login attempt.
   - 3: At least one service connected and verified. Others failed with clear explanation.
   - 2: Session files saved but verification failed for all services.
   - 1: No services connected.

2. **Session Persistence:** Saved sessions enable subsequent automated access without re-login.
   - 5: All saved sessions verified working via `browser_evaluate` tool test. Endpoint registry updated.
   - 4: Sessions saved and verified. Minor issue (e.g., one session required headless mode adjustment).
   - 3: Sessions saved. Verification passed in visible mode but headless mode not tested.
   - 2: Sessions saved but verification failed — sessions may require re-authentication.
   - 1: No session files produced.

3. **Endpoint Registry Accuracy:** The endpoint registry reflects the actual state of available connections.
   - 5: All connected services have correct, active entries in endpoints.json. Previously expired entries updated. No stale entries.
   - 4: Registry updated correctly. One minor field (e.g., verification date) not populated.
   - 3: Registry contains entries for connected services. May contain stale entries from previously expired sessions.
   - 2: Registry not updated despite successful connections.
   - 1: Registry corrupted or missing.

---

## NAMED FAILURE MODES

**The Headless Login Trap:** Playwright launches in headless mode (no visible browser), making it impossible for the user to log in. Correction: Always launch with `headless=False` during the login step. Headless mode is used only after a session is saved and verified.

**The Cookie Expiry Trap:** The user connects successfully, but the session expires hours or days later (service-dependent). The system silently fails with no clear error. Correction: The `browser_evaluate` tool must check response content for login redirect indicators before returning results. IF a login redirect is detected, THEN report "Session expired for [service]" and offer to re-run this framework.

**The Two-Factor Authentication Trap:** The service requires 2FA during login, but the automated browser doesn't display the 2FA prompt clearly or the user doesn't notice it. Correction: After navigating to the login page, explicitly tell the user: "Complete the login in the browser window, including any two-factor authentication prompts. Tell me when you can see the chat interface."

**The Captcha Trap:** Some services present CAPTCHA challenges during automated browser sessions. Correction: Launch with `headless=False` so the user can solve CAPTCHAs manually. Inform the user that CAPTCHAs may appear and are normal.

**The Wrong URL Trap:** Commercial AI services change their URLs and page layouts. The framework navigates to a URL that no longer reaches the expected page. Correction: After navigation, verify the page title or a known page element rather than assuming the URL is correct. IF the page doesn't match expectations, THEN report the issue and provide the expected URL for the user to navigate manually.

**The Session File Overwrite Trap:** Re-running this framework for one service accidentally overwrites session files for other services. Correction: Session files are named per-service (`claude.json`, `chatgpt.json`, `gemini.json`). Each service's login process only touches its own file.

---

## LAYER 1: SERVICE SELECTION

**Stage Focus:** Determine which services to connect or reconnect.

### Processing Instructions

1. Check for existing session files at `[workspace]/config/browser-sessions/`.
2. IF existing sessions found, THEN test each one:
   a. For each session file, attempt to load it in Playwright and navigate to the service's chat page.
   b. IF the page loads with a logged-in state (chat interface visible), THEN mark as "active."
   c. IF the page redirects to login, THEN mark as "expired."
   d. Report the results: "Found existing sessions: [service] (active), [service] (expired)."

3. Present the connection options:

   ```
   COMMERCIAL AI CONNECTIONS

   [IF existing sessions found:]
   Current status:
   - [service]: [active / expired / not configured]
   [for each known service]

   [Always:]
   Which services would you like to [connect / reconnect]?

   A) Claude (claude.ai) — Anthropic's AI
   B) ChatGPT (chat.openai.com) — OpenAI's AI
   C) Gemini (gemini.google.com) — Google's AI
   D) All available services
   E) Only reconnect expired sessions
   F) A different service (provide the URL)
   ```

4. Record the user's selection. Process each selected service through Layers 2–3 sequentially.

---

## LAYER 2: LOGIN AND SESSION CAPTURE (repeat for Each Selected service)

**Stage Focus:** Launch a visible browser, guide the user through login, and save the authenticated session.

### Processing Instructions

1. Create the sessions directory if it does not exist: `[workspace]/config/browser-sessions/`.
2. Launch Playwright with a visible Chromium browser:

   ```python
   browser = playwright.chromium.launch(headless=False)
   context = browser.new_context()
   page = context.new_page()
   ```

3. Navigate to the service's chat page:
   - IF Claude: `page.goto("https://claude.ai")`
   - IF ChatGPT: `page.goto("https://chat.openai.com")`
   - IF Gemini: `page.goto("https://gemini.google.com")`
   - IF custom service: `page.goto("[user-provided URL]")`

4. Instruct the user:

   ```
   A browser window has opened to [service name].

   Please log in to your account in that browser window. Complete any
   two-factor authentication or CAPTCHA challenges that appear.

   When you can see the chat interface (the place where you would
   normally type a message), tell me "I'm logged in" and I'll save
   the session.

   If you don't have an account, you can create one now — most
   services offer a free tier.
   ```

5. Wait for user confirmation.
6. After confirmation, save the browser session:

   ```python
   context.storage_state(path="[workspace]/config/browser-sessions/[service].json")
   ```

7. Confirm: "Session saved for [service]. I'll now test that it works."

---

## LAYER 3: VERIFICATION AND REGISTRATION (repeat for Each service)

**Stage Focus:** Verify the saved session works for automated access and register the endpoint.

### Processing Instructions

1. Close the login browser context. Open a new context using the saved session:

   ```python
   context = browser.new_context(storage_state="[workspace]/config/browser-sessions/[service].json")
   page = context.new_page()
   ```

2. Navigate to the service's chat page. Verify the page loads in a logged-in state (chat interface visible, not redirected to login).
3. IF logged-in state confirmed:
   - Report: "Session verified — [service] is accessible."
   - Send a minimal test prompt ("Say hello.") through the browser automation.
   - IF a response is received: "Connection fully verified. [service] responded successfully."
   - IF no response within 30 seconds: "Session is valid but the test prompt timed out. The connection should work for normal use — timeouts sometimes occur on first automated access."

4. IF redirected to login:
   - Report: "The session didn't persist. This sometimes happens with strict security settings. Let's try again."
   - Return to Layer 2 for this service.
   - IF second attempt also fails: "This service's security settings may not support session persistence. You can still use it through API keys (covered in a later chapter). Skipping [service]."

5. Register the endpoint in `[workspace]/config/endpoints.json`:

   Read the current registry. Add or update the entry for this service:

   ```json
   {
     "name": "[service]-browser",
     "type": "browser",
     "service": "[claude|chatgpt|gemini|custom]",
     "session_path": "config/browser-sessions/[service].json",
     "status": "active",
     "verified": "[ISO date]"
   }
   ```

   IF this service had a previous entry, THEN update it (do not create a duplicate).

   IF no `default_endpoint` is set in the registry, THEN set it to this service.

6. Close the browser.

---

## LAYER 4: SUMMARY

**Stage Focus:** Present results and explain what comes next.

### Processing Instructions

1. Present the summary:

   ```
   BROWSER EVALUATION CONNECTIONS CONFIGURED

   [For each service:]
   - [service]: [Connected and verified / Connected but unverified / Failed — (reason)]

   Your system can now access [service list] through browser automation.
   This uses your existing [free/paid] subscription at no additional cost.

   Your boot.md specification knows how to use these connections through
   the browser_evaluate tool. When adversarial review is needed (boot-v4
   and later), the system sends prompts to these services automatically.

   Sessions may expire periodically (typically every few days to weeks,
   depending on the service). If your system reports that a connection
   has expired, run this framework again to reconnect.

   To add more services later, tell your AI:
   "Read and execute frameworks/browser-eval-setup.md"
   ```

2. IF no services were successfully connected:

   ```
   No browser automation connections were configured. Your system will
   operate in local-only mode. You can:

   - Run this framework again to try connecting
   - Set up API keys instead: "Read and execute frameworks/api-key-setup.md"
   - Continue with local-only operation (everything works, but without
     independent adversarial review from a different model)
   ```

---

## RECOVERY

### Session Persistence Failures

WHEN a saved session does not persist across browser restarts:
- This is most commonly caused by the service using session cookies that are not included in Playwright's storage state.
- Suggest: "Try logging in again. Some services require you to check 'Remember me' or 'Stay signed in' during login."
- IF persistent failure: note that API keys (via the API Key Acquisition Framework) are the reliable alternative.

### Playwright Not Installed

WHEN Playwright or Chromium binaries are missing:
- Report: "Playwright is not installed. Run the first boot framework to install it, or install manually: `pip install playwright && python3 -m playwright install chromium`"
- Halt — this framework cannot execute without Playwright.

### Service Temporarily Unavailable

WHEN a service's website is down or unreachable:
- Report the specific error (timeout, DNS failure, HTTP error).
- Offer to skip this service and continue with others.
- Note that the user can retry later.

---

## EXECUTION COMMANDS

1. Confirm you have fully processed this framework.
2. Begin with Layer 1 (Service Selection). Check for existing sessions before asking the user to choose.
3. Process Layers 2–3 for each service the user selects.
4. Complete Layer 4 (Summary) after all services are processed.
5. IF invoked because a specific session expired (rather than by user request), THEN skip Layer 1's selection prompt and proceed directly to Layer 2 for the expired service.

---

*End of Browser Evaluation Setup Framework v1.0*
