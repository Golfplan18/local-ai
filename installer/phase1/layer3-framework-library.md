### PHASE 1, LAYER 3: FRAMEWORK LIBRARY

**Stage Focus:** Clone the book's framework repository into the frameworks directory, giving the reader every framework at once.

### Processing Instructions

1. Check whether Git is installed.
   - Execute `git --version`.
   - IF not found on macOS: `xcode-select --install` includes Git.
   - IF not found on Linux: `sudo apt install git` or equivalent.
   - IF not found on Windows: download from git-scm.com or use `winget install Git.Git`.

2. Clone the book's framework repository:

   ```
   git clone [REPOSITORY_URL] [workspace]/frameworks/book
   ```

   Replace `[REPOSITORY_URL]` with the actual repository URL when it is established. IF the repository has not been published yet, THEN create a placeholder README at `[workspace]/frameworks/README.md` explaining that frameworks will be installed when the repository is available, and provide the expected URL.

3. IF the frameworks directory already contains a cloned repository, THEN pull the latest version:

   ```
   cd [workspace]/frameworks/book && git pull
   ```

4. Copy the active boot.md specification to the workspace root:

   ```
   cp [workspace]/frameworks/book/boot/boot-v1-agent.md [workspace]/boot.md
   ```

   The file at `[workspace]/boot.md` is always the current active specification. When the reader upgrades versions, they copy the new version to this location (or the upgrade framework does it for them).

### Output Format for This Layer

```
FRAMEWORK LIBRARY INSTALLED
Repository: [URL or "placeholder — repository not yet available"]
Location: [workspace]/frameworks/book/
Frameworks available: [count, or list]
Active boot.md: [workspace]/boot.md → [version]
```

---

