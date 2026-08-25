# Forking This System

This system was designed to be forked. Not as a courtesy — as the point.

The premise of this project is that natural language is part of the system's specification. The current public install is a source install driven by `scripts/install.py`; the repository also contains documentation and configuration that describe how the system is intended to work. A fork may need to keep those descriptions aligned with its code, but no automatic reconciliation service is promised here.

There is no one-size-fits-all version of this system. There is a base version, and there are as many forks as there are people with ideas about how it should work.

## What You Need

- A GitHub account
- Two repositories: one **public** (your fork of this system), one **private** (your personal data)
- The system installed from the repository's current instructions (`scripts/install.py` and `help/install-guide.md`)

## Repository Architecture

### Your Public Fork (this repo)

Everything the system needs to run on any machine:

| Directory | Contents |
|---|---|
| `installer/macos/` | macOS launch support used by the current installer |
| `orchestrator/` | Pipeline engine and tool implementations |
| `server/` | V3 interface (Flask, browser UI, component styles/scripts, and theme packages) |
| `frameworks/` | Framework library (thinking tools for AI) |
| `modes/` | Resident analysis mode specifications; the set can change over time |
| `thinking-tools.md` | Runtime mirror of the canonical Thinking Tools Library |
| `config/` | Runtime configuration templates |
| `boot/` | System prompt |

These files are tracked in git. When you customize them, your fork diverges from the original. That is the point of a fork; the repository does not promise that every fork has the same resident files or capabilities.

### Data to keep private in your own fork

Everything specific to you that should never be public:

| Item | What It Is |
|---|---|
| `mind.md` | Your system's personality and behavioral rules |
| `config/routing-config.json` | Tracked in this public repository; it contains endpoint, slot, and provider configuration, not a private-vault copy |
| `~/.config/ora-server.env` (server) or env vars (Mac) | Your API keys |
| `chromadb/` | Your knowledge base |
| `knowledge/` | Your mental models and indexed documents; this checkout does not ignore this path, so inspect it before committing |
| `frameworks/personal/` | Frameworks you created for yourself |
| `agents/*.md` | Agent identities you programmed |
| `models/` | Downloaded model files |
| `reconciliation/` | Your reconciliation sweep reports |

Ordinary forkers do not have access to the author's private vault or to data outside the repository. This list identifies material a fork owner may want to keep private; it is not a promise that the upstream repository supplies a private vault or that `.gitignore` hides every item. To back up personal data, create a separate private repository or use another backup method.

## The Fork-Customize-Share Workflow

### 1. Fork and Install

```
# Fork on GitHub, then:
git clone https://github.com/YOUR-USERNAME/ora.git ~/ora
cd ~/ora
python3 scripts/install.py --profile solo
```

Follow `help/install-guide.md` for the source-install path. `scripts/install.py` is the only desktop installer; the legacy natural-language layer set that used to sit under `installer/` was retired and only `installer/macos/` remains.

### 2. Use It

Use the system and evaluate it in your own environment. The repository's instructions and checks are the evidence for a particular checkout; a fork should not be assumed complete or installable merely because it exists.

### 3. Customize It

This is where your fork becomes yours. Ideas that make the system better for you:

- **New modes** — add analysis modes in `modes/` for domains you work in
- **New frameworks** — create frameworks in `frameworks/user/` for problems you solve repeatedly
- **UI changes** — modify the V3 shell in `server/index-v3.html`, component styles under `server/static/styles/`, and behavior under `server/static/js/` (including `v3-layout.js`)
- **Theme changes** — use the V3 Theme Library, or add a fork-bundled package under `server/static/themes/<theme-id>/` with `manifest.json` and `theme.css`; theme operations are exposed through `/api/v3-themes/*`
- **New tools** — add orchestrator tools in `orchestrator/tools/`
- **Pipeline changes** — modify `orchestrator/boot.py` to change how queries are processed
- **New thinking tools** — extend `Projects/Ora/Reference — Thinking Tools Library.md` in the vault, then propagate its body to `thinking-tools.md`

Every change you make can create differences between code, documentation, configuration, and your local data. Review those differences as part of maintaining your fork.

The V3 workspace layout is intentionally defined in the interface code. Do not recreate the retired `config/interface.json`, `config/layouts/` presets, layout APIs, or natural-language layout generator when customizing a fork. A changed layout is a cohesive V3 shell/style/script change; a changed visual theme belongs in the V3 Theme Library rather than the retired `config/themes/` directory.

### 4. Reconcile what you changed

There is no public one-command reconciliation service for ordinary forkers. Compare the files you changed with the current code path, run the repository's setup/build/test checks, and update the relevant documentation manually. Ora's internal Documentation-Code Parity material can inform a deeper review when you have access to that project context, but it is not a guarantee that a pass leaves code and documentation aligned.

### 5. Share

```
git add -A
git commit -m "My customizations + reconciled installer"
git push origin main
```

Pushing a fork publishes your changes. It does not by itself prove that the fork is complete or installable. State the checks you ran and any setup limits in your fork's own documentation.

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

If the merge has conflicts, resolve them according to your fork's goals. Re-run the relevant setup, build, and test checks, then update documentation for the resulting state.

## What Not to Share

Your public fork should never contain:

- API keys or credentials (kept out of the repo entirely — they live in env vars or `~/.config/ora-server.env`, never in `config/routing-config.json`)
- Your `mind.md` (unless you want to — it contains personal values)
- Downloaded model files (too large for git; each user downloads their own)
- Your ChromaDB data (personal knowledge)

Review the repository's actual `.gitignore` rules and `git status` before committing. In this checkout, `config/routing-config.json` is tracked and `knowledge/` is not ignored, so never rely on `.gitignore` alone to protect personal data or credentials.

## The Thesis

Forking tests the thesis that public code, documentation, and user judgment can support independent adaptation. A successful fork is evidence from that fork's own checks; it is not proof that every fork is complete, installable, or fully aligned.
