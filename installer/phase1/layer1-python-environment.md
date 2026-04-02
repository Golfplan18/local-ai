### PHASE 1, LAYER 1: PYTHON ENVIRONMENT

**Stage Focus:** Ensure Python 3 and pip are installed and functional, and verify that Playwright can actually launch a browser — not just that it is installed.

### Processing Instructions

1. Check whether Python 3 is installed and accessible.
   - IF macOS: execute `python3 --version`. IF not found, check for Xcode command line tools: `xcode-select -p`. IF Xcode tools are not installed, install them: `xcode-select --install` (this includes Python 3). Wait for installation to complete.
   - IF Linux: execute `python3 --version`. IF not found, install via package manager: `sudo apt install python3 python3-pip` (Debian/Ubuntu) or equivalent.
   - IF Windows: execute `python --version` and `python3 --version`. IF neither found, download and install from python.org — use the official installer, ensure "Add to PATH" is checked.

2. Verify pip is available.
   - Execute `python3 -m pip --version`.
   - IF not found: execute `python3 -m ensurepip --upgrade`.
   - IF still not found on macOS/Linux: `curl https://bootstrap.pypa.io/get-pip.py | python3`.

3. Install the complete package set for all book versions:

   ```
   python3 -m pip install --break-system-packages \
       chromadb \
       duckduckgo-search \
       ddgs \
       keyring \
       anthropic \
       openai \
       google-generativeai \
       playwright \
       flask
   ```

   Note on `--break-system-packages`: Required on macOS with system Python (PEP 668). The flag is harmless on systems where it is not required.

   IF any package fails to install, THEN:
   - Report the specific package and error.
   - Attempt to install the remaining packages (do not abort the entire install for one failure).
   - Record the failure in the installation report.

4. Install Playwright browser binaries:

   ```
   python3 -m playwright install chromium
   ```

   This downloads a standalone Chromium browser (~150 MB) used for browser automation. It does not affect the user's existing browser installation.

   IF installation fails, THEN:
   - Report the specific error.
   - Note that browser automation will not be available until this is resolved.
   - Continue with remaining Phase 1 layers (the system can still function with API keys if browser automation fails).

5. Verify Playwright browser binaries are present:

   ```
   python3 -m playwright install chromium --dry-run
   ```

   IF the dry-run reports missing binaries, THEN install them:

   ```
   python3 -m playwright install chromium
   ```

   Note: On Linux, Playwright requires system dependencies that pip does not install. If the above fails on Linux, run:

   ```
   python3 -m playwright install-deps chromium
   python3 -m playwright install chromium
   ```

   On macOS, no system dependencies are required beyond what Xcode command line tools provides.

   On Windows, Playwright should install without additional dependencies. If installation fails, verify that the user has write permissions to `%USERPROFILE%\AppData\Local\ms-playwright`.

6. Verify Playwright can actually launch a browser (not just that it is installed):

   ```python
   python3 -c "
   from playwright.sync_api import sync_playwright
   with sync_playwright() as p:
       browser = p.chromium.launch(headless=True)
       page = browser.new_page()
       page.goto('about:blank')
       browser.close()
       print('Playwright browser launch: OK')
   "
   ```

   This test confirms the browser binary is present, executable, and capable of launching. A pip install that succeeded but produced a broken binary will fail here with a clear error.

   IF this test fails, THEN:

   - On Linux: Run `python3 -m playwright install-deps chromium` and retry.
   - On macOS: Check for missing Xcode command line tools: `xcode-select -p`. If absent, install: `xcode-select --install`.
   - On Windows: Check antivirus software is not blocking browser launch. Verify write permissions to the AppData directory.
   - Record the failure in the installation report.
   - Note: The system can still function without browser automation if API keys are provided later. However, Tier 0 readers require browser automation — do not continue to Layer 5 (Commercial AI Connections) if this test fails on a Tier 0 machine.

7. Verify key packages imported successfully:

   ```python
   python3 -c "import chromadb; import keyring; from playwright.sync_api import sync_playwright; try: from ddgs import DDGS
   except ImportError: from duckduckgo_search import DDGS; print('All packages verified.')"
   ```

   IF verification fails for any package, THEN report the specific import error.

### Package Purposes (for documentation)

- `chromadb`: Vector database for semantic search. Used at v5. Includes default embedding model — no external embedding service required for basic operation.
- `ddgs` / `duckduckgo-search`: Web search with no API key required. Used at v1+. Install both; import `ddgs` with a fallback to `duckduckgo_search` to handle package renames.
- `keyring`: Cross-platform secure credential storage (macOS Keychain, Windows Credential Manager, Linux SecretService). Used at v4-B+.
- `anthropic`: Anthropic API client for Claude evaluations. Used at v4-B if Claude selected for API overflow.
- `openai`: OpenAI API client for GPT evaluations. Used at v4-B if GPT selected for API overflow.
- `google-generativeai`: Google API client for Gemini evaluations. Used at v4-B if Gemini selected for API overflow.
- `playwright`: Browser automation for commercial AI access. Used at all tiers as the primary channel for cloud AI interaction. Uses existing subscriptions at no additional cost.
- `flask`: HTTP server framework for the universal chat server installed in Layer 7.

### Output Format for This Layer

```
PYTHON ENVIRONMENT CONFIGURED
Python version: [version]
pip version: [version]
Packages installed: [list]
Packages failed: [list, or "none"]
Playwright pip install: [installed / failed]
Playwright browser binaries: [installed / failed — (reason)]
Playwright launch test: [PASS / FAIL — (reason)]
Verification: [Pass / Fail with details]
```

---

