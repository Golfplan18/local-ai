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
   ├── config/         ← system configuration files
   ├── chromadb/       ← vector database (two collections: knowledge, conversations)
   ├── models/         ← downloaded model files (Phase 2)
   ├── server/         ← chat interface server files
   └── docs/           ← hardware report and README
   ```

   Note (install Chunk 1, 2026-05-18): the `config/browser-sessions/` directory that previously held Playwright session state was retired alongside the deprecated subscription-account dispatcher. Subscription-based model dispatching was replaced by API-only routing through OpenRouter. Playwright may be re-incorporated as a generic tool when a real use case appears, but it is no longer part of the default install.

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
5. Create the framework registry file at `[workspace]/frameworks/framework-registry.md` populated with initial entries for all book-shipped frameworks. Each entry follows the registry entry format produced by the PFF (name, purpose, problem class, input summary, output summary, proven applications, known limitations, file location, provenance, confidence, version).
6. Write `config/routing-config.json` with the three paths, an empty endpoint registry, and the v2 schema's required blocks. (Note: install Chunk 12 retired `endpoints.json` and consolidated everything into `routing-config.json` — see `_schema_notes.v1_compat_fields_carried` in the file for the migration history.)

   ```json
   {
     "_schema_version": 2,
     "paths": {
       "vault": "[user-chosen path]",
       "conversations": "~/Documents/conversations/",
       "chromadb": "[workspace]/chromadb/"
     },
     "endpoints": [],
     "default_endpoint": null,
     "slot_assignments": {},
     "gear4_overrides": {},
     "operational_context": {
       "interactive": ["local", "api"],
       "autonomous": ["local"],
       "agent": ["local"]
     },
     "slots": {},
     "buckets": {}
   }
   ```

   Note: the `"browser"` transport that previously appeared in `operational_context.interactive` was retired with the subscription-account dispatcher (install Chunk 1). Live transports are now `local` (MLX, Ollama) and `api` (OpenRouter, direct Anthropic/OpenAI/Google).

7. Initialize ChromaDB at `[workspace]/chromadb/` with two empty collections:
   - `knowledge` — will index the vault
   - `conversations` — will index processed conversation chunks

   ```python
   import chromadb
   client = chromadb.PersistentClient(path="[workspace]/chromadb/")
   client.get_or_create_collection("knowledge")
   client.get_or_create_collection("conversations")
   ```

8. IF any directory already exists (from a prior run), THEN skip it without error.
9. Create a `.gitkeep` file in each empty directory so Git tracks them.

### Output Format for This Layer

```
DIRECTORY STRUCTURE CREATED
System folder: [workspace path]
  Directories: modes/, frameworks/, frameworks/user/, config/,
               chromadb/, models/, server/, docs/
Conversations folder: ~/Documents/conversations/
  Subdirectory: raw/
Vault: [user-chosen path]
  Structure: flat (no subfolders)
Framework registry: [workspace]/frameworks/framework-registry.md (populated with book-shipped entries)
ChromaDB: initialized with collections [knowledge, conversations]
Routing config: [workspace]/config/routing-config.json written with paths, empty endpoint registry,
                and v2 schema scaffolding
```

---

