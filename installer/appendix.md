### How File Access Actually Works

- Boot-v1.md defines the tool protocol — what the model is allowed to request and the exact XML format for requesting it
- The orchestrator (installed by the boot framework) watches the model's output for those XML tags, executes the corresponding Python function on your machine, and injects the result back into the conversation
- The model never touches your files directly — it asks, Python acts, Python reports back
- Boot-v1.md without the orchestrator is instructions with no one to follow them — the model will issue tool calls into silence
- This is also why pasting boot-v1.md into claude.ai directly does not give you file access — claude.ai has no orchestrator watching for your tool calls

### What This Means Practically

- Every interaction goes through localhost:5000 — the browser interface that has Python in the loop
- Direct access to commercial AI interfaces (claude.ai, ChatGPT) is for casual conversation, not orchestrated workflows
- The desktop launcher the boot framework created starts the server and opens localhost:5000 — this is the entry point for all serious work
- The intelligence is in the model; the reach is in Python; boot-v1.md is the contract between them

### What You Now Have at Every Tier

- Internet access: available at all tiers (commercial AI already had this; now it flows through the orchestrator)
- Local file read and write: available at all tiers via the orchestrator's file tools
- Anti-confabulation directives: active via boot.md at every conversation
- Session logging: the orchestrator writes a timestamped log of every session to [workspace]/logs/
- The Bridge tier user has commercial AI intelligence with local file reach, running through Python on their machine
- Scout, Workhorse, and Sovereign users have the same baseline with a local model as the primary endpoint

---

## MISSING INFORMATION DECLARATION

Before finalizing, explicitly state:
- Any hardware characteristic that could not be measured and was assumed.
- Any model metadata that could not be read (parameter count, quantization level) and was estimated.
- Any installation step that produced warnings (even if it succeeded).
- Any verification test that was skipped and why.
- Any known limitation of the installed configuration (e.g., "Your model is Tier 1 — it will handle basic questions well but may struggle with complex analysis or reliable tool calling").
- Any companion file that was not found and where a default was applied (especially chat templates).
- Whether Playwright launch test passed or failed, and its impact on Tier 0 functionality.

A response that acknowledges limitations is always preferable to a response that implies the setup is more capable than it is.

---

## RECOVERY DECLARATION

IF any of the following unresolved issues remain:
- Model could not be loaded (Phase 2, Layer 5 invariant check failed)
- Chat template mismatch producing garbled output
- Playwright launch test failed on a Tier 0 machine (no fallback AI access)
- Chat server tool execution test failed
- End-to-end test failed

THEN for each issue, state:
- What specifically failed.
- What was attempted to resolve it.
- What the user can do next (specific action, not general advice).
- Whether re-running the framework would help or whether the issue requires manual intervention.

---

## EXECUTION SEQUENCE SUMMARY

```
PHASE 1 — UNIVERSAL BASE (every reader)
  Layer 1: Python Environment (+ Playwright launch verification)
  Layer 2: Directory Structure (system folder, vault, ~/Documents/conversations/, ChromaDB init)
  Layer 3: Framework Library (Git clone)
  Layer 4: Orchestrator Installation (boot.py — terminal interface)
  Layer 5: Commercial AI Connections (Playwright)
  Layer 6: API Key Framework Installation (staged, not executed)
  Layer 7: Universal Chat Server (browser interface with agentic loop)

  Hardware Evaluation (inform, not gate)

  IF hardware supports local models → PHASE 2
  IF not → Phase 1 Completion (documentation, verification, Tier 0 launcher)

PHASE 2 — ADDITIVE LOCAL CAPABILITY (hardware permitting)
  Layer 1: Hardware Evaluation (detailed)
  Layer 2: Model Selection
  Layer 3: Workspace Setup (verify existing structure)
  Layer 4: Inference Engine Installation
  Layer 5: Model Download
  Layer 6: Local Endpoint Registration + Routing Verification
  Layer 7: Desktop Launcher Generation
  Layer 8: Documentation and Verification
  Layer 9: Model Switcher Module (Tier C only — multi-model pipeline slot configuration)
  Layer 10: Interface Customization Framework (all tiers — layouts, themes, layout generator)
  Layer 11: App Bundle + Custom Icon (macOS only — ai.app with Python launcher and lettermark icon)
  Layer 12: Conversation Auto-Save + RAG Indexing (all tiers — markdown logs + ChromaDB indexing)

  Local Endpoint Registration
```

---

## EXECUTION COMMANDS

1. Confirm you have fully processed this framework.
2. IF you are not running as a coding agent with terminal access on the user's local machine, THEN inform the user that this framework requires Claude Code or an equivalent tool and cannot execute in a standard chat interface.
3. Before beginning Phase 1, Layer 1, present the following:

```
This framework will set up a local AI system on your machine.
Before I start, I need to understand what you're looking for.

MODELS — Do you already have a model in mind?
(This applies to Phase 2 — local model installation.
Phase 1 gives you cloud AI access regardless of your answer.)

A) Yes — I have a specific model.
   (Give me the Hugging Face URL, repository name, or model name.)

B) I have a general idea but want help choosing.
   (I'll ask about your use case and walk you through the options.)

C) I'm new to this — explain my options.
   (I'll explain what AI models are, what's available, and how
   to choose. You can ask as many questions as you want.)

D) Just pick the best one for my hardware.
   (I'll evaluate your machine and select automatically.)

WORKSPACE — Do you have a folder you want me to use?
If not, I'll create one at [default path for detected OS].

Once I know your model preference, I'll proceed through these steps:

PHASE 1 (every reader):
1. Install Python, Playwright, and required packages — with browser verification
2. Create the workspace directory structure
3. Install the framework library from the book repository
4. Install the orchestrator (boot.py) with tool implementations
5. Connect to commercial AI services via browser automation
6. Stage the API key framework for later use
7. Install the universal chat server at localhost:5000

PHASE 2 (hardware permitting — 8GB+ RAM):
8.  Evaluate your hardware in detail
9.  Help you select a local model
10. Verify the workspace
11. Install or verify the inference engine
12. Download your model and verify all required files
13. Register the local model endpoint in the chat server
14. Create a desktop launcher
15. Generate documentation and run final verification
16. Install the Model Switcher Module (Tier C only — configure which model fills each pipeline slot)
17. Install the Interface Customization Framework (all tiers — layout presets, themes, layout generator)

After Phase 1, you'll have a working AI interface at localhost:5000
with commercial AI access and full tool support.
After Phase 2, the same interface will use your local model by default.

I'll explain each step before doing it and ask for your approval
on key decisions. You can stop at any time.
```

---

*This framework installs a universal browser chat interface for every reader in Phase 1, closing the Unmanned Chat Trap from earlier versions. Every reader, regardless of tier, interacts with AI through Python from their first session. Phase 2 adds local model capability without replacing the Phase 1 server — the local model registers as a new endpoint in the same chat server. The model is never directly accessible without the orchestrator in the loop.*
