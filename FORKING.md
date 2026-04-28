# Forking This System

This system was designed to be forked. Not as a courtesy — as the point.

The premise of this project is that natural language is source code. The installer that builds this system is written in natural language. The specification that describes the system is written in natural language. If you fork this repository, customize the system, and run the reconciliation framework, your fork produces its own specification and its own installer — both in natural language. Your version becomes a complete, self-describing system that anyone can install from your instructions.

There is no one-size-fits-all version of this system. There is a base version, and there are as many forks as there are people with ideas about how it should work.

## What You Need

- A GitHub account
- Two repositories: one **public** (your fork of this system), one **private** (your personal data)
- The system installed and running (see the book, Chapter 1, or `installer/install-manifest.md`)

## Repository Architecture

### Your Public Fork (this repo)

Everything the system needs to run on any machine:

| Directory | Contents |
|---|---|
| `installer/` | Natural language installer layers — execute these to build the system |
| `orchestrator/` | Pipeline engine and tool implementations |
| `server/` | Chat interface (Flask + browser UI) |
| `frameworks/` | Framework library (thinking tools for AI) |
| `modes/` | Analysis modes (18 ways to approach a problem) |
| `modules/` | Thinking tools and question banks |
| `config/` | Configuration templates and theme files |
| `boot/` | System prompt |

These files are tracked in git. When you customize them, your fork diverges from the original. That's the point.

### Your Private Repository (your data)

Everything specific to you that should never be public:

| Item | What It Is |
|---|---|
| `mind.md` | Your system's personality and behavioral rules |
| `config/endpoints.json` | Your API keys and service credentials |
| `config/browser-sessions/` | Your logged-in browser cookies |
| `chromadb/` | Your knowledge base |
| `knowledge/` | Your mental models and indexed documents |
| `frameworks/personal/` | Frameworks you created for yourself |
| `agents/*.md` | Agent identities you programmed |
| `models/` | Downloaded model files |
| `reconciliation/` | Your reconciliation sweep reports |

The `.gitignore` already excludes all of these from the public repo. To back them up, create a separate private repository pointed at your data directories, or use your own backup method.

## The Fork-Customize-Share Workflow

### 1. Fork and Install

```
# Fork on GitHub, then:
git clone https://github.com/YOUR-USERNAME/ora.git ~/ora
```

Follow the installer manifest (`installer/install-manifest.md`) to build the system. The installer is written in natural language — load it into Claude Code and it builds everything.

### 2. Use It

Use the system. Talk to it. Push it. The base system works out of the box.

### 3. Customize It

This is where your fork becomes yours. Ideas that make the system better for you:

- **New modes** — add analysis modes in `modes/` for domains you work in
- **New frameworks** — create frameworks in `frameworks/user/` for problems you solve repeatedly
- **UI changes** — modify `server/index.html` and themes in `config/themes/`
- **New tools** — add orchestrator tools in `orchestrator/tools/`
- **Pipeline changes** — modify `orchestrator/boot.py` to change how queries are processed
- **New thinking tools** — add question banks in `modules/tools/`

Every change you make creates drift between the installer (which describes the old system) and the filesystem (which contains your system). That drift is expected. It's the raw material for the next step.

### 4. Reconcile

Run the Spec-Code Reconciliation Framework (`frameworks/book/spec-code-reconciliation.md`). It:

1. Compares every installer layer against your actual filesystem
2. Identifies every difference — what you added, changed, or removed
3. Updates the installer layers to describe your system
4. Produces a natural language system specification — a single document that describes your entire system in plain English

After reconciliation, your fork's installer would build your system on a fresh machine. The specification describes it completely. The natural-language-is-source-code loop is closed.

### 5. Share

```
git add -A
git commit -m "My customizations + reconciled installer"
git push origin main
```

Your fork is now a complete, installable system. Anyone who clones it and runs the installer gets your version. The specification tells them what they're getting before they install.

## Finding Other Forks

GitHub's fork network shows everyone who forked this repository. Browse forks to find:

- Domain-specific versions (legal, medical, engineering, creative writing)
- UI experiments (different layouts, new panel types, alternative themes)
- Pipeline modifications (different evaluation strategies, new processing steps)
- Tool additions (new orchestrator capabilities)

If you find a fork with features you want, you can cherry-pick commits, merge branches, or read their specification to understand their design decisions — then implement your own version.

## Upstream Updates

The original repository will continue to receive updates. To pull upstream changes into your fork:

```
git remote add upstream https://github.com/ora-commons/ora.git
git fetch upstream
git merge upstream/main
```

If the merge has conflicts, resolve them — your customizations take priority. Then run reconciliation again to update the installer and specification to reflect the merged state.

## What Not to Share

Your public fork should never contain:

- API keys or credentials (`config/endpoints.json` — use the template)
- Browser session cookies (`config/browser-sessions/`)
- Your `mind.md` (unless you want to — it contains personal values)
- Downloaded model files (too large for git; each user downloads their own)
- Your ChromaDB data (personal knowledge)

The `.gitignore` handles all of this automatically. Don't override it.

## The Thesis

Every fork that runs reconciliation proves the thesis: natural language specifications can describe a running system completely enough that the system can be rebuilt from the description alone. Every fork that diverges and reconciles is another proof. The more forks, the stronger the evidence.
