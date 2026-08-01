### PHASE 1, LAYER 1: PYTHON ENVIRONMENT

**Status 2026-06-16: legacy natural-language installer layer.** Do not execute this file as the live installer. Use `scripts/install.py --profile solo`; this layer is retained for G3.32 reconciliation.

**Stage Focus:** Ensure Python 3 and pip are installed and functional, and that all required packages are importable.

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
       flask \
       watchfiles
   ```

   Note on `--break-system-packages`: Required on macOS with system Python (PEP 668). The flag is harmless on systems where it is not required.

   IF any package fails to install, THEN:
   - Report the specific package and error.
   - Attempt to install the remaining packages (do not abort the entire install for one failure).
   - Record the failure in the installation report.

4. Verify key packages imported successfully:

   ```python
   python3 -c "import chromadb; import keyring; import watchfiles; try: from ddgs import DDGS
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
- `flask`: HTTP server framework for the universal chat server installed in Layer 6.

### Output Format for This Layer

```
PYTHON ENVIRONMENT CONFIGURED
Python version: [version]
pip version: [version]
Packages installed: [list]
Packages failed: [list, or "none"]
Verification: [Pass / Fail with details]
```

---
