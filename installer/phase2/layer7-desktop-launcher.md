### PHASE 2, LAYER 7: DESKTOP LAUNCHER CREATION

**Stage Focus**: Create a one-click launcher that starts the Phase 1 chat server and opens the browser interface.

**Input**: Workspace path, server file path, port number, operating system.

**Output**: A clickable desktop launcher that starts the AI chat system.

### Processing Instructions

1. Generate the launcher script at `[workspace]/start.sh` (macOS/Linux) or `[workspace]/start.bat` (Windows). The script must:
   a. Check for and terminate any existing server process from a previous session (the Stale Process Trap).
   b. IF Ollama: start the Ollama service if not already running.
   c. Start `[workspace]/server/server.py` in the background.
   d. Wait for the server to become responsive (poll the health endpoint every second, timeout after 30 seconds).
   e. Open the default browser to `http://localhost:5000` (or the port the server selected).
   f. IF the server fails to start within 30 seconds, THEN display an error message explaining what went wrong.

2. Generate a stop script at `[workspace]/stop.sh` (macOS/Linux) or `[workspace]/stop.bat` (Windows) that cleanly shuts down the server and the inference engine.
3. **macOS launcher:**
   a. Create an Automator application or a `.command` file that executes the start script.
   b. IF Automator is available, THEN create an `.app` bundle — this produces a double-clickable application icon.
   c. IF Automator is not available or fails, THEN create a `.command` file (ensure it is executable: `chmod +x`).
   d. Copy or symlink the launcher to the Desktop.

4. **Linux launcher:**
   a. Create a `.desktop` file at `~/.local/share/applications/ora.desktop`.
   b. Also place a copy on the Desktop if `~/Desktop/` exists.

5. **Windows launcher:**
   a. Create a shortcut to the `.bat` file on the Desktop.

6. Test the launcher:
   a. Execute the launcher.
   b. Verify the browser opens to `http://localhost:5000`.
   c. Verify the chat interface is responsive.
   d. Execute the stop script and verify the server and inference engine stop cleanly.

### Output Format for This Layer

```
LAUNCHER CREATED
Start: [path to launcher]
Stop: [path to stop script]
Desktop shortcut: [path]
Opens: http://localhost:5000
Test result: [Pass / Fail]
```

---

