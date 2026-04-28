### PHASE 1, LAYER 2: DIRECTORY STRUCTURE

**Stage Focus:** Create the three-location directory structure used by all boot.md versions: the system folder, the conversations folder, and the vault.

### Processing Instructions

1. Create the following directories within the system folder (default `~/ora/` on macOS/Linux, `%USERPROFILE%\ora\` on Windows):

   ```
   [workspace]/
   ├── modes/          ← mode specification files (17 files)
   ├── frameworks/     ← framework library from the book repository
   │   ├── user/       ← user-created frameworks accumulate here
   │   └── framework-registry.md ← index of all frameworks (populated with book-shipped entries)
   ├── agents/         ← agent identity files (created empty)
   │   └── agent-registry.md     ← manifest of all agents (created with empty template)
   ├── config/         ← system configuration files
   │   └── browser-sessions/  ← Playwright session state
   ├── chromadb/       ← vector database (two collections: knowledge, conversations)
   ├── models/         ← downloaded model files (Phase 2)
   ├── server/         ← chat interface server files
   └── docs/           ← hardware report and README
   ```

2. Create the conversations folder at `~/Documents/conversations/` (default location, all platforms — `%USERPROFILE%\Documents\conversations\` on Windows):

   ```
   ~/Documents/conversations/
   └── raw/            ← archive: original conversation exports
   ```

3. Ask the user where they want their vault:

   "Your vault is where your work lives — notes, documents, research, AI-generated outputs. Everything you create or save goes here.

   The default location is [~/Documents/vault/ on macOS/Linux, %USERPROFILE%\Documents\vault\ on Windows].

   You can put it anywhere. If you plan to use Obsidian later, we recommend relying on iCloud (macOS) or your existing file sync service rather than Obsidian Sync. Obsidian Sync and iCloud sync on the same folder can cause conflicts. Since the vault is plain Markdown files, iCloud handles it seamlessly. Only use Obsidian Sync if you need to sync between a Mac and a non-Apple device and have no other sync service available.

   Where would you like your vault? Press Enter for the default, or type a path."

4. Create the vault folder at the user's chosen location. Do NOT create subfolders inside it — the vault is flat.
5. Create the agent registry file at `[workspace]/agents/agent-registry.md` with the empty template:

   ```markdown
   # Agent Registry

   ## Format

   | Field | Description |
   |---|---|
   | **Name** | Agent identifier |
   | **Type** | functional / incarnated |
   | **Created** | Date |
   | **Last Modified** | Date |
   | **Description** | One sentence describing the agent's purpose |

   ## Registered Agents

   [Entries added as agents are created through the Agent Identity Framework]
   ```

6. Create the framework registry file at `[workspace]/frameworks/framework-registry.md` populated with initial entries for all book-shipped frameworks. Each entry follows the registry entry format produced by the PFF (name, purpose, problem class, input summary, output summary, proven applications, known limitations, file location, provenance, confidence, version).
7. Write endpoints.json with the three paths and an empty endpoint registry:

   ```json
   {
     "vault_path": "[user-chosen path]",
     "conversations_path": "~/Documents/conversations/",
     "chromadb_path": "[workspace]/chromadb/",
     "endpoints": [],
     "default_endpoint": null,
     "operational_context": {
       "interactive": ["local", "browser", "api"],
       "autonomous": ["local"],
       "agent": ["local"]
     }
   }
   ```

8. Initialize ChromaDB at `[workspace]/chromadb/` with two empty collections:
   - `knowledge` — will index the vault
   - `conversations` — will index processed conversation chunks

   ```python
   import chromadb
   client = chromadb.PersistentClient(path="[workspace]/chromadb/")
   client.get_or_create_collection("knowledge")
   client.get_or_create_collection("conversations")
   ```

9. IF any directory already exists (from a prior run), THEN skip it without error.
10. Create a `.gitkeep` file in each empty directory so Git tracks them.

### Output Format for This Layer

```
DIRECTORY STRUCTURE CREATED
System folder: [workspace path]
  Directories: modes/, frameworks/, frameworks/user/, agents/, config/, config/browser-sessions/,
               chromadb/, models/, server/, docs/
Conversations folder: ~/Documents/conversations/
  Subdirectory: raw/
Vault: [user-chosen path]
  Structure: flat (no subfolders)
Agent registry: [workspace]/agents/agent-registry.md (empty template)
Framework registry: [workspace]/frameworks/framework-registry.md (populated with book-shipped entries)
ChromaDB: initialized with collections [knowledge, conversations]
Endpoints: [workspace]/config/endpoints.json written with three paths
```

---

